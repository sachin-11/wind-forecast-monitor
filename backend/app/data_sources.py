"""Data access layer.

Two interchangeable sources expose the same interface and return tidy DataFrames:

* ``ElexonSource``  - live BMRS API (FUELHH for actuals, WINDFOR for forecasts)
* ``SampleSource``  - deterministic synthetic data with the same shape (offline dev & tests)

Frames returned (all timestamps tz-aware UTC):
    actuals   : start_time, generation
    forecasts : start_time, publish_time, generation
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx
import numpy as np
import pandas as pd

from .config import Settings, settings

log = logging.getLogger(__name__)

ACTUAL_COLS = ["start_time", "generation"]
FORECAST_COLS = ["start_time", "publish_time", "generation"]


class DataSourceError(RuntimeError):
    """Raised when upstream data cannot be fetched."""


class DataSource(Protocol):
    name: str

    def actuals(self, start: datetime, end: datetime) -> pd.DataFrame: ...

    def forecasts(self, publish_from: datetime, publish_to: datetime) -> pd.DataFrame: ...


# --------------------------------------------------------------------------- cache
class TTLCache:
    """Tiny thread-safe TTL cache. Historical data never changes, so this removes
    almost all upstream calls after the first request (also survives warm serverless
    invocations)."""

    def __init__(self, ttl_s: int):
        self.ttl_s = ttl_s
        self._data: dict[tuple, tuple[float, pd.DataFrame]] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple) -> pd.DataFrame | None:
        with self._lock:
            hit = self._data.get(key)
            if hit and time.monotonic() - hit[0] < self.ttl_s:
                return hit[1]
            return None

    def set(self, key: tuple, value: pd.DataFrame) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), value)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- Elexon
class ElexonSource:
    name = "elexon"

    def __init__(self, cfg: Settings = settings, client: httpx.Client | None = None):
        self.cfg = cfg
        self.client = client or httpx.Client(timeout=cfg.http_timeout_s)
        self.cache = TTLCache(cfg.cache_ttl_s)

    def _get(self, path: str, params: dict) -> list[dict]:
        url = f"{self.cfg.elexon_base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = self.client.get(url, params=params)
                resp.raise_for_status()
                payload = resp.json()
                # stream endpoints return a bare list; non-stream endpoints wrap in {"data": [...]}
                return payload["data"] if isinstance(payload, dict) else payload
            except (httpx.HTTPError, ValueError) as exc:  # network, 5xx, bad json
                last_exc = exc
                log.warning("Elexon call failed (attempt %s): %s", attempt + 1, exc)
                time.sleep(0.5 * 2**attempt)
        raise DataSourceError(f"Elexon API unavailable: {last_exc}") from last_exc

    def actuals(self, start: datetime, end: datetime) -> pd.DataFrame:
        # FUELHH filters by settlement date (UK local date); pad one day each side then trim.
        d_from = (start - timedelta(days=1)).date().isoformat()
        d_to = (end + timedelta(days=1)).date().isoformat()
        key = ("FUELHH", d_from, d_to)
        df = self.cache.get(key)
        if df is None:
            rows = self._get(
                "/datasets/FUELHH/stream",
                {"settlementDateFrom": d_from, "settlementDateTo": d_to, "fuelType": "WIND"},
            )
            df = normalise_actuals(rows)
            self.cache.set(key, df)
        return df[(df.start_time >= start) & (df.start_time < end)].reset_index(drop=True)

    def forecasts(self, publish_from: datetime, publish_to: datetime) -> pd.DataFrame:
        key = ("WINDFOR", _iso(publish_from), _iso(publish_to))
        df = self.cache.get(key)
        if df is None:
            rows = self._get(
                "/datasets/WINDFOR/stream",
                {"publishDateTimeFrom": _iso(publish_from), "publishDateTimeTo": _iso(publish_to)},
            )
            df = normalise_forecasts(rows)
            self.cache.set(key, df)
        return df


def normalise_actuals(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=ACTUAL_COLS)
    df = pd.DataFrame(rows)
    if "fuelType" in df:
        df = df[df.fuelType == "WIND"]
    df = df.assign(start_time=pd.to_datetime(df.startTime, utc=True), generation=df.generation.astype(float))
    # A settlement period can be republished; keep the latest publication.
    if "publishTime" in df:
        df = df.sort_values("publishTime")
    df = df.drop_duplicates("start_time", keep="last")
    return df[ACTUAL_COLS].sort_values("start_time").reset_index(drop=True)


def normalise_forecasts(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=FORECAST_COLS)
    df = pd.DataFrame(rows)
    df = df.assign(
        start_time=pd.to_datetime(df.startTime, utc=True),
        publish_time=pd.to_datetime(df.publishTime, utc=True),
        generation=df.generation.astype(float),
    )
    df = df.drop_duplicates(["start_time", "publish_time"], keep="last")
    return df[FORECAST_COLS].sort_values(["publish_time", "start_time"]).reset_index(drop=True)


# --------------------------------------------------------------------------- Sample
class SampleSource:
    """Synthetic data that mimics the real feeds:

    * actuals every 30 min, smooth weather-driven wind profile (2-18 GW)
    * forecasts published 8x/day (same UTC times as WINDFOR), hourly targets up to ~66h
      ahead, error that grows with horizon plus a small positive bias.
    """

    name = "sample"
    PUBLISH_HOURS: tuple = ((2, 30), (4, 30), (7, 30), (9, 30), (11, 30), (15, 30), (18, 30), (22, 30))

    def __init__(self, seed: int = 7):
        self.seed = seed
        self.epoch = datetime(2025, 12, 1, tzinfo=UTC)

    def _truth(self, ts: pd.DatetimeIndex) -> np.ndarray:
        h = (ts - pd.Timestamp(self.epoch)).total_seconds().to_numpy() / 3600
        weather = (
            np.sin(2 * np.pi * h / 97) * 0.45 + np.sin(2 * np.pi * h / 41 + 1.3) * 0.3 + np.sin(2 * np.pi * h / 233 + 0.4) * 0.35
        )
        diurnal = np.sin(2 * np.pi * (h % 24) / 24 - 1.2) * 0.06
        return np.clip(9500 + 6000 * (weather + diurnal), 1500, 18500)

    def actuals(self, start: datetime, end: datetime) -> pd.DataFrame:
        ts = pd.date_range(start, end, freq="30min", inclusive="left", tz="UTC")
        rng = np.random.default_rng(self.seed)
        noise = rng.normal(0, 120, len(ts))
        return pd.DataFrame({"start_time": ts, "generation": np.round(self._truth(ts) + noise)})

    def forecasts(self, publish_from: datetime, publish_to: datetime) -> pd.DataFrame:
        frames = []
        day = pd.Timestamp(publish_from).normalize()
        while day <= pd.Timestamp(publish_to):
            for hh, mm in self.PUBLISH_HOURS:
                pub = day + pd.Timedelta(hours=hh, minutes=mm)
                if not (publish_from <= pub <= publish_to):
                    continue
                first = pub.ceil("h") - pd.Timedelta(hours=6)  # WINDFOR also contains recent past hours
                targets = pd.date_range(first, pub + pd.Timedelta(hours=66), freq="h")
                horizon = np.clip((targets - pub).total_seconds().to_numpy() / 3600, 0, None)
                rng = np.random.default_rng(int(pub.timestamp()) % 2**32)
                # error std grows with horizon; persistent (autocorrelated) per publication
                walk = np.cumsum(rng.normal(0, 1, len(targets))) / np.sqrt(np.arange(1, len(targets) + 1))
                err = walk * (250 + 38 * horizon) + 180
                # Real WINDFOR over-forecasts metered wind by ~15% (unconstrained vs curtailed output)
                gen = np.clip(self._truth(targets) * 1.15 + err, 0, None)
                frames.append(pd.DataFrame({"start_time": targets, "publish_time": pub, "generation": np.round(gen)}))
            day += pd.Timedelta(days=1)
        if not frames:
            return pd.DataFrame(columns=FORECAST_COLS)
        return pd.concat(frames, ignore_index=True)[FORECAST_COLS]


_source: DataSource | None = None


def get_source() -> DataSource:
    global _source
    if _source is None:
        _source = SampleSource() if settings.data_source == "sample" else ElexonSource()
        log.info("Using data source: %s", _source.name)
    return _source
