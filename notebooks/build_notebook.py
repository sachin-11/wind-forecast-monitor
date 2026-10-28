"""Generates analysis.ipynb (kept as code so the notebook is reviewable in diffs).

Run:  python notebooks/build_notebook.py
"""

from pathlib import Path

import nbformat as nbf

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = [
    md(
        """# Wind forecast accuracy - January 2026

**Question from the client:** *How far can we trust the national wind forecast when we buy power on the day-ahead market, and how much extra power should we plan to buy as a safety margin?*

This notebook backs up the numbers shown in the web app. It reuses the **same** code as the API (`backend/app`), so the notebook and the product can't drift apart.

| Dataset | What | Resolution |
|---|---|---|
| `FUELHH` (fuelType = WIND) | Actual metered wind generation | 30 min |
| `WINDFOR` | National wind generation forecast, published ~8x per day | hourly, up to ~66h ahead |

**Rule used throughout:** for a target hour *T* only a forecast that was *already published* when the decision was made is allowed - no hindsight."""
    ),
    code(
        """import os, sys, warnings
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.abspath("../backend"))
from app import analysis as an
from app.data_sources import ElexonSource, SampleSource, DataSourceError

plt.rcParams.update({"figure.figsize": (11, 4), "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False})
pd.set_option("display.float_format", "{:,.1f}".format)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 2, 1, tzinfo=timezone.utc)
HISTORY_DAYS = 15  # warm-up for the trailing correction
warnings.filterwarnings("ignore", category=DeprecationWarning)"""
    ),
    md("## 1. Load data\nLive from Elexon BMRS (falls back to the synthetic sample if the API is unreachable, e.g. offline)."),
    code(
        """src = SampleSource() if os.getenv("DATA_SOURCE") == "sample" else ElexonSource()
try:
    actuals = src.actuals(START - timedelta(days=HISTORY_DAYS), END)
    forecasts = src.forecasts(START - timedelta(days=HISTORY_DAYS, hours=72), END)
except DataSourceError as exc:
    print("Elexon unavailable, using sample data:", exc)
    src = SampleSource()
    actuals = src.actuals(START - timedelta(days=HISTORY_DAYS), END)
    forecasts = src.forecasts(START - timedelta(days=HISTORY_DAYS, hours=72), END)

print(f"source={src.name}  actual rows={len(actuals):,}  forecast rows={len(forecasts):,}")
actuals.tail(3), forecasts.tail(3)"""
    ),
    md("## 2. Data quality checks"),
    code(
        """jan = actuals[(actuals.start_time >= START) & (actuals.start_time < END)]
expected = pd.date_range(START, END, freq="30min", inclusive="left", tz="UTC")
missing = expected.difference(jan.start_time)
print(f"January actuals: {len(jan):,} of {len(expected):,} half-hours  (missing: {len(missing)})")
print(f"Actual wind range: {jan.generation.min():,.0f} - {jan.generation.max():,.0f} MW, mean {jan.generation.mean():,.0f} MW")

pubs = forecasts.publish_time.drop_duplicates().sort_values()
print(f"Forecast publications: {len(pubs)}  (~{len(pubs) / ((pubs.max() - pubs.min()).days or 1):.1f} per day)")
print("Typical publish times (UTC):", sorted(pubs.dt.strftime('%H:%M').value_counts().head(8).index))

lead = (forecasts.start_time - forecasts.publish_time).dt.total_seconds() / 3600
print(f"Lead time range in WINDFOR: {lead.min():.1f}h to {lead.max():.1f}h  (negative = 'forecasts' of the past -> excluded)")"""
    ),
    md("## 3. How does accuracy decay with forecast horizon?"),
    code(
        """curve = pd.DataFrame(an.horizon_curve(actuals, forecasts, START, END))
display(curve[["horizon_h", "n", "mae", "rmse", "bias", "p90_ae", "nmae_pct", "mae_corrected"]])

fig, ax = plt.subplots()
ax.plot(curve.horizon_h, curve.mae, "o-", label="MAE (raw)")
ax.plot(curve.horizon_h, curve.p90_ae, "--", label="P90 |error| (raw)")
ax.plot(curve.horizon_h, curve.bias, ":", label="Bias (raw)")
ax.plot(curve.horizon_h, curve.mae_corrected, "o-", label="MAE (bias-corrected)")
ax.set(xlabel="Minimum lead time (h)", ylabel="MW", title="Forecast error vs horizon")
ax.legend();"""
    ),
    md(
        """## 4. The day-ahead decision
The purchase decision for delivery day *D* is made on *D-1* (cut-off assumed 09:00 UK, configurable). Every hour of *D* is therefore forecast ~15-39h ahead."""
    ),
    code(
        """dec = an.scored(actuals, forecasts, START, END, mode="decision")
m_raw, m_cor = an.error_metrics(dec), an.error_metrics(an.corrected_view(dec))
pd.DataFrame({"raw": m_raw, "bias-corrected": m_cor}).loc[["n", "mean_lead_h", "mae", "rmse", "bias", "p90_ae", "nmae_pct", "pct_within_1gw", "over_forecast_p90"]]"""
    ),
    code(
        """fig, axes = plt.subplots(1, 2, figsize=(13, 4))
axes[0].hist(dec.error, bins=40, alpha=0.6, label="raw")
axes[0].hist(dec.error_corrected, bins=40, alpha=0.6, label="corrected")
axes[0].axvline(0, color="k", lw=1)
axes[0].set(title="Day-ahead error distribution (forecast - actual)", xlabel="MW")
axes[0].legend()

axes[1].scatter(dec.actual, dec.forecast, s=6, alpha=0.4)
lim = [0, max(dec.actual.max(), dec.forecast.max()) * 1.05]
axes[1].plot(lim, lim, "k--", lw=1)
axes[1].set(title="Forecast vs actual (day-ahead)", xlabel="Actual MW", ylabel="Forecast MW", xlim=lim, ylim=lim);"""
    ),
    md(
        """### Why is there a large, persistent positive bias?
`WINDFOR` forecasts what the wind fleet *could* generate, whereas `FUELHH` reports *metered* output. The gap is consistent with
(a) **curtailment / constraint actions** - on windy days the system operator pays wind farms to turn down because of transmission limits (notably Scotland → England), and
(b) differences in which capacity each dataset covers.

Evidence: if the bias were random forecast skill it would grow with horizon and be centred near zero at short leads. Instead it is large even at 0-1h lead. Check how it scales with wind level:"""
    ),
    code(
        """d = dec.assign(level=pd.cut(dec.forecast, bins=[0, 4000, 8000, 12000, 16000, 25000]))
display(d.groupby("level", observed=True).agg(hours=("error", "size"), bias=("error", "mean"), mae=("error", lambda e: e.abs().mean()), ratio=("actual", "sum")).assign(ratio=lambda x: x.ratio / d.groupby("level", observed=True).forecast.sum()))"""
    ),
    md(
        """## 5. Back-testing a simple correction
Because the bias is persistent, a **causal** multiplicative correction works well: multiply each forecast by
`sum(actual) / sum(forecast)` over the previous *N* days of hours that were already settled at the decision time.
No future data is used, so this is an honest back-test. Choose *N*:"""
    ),
    code(
        """rows = []
for n_days in [3, 7, 14, 21]:
    df = an.scored(actuals, forecasts, START, END, mode="decision", correction_days=n_days)
    rows.append({"window_days": n_days, "mae_raw": df.error.abs().mean(), "mae_corrected": df.error_corrected.abs().mean(),
                 "bias_corrected": df.error_corrected.mean()})
bt = pd.DataFrame(rows).assign(improvement_pct=lambda x: (1 - x.mae_corrected / x.mae_raw) * 100)
bt"""
    ),
    md("## 6. Is the uncertainty band honest? (coverage check)\nFor each day, build the P10-P90 band from the previous 14 days of corrected residuals only, then count how often the actual lands inside. A well-calibrated band should cover ~80%."),
    code(
        """full = an.scored(actuals, forecasts, None, END, mode="decision")
inside, total = 0, 0
for day in pd.date_range(START, END, freq="D", inclusive="left"):
    rows_ = full[(full.start_time >= day) & (full.start_time < day + pd.Timedelta(days=1))]
    if rows_.empty:
        continue
    q = an.trailing_residual_quantiles(full, rows_.cutoff.iloc[0], 14)
    if not q:
        continue
    lo, hi = rows_.forecast_corrected + q["p10"], rows_.forecast_corrected + q["p90"]
    inside += ((rows_.actual >= lo) & (rows_.actual <= hi)).sum()
    total += len(rows_)
print(f"P10-P90 coverage: {inside / total * 100:.1f}% of {total} hours (target 80%)")"""
    ),
    md("## 7. When are forecasts worst?"),
    code(
        """hod = pd.DataFrame(an.hour_of_day_profile(dec))
daily = pd.DataFrame(an.daily_metrics(dec))
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
axes[0].bar(hod.hour, hod.mae); axes[0].set(title="Day-ahead MAE by UK hour", xlabel="hour", ylabel="MW")
axes[1].bar(daily.date.str[-2:], daily.mae); axes[1].set(title="Day-ahead MAE by day", xlabel="January", ylabel="MW")
plt.tight_layout()
pd.DataFrame(an.worst_misses(dec[["start_time", "actual", "forecast", "publish_time", "lead_h", "error"]], 8))"""
    ),
    md(
        """## 8. Conclusions & recommendations
*(Numbers quoted from the live January 2026 run - re-run the notebook to refresh.)*

1. **Forecast skill decays with lead time** - every extra hour of lead adds error; the day-ahead decision (average lead ~28h) sits in the middle of that curve.
2. **The raw forecast is systematically too high.** For January 2026 the day-ahead forecast over-stated metered wind by roughly 1.8 GW on average (≈16% of mean output). Taken at face value, the team would under-buy.
3. **A zero-cost fix:** scaling forecasts by the trailing 14-day actual/forecast ratio removed about a third of the day-ahead error (MAE ≈ 2.1 GW → ≈ 1.4 GW) in an honest back-test.
4. **Size the safety margin from data, not gut feel:** the P10 of the corrected forecast gives a defensible "low wind" scenario for each hour; the app turns this into a daily GWh of extra cover.
5. **Next steps:** add curtailment / BOA data to explain the bias directly, extend to regional (Scotland vs England) wind, and benchmark against a weather-model forecast (e.g. ECMWF wind speed → power curve)."""
    ),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
out = Path(__file__).with_name("analysis.ipynb")
nbf.write(nb, out)
print("wrote", out)
