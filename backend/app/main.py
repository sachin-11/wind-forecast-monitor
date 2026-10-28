"""FastAPI application - thin HTTP layer over ``analysis`` + ``data_sources``."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from . import analysis as an
from .config import settings
from .data_sources import DataSourceError, get_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Wind Forecast Monitor API",
    version="1.0.0",
    description="Compares UK national wind generation forecasts (BMRS WINDFOR) with actual "
    "generation (BMRS FUELHH) to support day-ahead purchase decisions.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET"], allow_headers=["*"])

Mode = Literal["horizon", "decision"]


# --------------------------------------------------------------------------- helpers
def _window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    start = (start or settings.window_start).astimezone(UTC)
    end = (end or settings.window_end).astimezone(UTC)
    try:
        return an.clamp_window(start, end, settings.window_start, settings.window_end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _load(start: datetime, end: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Actuals + forecasts for [start, end) **plus** history for warming up the correction."""
    src = get_source()
    hist_start = start - timedelta(days=settings.correction_days + 1)
    try:
        actuals = src.actuals(hist_start, end)
        # One cached call covering the whole window (+history, +max lead) - sliced in memory.
        pub_from = settings.window_start - timedelta(days=settings.correction_days + 1, hours=settings.max_lookback_h)
        forecasts = src.forecasts(pub_from, settings.window_end)
    except DataSourceError as exc:
        raise HTTPException(502, str(exc)) from exc
    forecasts = forecasts[(forecasts.start_time >= hist_start) & (forecasts.start_time < end)]
    return actuals, forecasts


def _scored(actuals, forecasts, start, end, mode: Mode, horizon_h: float = 0) -> pd.DataFrame:
    return an.scored(
        actuals,
        forecasts,
        start,
        end,
        mode,
        horizon_h,
        settings.decision_cutoff_local,
        settings.local_tz,
        settings.correction_days,
    )


StartQ = Query(None, description="UTC start (inclusive), defaults to 2026-01-01")
EndQ = Query(None, description="UTC end (exclusive), defaults to 2026-02-01")
ModeQ = Query("horizon", description="'horizon' = fixed lead time, 'decision' = day-ahead cut-off")
HorizonQ = Query(4, ge=0, le=48, description="Minimum forecast lead time in hours (mode=horizon)")


def _ts(t: pd.Timestamp) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    return {"status": "ok", "data_source": get_source().name}


@app.get("/api/meta")
def meta():
    return {
        "window_start": settings.window_start.isoformat().replace("+00:00", "Z"),
        "window_end": settings.window_end.isoformat().replace("+00:00", "Z"),
        "max_horizon_h": settings.max_horizon_h,
        "decision_cutoff_local": settings.decision_cutoff_local,
        "correction_days": settings.correction_days,
        "timezone": settings.local_tz,
        "data_source": get_source().name,
        "sources": {
            "actuals": "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream",
            "forecasts": "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream",
        },
    }


@app.get("/api/series")
def series(start: datetime | None = StartQ, end: datetime | None = EndQ, mode: Mode = ModeQ, horizon_h: float = HorizonQ):
    """Time series for the main chart: half-hourly actuals + the applicable hourly forecast."""
    s, e = _window(start, end)
    actuals, forecasts = _load(s, e)
    df = _scored(actuals, forecasts, s, e, mode, horizon_h)
    in_window = actuals[(actuals.start_time >= s) & (actuals.start_time < e)]
    cols = ["start_time", "forecast", "forecast_corrected", "publish_time", "lead_h", "error"]
    merged = in_window.rename(columns={"generation": "actual"}).merge(df[cols], on="start_time", how="left")
    return {
        "mode": mode,
        "horizon_h": horizon_h,
        "points": an.records(merged),
        "metrics": an.error_metrics(df),
        "metrics_corrected": an.error_metrics(an.corrected_view(df)),
    }


@app.get("/api/analysis")
def analysis_endpoint(
    start: datetime | None = StartQ, end: datetime | None = EndQ, mode: Mode = ModeQ, horizon_h: float = HorizonQ
):
    """Everything the 'Accuracy' tab needs in a single round-trip."""
    s, e = _window(start, end)
    actuals, forecasts = _load(s, e)
    df = _scored(actuals, forecasts, s, e, mode, horizon_h)
    dec = _scored(actuals, forecasts, s, e, "decision")
    return {
        "mode": mode,
        "horizon_h": horizon_h,
        "metrics": an.error_metrics(df),
        "metrics_corrected": an.error_metrics(an.corrected_view(df)),
        "horizon_curve": an.horizon_curve(actuals, forecasts, s, e),
        "decision_metrics": an.error_metrics(dec),
        "decision_metrics_corrected": an.error_metrics(an.corrected_view(dec)),
        "hour_of_day": an.hour_of_day_profile(df, settings.local_tz),
        "daily": an.daily_metrics(df, settings.local_tz),
        "histogram": an.error_histogram(df),
        "quantiles": an.error_quantiles(df),
        "worst_misses": an.worst_misses(df[["start_time", "actual", "forecast", "publish_time", "lead_h", "error"]]),
    }


@app.get("/api/day-ahead")
def day_ahead(delivery_date: str = Query(..., description="Delivery day (UK local) YYYY-MM-DD")):
    """Replay the purchase decision for ``delivery_date``.

    Everything shown is causal: the forecast published before the D-1 cut-off, the
    corrected forecast and an uncertainty band calibrated only on the previous
    ``correction_days`` of *known* errors. Actuals are returned for the after-the-fact view.
    """
    try:
        day = pd.Timestamp(delivery_date).tz_localize(settings.local_tz)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "delivery_date must be YYYY-MM-DD") from exc
    s = day.tz_convert("UTC").to_pydatetime()
    e = (day + pd.Timedelta(days=1)).tz_convert("UTC").to_pydatetime()
    if s < settings.window_start or e > settings.window_end + timedelta(hours=1):
        raise HTTPException(422, "delivery_date outside supported window")

    actuals, forecasts = _load(s, e)
    full = _scored(actuals, forecasts, None, e, "decision")
    cutoff = an.decision_cutoffs(pd.Series([pd.Timestamp(s)]), settings.decision_cutoff_local, settings.local_tz).iloc[0]
    day_df = full[full.start_time >= pd.Timestamp(s)].copy()
    q = an.trailing_residual_quantiles(full, cutoff, settings.correction_days)
    if q and not day_df.empty:
        day_df["p10"] = (day_df.forecast_corrected + q["p10"]).clip(lower=0)
        day_df["p90"] = day_df.forecast_corrected + q["p90"]
    has = not day_df.empty
    cols = [
        c
        for c in [
            "start_time",
            "actual",
            "forecast",
            "forecast_corrected",
            "p10",
            "p90",
            "publish_time",
            "lead_h",
            "error",
            "scale",
        ]
        if c in day_df
    ]
    return {
        "delivery_date": delivery_date,
        "cutoff_utc": _ts(cutoff),
        "publish_time": _ts(day_df.publish_time.max()) if has else None,
        "scale": float(day_df.scale.iloc[0]) if has else None,
        "points": an.records(day_df[cols]),
        "band_quantiles": q,
        "metrics": an.error_metrics(day_df),
        "metrics_corrected": an.error_metrics(an.corrected_view(day_df)) if has else {"n": 0},
        # Hourly MW values -> MWh by summing over the hours of the day.
        "summary": {
            "forecast_mwh": float(day_df.forecast.sum()) if has else None,
            "corrected_mwh": float(day_df.forecast_corrected.sum()) if has else None,
            "p10_mwh": float(day_df.p10.sum()) if "p10" in day_df and has else None,
            "actual_mwh": float(day_df.actual.sum()) if has else None,
        },
    }
