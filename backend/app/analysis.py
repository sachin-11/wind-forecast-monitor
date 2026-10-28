"""Pure analysis functions (no I/O) - easy to unit test and reused by the notebook.

Key concept - *which forecast counts?*
For a target settlement time ``T`` we only ever use a forecast that was already
published at the moment a decision had to be made. Two rules are supported:

* ``horizon``  : latest forecast with ``publish_time <= T - h`` (h = 0..48 hours)
* ``decision`` : latest forecast published before the day-ahead decision cut-off,
                 i.e. ``D-1 @ HH:MM Europe/London`` for delivery day ``D``.

Errors are defined as ``forecast - actual`` (positive = over-forecast, i.e. the
trader would have bought too little power).
"""

from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd

DEFAULT_HORIZONS = [0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48]


# --------------------------------------------------------------------------- cut-offs
def horizon_cutoffs(targets: pd.Series, horizon_h: float) -> pd.Series:
    return targets - pd.Timedelta(hours=horizon_h)


def decision_cutoffs(targets: pd.Series, cutoff_local: str = "09:00", tz: str = "Europe/London") -> pd.Series:
    """Cut-off = previous local day at ``cutoff_local`` (DST-aware)."""
    hh, mm = (int(x) for x in cutoff_local.split(":"))
    local_day = targets.dt.tz_convert(tz).dt.normalize()  # local midnight of delivery day
    prev_day = local_day - pd.Timedelta(days=1)
    naive = prev_day.dt.tz_localize(None) + pd.Timedelta(hours=hh, minutes=mm)
    return naive.dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")


# --------------------------------------------------------------------------- selection
def select_forecasts(forecasts: pd.DataFrame, targets: pd.Series, cutoffs: pd.Series, max_lookback_h: float = 72) -> pd.DataFrame:
    """For each target pick the most recent forecast published at/before its cut-off.

    Uses ``merge_asof`` grouped by target time -> O(n log n), no python loops.
    Returns: start_time, cutoff, publish_time, forecast (NaN when nothing qualifies).
    """
    left = pd.DataFrame({"start_time": targets.values, "cutoff": cutoffs.values})
    left["start_time"] = pd.to_datetime(left.start_time, utc=True)
    left["cutoff"] = pd.to_datetime(left.cutoff, utc=True)
    if forecasts.empty:
        return left.assign(publish_time=pd.NaT, forecast=np.nan)

    right = forecasts.rename(columns={"generation": "forecast"})
    # A forecast for a time already in the past is not a forecast - ignore negative horizons.
    right = right[right.publish_time <= right.start_time]

    left_sorted = left.dropna(subset=["cutoff"]).sort_values("cutoff")
    right_sorted = right.sort_values("publish_time")
    merged = pd.merge_asof(
        left_sorted,
        right_sorted,
        left_on="cutoff",
        right_on="publish_time",
        by="start_time",
        direction="backward",
    )
    too_old = (merged.start_time - merged.publish_time) > pd.Timedelta(hours=max_lookback_h)
    merged.loc[too_old, ["publish_time", "forecast"]] = [pd.NaT, np.nan]
    out = left[["start_time"]].merge(merged, on="start_time", how="left")
    return out.sort_values("start_time").reset_index(drop=True)


def build_comparison(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
    mode: str = "horizon",
    horizon_h: float = 4,
    cutoff_local: str = "09:00",
    tz: str = "Europe/London",
    max_lookback_h: float = 72,
) -> pd.DataFrame:
    """Join actuals with the forecast that would have been used.

    Forecasts are hourly while actuals are half-hourly, so the joined frame is on the
    hourly grid (the :30 actual has no matching forecast and is excluded from metrics).
    Returns: start_time, actual, forecast, publish_time, cutoff, lead_h, error
    """
    a = actuals.rename(columns={"generation": "actual"})
    targets = a.loc[a.start_time.dt.minute == 0, "start_time"].reset_index(drop=True)
    if mode == "decision":
        cut = decision_cutoffs(targets, cutoff_local, tz)
    elif mode == "horizon":
        cut = horizon_cutoffs(targets, horizon_h)
    else:
        raise ValueError(f"unknown mode: {mode}")

    sel = select_forecasts(forecasts, targets, cut, max_lookback_h)
    df = a.merge(sel[["start_time", "cutoff", "publish_time", "forecast"]], on="start_time", how="inner")
    df = df.dropna(subset=["forecast"])  # targets with no eligible forecast are not scored
    df["lead_h"] = (df.start_time - df.publish_time).dt.total_seconds() / 3600
    df["error"] = df.forecast - df.actual
    return df.sort_values("start_time").reset_index(drop=True)


# --------------------------------------------------------------------------- bias correction
def add_scale_correction(df: pd.DataFrame, window_days: float = 14, min_points: int = 48) -> pd.DataFrame:
    """Add a causal, self-calibrating correction of the forecast.

    For every row the forecast is multiplied by ``k = sum(actual) / sum(forecast)`` over the
    scored hours of the previous ``window_days`` whose actuals were already known at that
    row's decision ``cutoff`` (start_time + 1h <= cutoff). No future information is used, so
    the corrected accuracy is a fair back-test of what a trader could have done.

    Adds: scale, forecast_corrected, error_corrected
    """
    d = df.sort_values("start_time").reset_index(drop=True)
    if d.empty:
        return d.assign(scale=[], forecast_corrected=[], error_corrected=[])
    t = d.start_time.to_numpy(dtype="datetime64[ns]")
    known_until = (d.cutoff - pd.Timedelta(hours=1)).to_numpy(dtype="datetime64[ns]")
    since = (d.cutoff - pd.Timedelta(hours=1) - pd.Timedelta(days=window_days)).to_numpy(dtype="datetime64[ns]")
    hi = np.searchsorted(t, known_until, side="right")
    lo = np.searchsorted(t, since, side="left")
    ca = np.concatenate([[0.0], np.cumsum(d.actual.to_numpy())])
    cf = np.concatenate([[0.0], np.cumsum(d.forecast.to_numpy())])
    sa, sf, cnt = ca[hi] - ca[lo], cf[hi] - cf[lo], hi - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.where((cnt >= min_points) & (sf > 0), sa / sf, 1.0)
    d["scale"] = k
    d["forecast_corrected"] = d.forecast * k
    d["error_corrected"] = d.forecast_corrected - d.actual
    return d


def corrected_view(df: pd.DataFrame) -> pd.DataFrame:
    """Frame where ``forecast``/``error`` are the corrected values (for reuse of metric helpers)."""
    return df.assign(forecast=df.forecast_corrected, error=df.error_corrected)


def trailing_residual_quantiles(df: pd.DataFrame, cutoff: pd.Timestamp, window_days: float = 14) -> dict:
    """Quantiles of (actual - corrected forecast) over hours known before ``cutoff`` - causal band."""
    hist = df[(df.start_time <= cutoff - pd.Timedelta(hours=1)) & (df.start_time > cutoff - pd.Timedelta(days=window_days))]
    return error_quantiles(corrected_view(hist)) if len(hist) else {}


# --------------------------------------------------------------------------- metrics
def error_metrics(df: pd.DataFrame) -> dict:
    """Summary accuracy statistics on rows that have both actual and forecast."""
    d = df.dropna(subset=["forecast", "actual"])
    n = len(d)
    if n == 0:
        return {"n": 0}
    e = d.error.to_numpy()
    ae = np.abs(e)
    mean_actual = float(d.actual.mean())
    return {
        "n": n,
        "mae": float(ae.mean()),
        "rmse": float(np.sqrt((e**2).mean())),
        "bias": float(e.mean()),  # >0 => forecasts too high on average
        "median_ae": float(np.median(ae)),
        "p90_ae": float(np.quantile(ae, 0.90)),
        "p99_ae": float(np.quantile(ae, 0.99)),
        "max_ae": float(ae.max()),
        "nmae_pct": float(ae.mean() / mean_actual * 100) if mean_actual else None,
        "mean_actual": mean_actual,
        "mean_forecast": float(d.forecast.mean()),
        # Over-forecast (forecast > actual) means LESS wind than planned -> extra purchase
        # needed. Its 90th/95th percentile is a data-driven safety margin for buying.
        "over_forecast_p90": float(np.quantile(e, 0.90)),
        "over_forecast_p95": float(np.quantile(e, 0.95)),
        "under_forecast_p90": float(np.quantile(-e, 0.90)),  # more wind than planned
        "pct_within_1gw": float((ae <= 1000).mean() * 100),
        "corr": float(np.corrcoef(d.actual, d.forecast)[0, 1]) if n > 2 else None,
        "mean_lead_h": float(d.lead_h.mean()) if "lead_h" in d else None,
    }


def scored(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
    start: pd.Timestamp | datetime | None = None,
    end: pd.Timestamp | datetime | None = None,
    mode: str = "horizon",
    horizon_h: float = 4,
    cutoff_local: str = "09:00",
    tz: str = "Europe/London",
    correction_days: float = 14,
) -> pd.DataFrame:
    """Comparison + causal correction, trimmed to [start, end).

    ``actuals``/``forecasts`` should include ``correction_days`` of history before
    ``start`` so the correction is warmed up on the first day of the window.
    """
    df = add_scale_correction(build_comparison(actuals, forecasts, mode, horizon_h, cutoff_local, tz), correction_days)
    if start is not None:
        df = df[df.start_time >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.start_time < pd.Timestamp(end)]
    return df.reset_index(drop=True)


def horizon_curve(actuals: pd.DataFrame, forecasts: pd.DataFrame, start=None, end=None, horizons=DEFAULT_HORIZONS) -> list[dict]:
    rows = []
    for h in horizons:
        df = scored(actuals, forecasts, start, end, "horizon", h)
        m = error_metrics(df)
        if m.get("n"):
            mc = error_metrics(corrected_view(df))
            rows.append(
                {
                    "horizon_h": h,
                    **{k: m[k] for k in ("n", "mae", "rmse", "bias", "p90_ae", "nmae_pct")},
                    "mae_corrected": mc["mae"],
                    "bias_corrected": mc["bias"],
                }
            )
    return rows


def hour_of_day_profile(df: pd.DataFrame, tz: str = "Europe/London") -> list[dict]:
    d = df.dropna(subset=["forecast"]).copy()
    if d.empty:
        return []
    d["hour"] = d.start_time.dt.tz_convert(tz).dt.hour
    d["ae"] = d.error.abs()
    g = d.groupby("hour").agg(mae=("ae", "mean"), bias=("error", "mean"), n=("ae", "size")).reset_index()
    return g.to_dict(orient="records")


def daily_metrics(df: pd.DataFrame, tz: str = "Europe/London") -> list[dict]:
    d = df.dropna(subset=["forecast"]).copy()
    if d.empty:
        return []
    d["date"] = d.start_time.dt.tz_convert(tz).dt.strftime("%Y-%m-%d")
    d["ae"] = d.error.abs()
    g = d.groupby("date").agg(
        mae=("ae", "mean"),
        bias=("error", "mean"),
        mean_actual=("actual", "mean"),
        mean_forecast=("forecast", "mean"),
        n=("ae", "size"),
    )
    return g.reset_index().to_dict(orient="records")


def error_histogram(df: pd.DataFrame, bin_mw: int = 500) -> list[dict]:
    e = df.error.dropna().to_numpy()
    if len(e) == 0:
        return []
    lo = np.floor(e.min() / bin_mw) * bin_mw
    hi = np.ceil(e.max() / bin_mw) * bin_mw + bin_mw
    counts, edges = np.histogram(e, bins=np.arange(lo, hi + 1, bin_mw))
    return [{"from": float(edges[i]), "to": float(edges[i + 1]), "count": int(c)} for i, c in enumerate(counts)]


def worst_misses(df: pd.DataFrame, k: int = 5) -> list[dict]:
    d = df.dropna(subset=["forecast"])
    if d.empty:
        return []
    top = d.reindex(d.error.abs().sort_values(ascending=False).index).head(k)
    return records(top)


def error_quantiles(df: pd.DataFrame) -> dict:
    """Empirical quantiles of (actual - forecast) used to draw an uncertainty band."""
    r = (df.actual - df.forecast).dropna().to_numpy()
    if len(r) == 0:
        return {}
    return {f"p{q}": float(np.quantile(r, q / 100)) for q in (5, 10, 25, 50, 75, 90, 95)}


# --------------------------------------------------------------------------- helpers
def records(df: pd.DataFrame) -> list[dict]:
    """JSON friendly records: ISO timestamps, NaN -> None."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out = out.astype(object).where(pd.notna(out), None)
    return out.to_dict(orient="records")


def clamp_window(start: datetime, end: datetime, lo: datetime, hi: datetime) -> tuple[datetime, datetime]:
    s, e = max(start, lo), min(end, hi)
    if s >= e:
        raise ValueError("Selected range is outside the supported window")
    return s, e


def parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))
