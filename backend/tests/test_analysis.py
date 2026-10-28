import numpy as np
import pandas as pd
import pytest

from app import analysis as an
from app.data_sources import normalise_actuals, normalise_forecasts


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


@pytest.fixture
def forecasts():
    # Three publications forecasting 12:00; one forecasting a time already in the past.
    return pd.DataFrame(
        {
            "start_time": [ts("2026-01-10 12:00")] * 3 + [ts("2026-01-10 08:00")],
            "publish_time": [ts("2026-01-09 22:30"), ts("2026-01-10 07:30"), ts("2026-01-10 11:30"), ts("2026-01-10 09:30")],
            "generation": [1000.0, 1100.0, 1200.0, 999.0],
        }
    )


@pytest.fixture
def actuals():
    return pd.DataFrame(
        {
            "start_time": [ts("2026-01-10 08:00"), ts("2026-01-10 12:00"), ts("2026-01-10 12:30")],
            "generation": [900.0, 1050.0, 1060.0],
        }
    )


@pytest.mark.parametrize(
    "horizon,expected_publish,expected_value",
    [
        (0, "2026-01-10 11:30", 1200.0),
        (1, "2026-01-10 07:30", 1100.0),
        (4, "2026-01-10 07:30", 1100.0),
        (5, "2026-01-09 22:30", 1000.0),
    ],
)
def test_horizon_picks_latest_eligible_forecast(forecasts, horizon, expected_publish, expected_value):
    targets = pd.Series([ts("2026-01-10 12:00")])
    out = an.select_forecasts(forecasts, targets, an.horizon_cutoffs(targets, horizon))
    assert out.publish_time.iloc[0] == ts(expected_publish)
    assert out.forecast.iloc[0] == expected_value


def test_no_forecast_old_enough_returns_nan(forecasts):
    targets = pd.Series([ts("2026-01-10 12:00")])
    out = an.select_forecasts(forecasts, targets, an.horizon_cutoffs(targets, 20))
    assert np.isnan(out.forecast.iloc[0])


def test_negative_horizon_forecasts_are_ignored(forecasts):
    # 08:00 was "forecast" at 09:30 (after the fact) -> must not be used
    targets = pd.Series([ts("2026-01-10 08:00")])
    out = an.select_forecasts(forecasts, targets, an.horizon_cutoffs(targets, 0))
    assert np.isnan(out.forecast.iloc[0])


def test_lookback_limit(forecasts):
    targets = pd.Series([ts("2026-01-10 12:00")])
    out = an.select_forecasts(forecasts, targets, an.horizon_cutoffs(targets, 5), max_lookback_h=6)
    assert np.isnan(out.forecast.iloc[0])


def test_decision_cutoff_is_previous_local_day_dst_aware():
    winter = an.decision_cutoffs(pd.Series([ts("2026-01-15 13:00")]), "09:00").iloc[0]
    summer = an.decision_cutoffs(pd.Series([ts("2026-07-15 13:00")]), "09:00").iloc[0]
    assert winter == ts("2026-01-14 09:00")  # GMT == UTC
    assert summer == ts("2026-07-14 08:00")  # BST = UTC+1
    # 23:30 UTC on 31 Jul is already 1 Aug in London -> cut-off 31 Jul 09:00 BST
    late = an.decision_cutoffs(pd.Series([ts("2026-07-31 23:30")]), "09:00").iloc[0]
    assert late == ts("2026-07-31 08:00")


def test_build_comparison_uses_hourly_grid_and_error_sign(actuals, forecasts):
    df = an.build_comparison(actuals, forecasts, "horizon", 1)
    assert list(df.start_time) == [ts("2026-01-10 12:00")]  # 08:00 has no valid forecast, 12:30 not hourly
    row = df.iloc[0]
    assert row.forecast == 1100.0 and row.actual == 1050.0
    assert row.error == 50.0  # forecast - actual
    assert row.lead_h == pytest.approx(4.5)


def test_error_metrics_known_values():
    df = pd.DataFrame({"actual": [100.0, 200.0, 300.0, 400.0], "forecast": [110.0, 190.0, 330.0, 400.0], "lead_h": [1, 1, 1, 1]})
    df["error"] = df.forecast - df.actual
    m = an.error_metrics(df)
    assert m["n"] == 4
    assert m["mae"] == pytest.approx(12.5)
    assert m["bias"] == pytest.approx(7.5)
    assert m["rmse"] == pytest.approx(np.sqrt((100 + 100 + 900) / 4))
    assert m["nmae_pct"] == pytest.approx(12.5 / 250 * 100)


def test_error_metrics_empty():
    assert an.error_metrics(pd.DataFrame(columns=["actual", "forecast", "error"])) == {"n": 0}


def test_histogram_counts_everything():
    df = pd.DataFrame({"error": [-600.0, -10.0, 20.0, 499.0, 1200.0]})
    h = an.error_histogram(df, 500)
    assert sum(b["count"] for b in h) == 5


def test_normalisers_dedupe_and_filter():
    a = normalise_actuals(
        [
            {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2026-01-01T00:30:00Z", "fuelType": "WIND", "generation": 1},
            {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2026-01-01T01:00:00Z", "fuelType": "WIND", "generation": 2},
            {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2026-01-01T01:00:00Z", "fuelType": "CCGT", "generation": 9},
        ]
    )
    assert len(a) == 1 and a.generation.iloc[0] == 2
    f = normalise_forecasts([{"startTime": "2026-01-01T03:00:00Z", "publishTime": "2025-12-31T22:30:00Z", "generation": 5}])
    assert f.publish_time.iloc[0] == ts("2025-12-31 22:30")


def _hourly_frame(days: int, ratio: float, cutoff_lag_h: float = 24) -> pd.DataFrame:
    t = pd.date_range("2026-01-01", periods=days * 24, freq="h", tz="UTC")
    actual = np.full(len(t), 1000.0)
    return pd.DataFrame(
        {
            "start_time": t,
            "actual": actual,
            "forecast": actual * ratio,
            "cutoff": t - pd.Timedelta(hours=cutoff_lag_h),
        }
    )


def test_scale_correction_learns_systematic_bias():
    df = an.add_scale_correction(_hourly_frame(20, ratio=1.25), window_days=14, min_points=48)
    late = df[df.start_time >= ts("2026-01-10")]
    assert late.scale.round(6).eq(0.8).all()  # 1000 / 1250
    assert late.error_corrected.abs().max() < 1e-6


def test_scale_correction_is_causal_and_needs_warmup():
    df = _hourly_frame(5, ratio=1.25)
    # Poison the future: if the correction peeked ahead, early rows would change.
    df.loc[df.start_time >= ts("2026-01-04"), "actual"] = 99_999.0
    out = an.add_scale_correction(df, window_days=14, min_points=48)
    early = out[out.start_time < ts("2026-01-03 01:00")]
    assert (early.scale == 1.0).all()  # not enough known history yet -> no correction
    # Day 4 rows have poisoned actuals themselves, but their cut-off (24h earlier) only
    # sees clean history -> the learnt scale must be exactly 1000/1250.
    day4 = out[(out.start_time >= ts("2026-01-04")) & (out.start_time < ts("2026-01-05"))]
    assert np.allclose(day4.scale, 0.8)
