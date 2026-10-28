import { useMemo, useState } from "react";
import { Bar, Brush, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Query } from "../api";
import { biasSentence, fmtDateTime, fmtDay, fmtTime, gw, mw, pct, signedMw } from "../format";
import type { SeriesPoint } from "../types";
import { useApi } from "../useApi";
import { Card, Insight, Kpi, Skeleton, Status } from "./ui";

const C = { actual: "var(--c-actual)", forecast: "var(--c-forecast)", over: "var(--c-over)", under: "var(--c-under)" };

function TooltipBody({ active, payload }: { active?: boolean; payload?: { payload: SeriesPoint }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tt">
      <div className="tt-title">{fmtDateTime(p.start_time)}</div>
      <div className="tt-row">
        <i style={{ background: C.actual }} /> Actual <b>{mw(p.actual)}</b>
      </div>
      <div className="tt-row">
        <i style={{ background: C.forecast }} /> Forecast <b>{mw(p.forecast)}</b>
      </div>
      {p.forecast_corrected != null && (
        <div className="tt-row">
          <i style={{ background: "var(--c-accent)" }} /> Corrected <b>{mw(p.forecast_corrected)}</b>
        </div>
      )}
      {p.forecast != null && (
        <>
          <div className="tt-row">
            Error <b>{signedMw(p.error)}</b>
          </div>
          <div className="tt-sub">
            Published {fmtDateTime(p.publish_time)} · {p.lead_h?.toFixed(1)}h ahead
          </div>
        </>
      )}
    </div>
  );
}

export function MonitorView({ query }: { query: Query }) {
  const { data, error, loading } = useApi((s) => api.series(query, s), [query.start, query.end, query.mode, query.horizonH]);
  const m = data?.metrics;
  const mc = data?.metrics_corrected;
  const [showCorrected, setShowCorrected] = useState(true);
  const gain = m?.mae && mc?.mae ? (1 - mc.mae / m.mae) * 100 : null;
  const pts = data?.points ?? [];
  // Hourly-only points for the error bars (forecasts are hourly)
  const errPts = useMemo(() => pts.filter((p) => p.error != null), [pts]);
  const label = query.mode === "horizon" ? `${query.horizonH}h-ahead` : "day-ahead";
  // One tick per UK day (midnight) when showing several days, otherwise hourly ticks.
  const dayTicks = useMemo(() => pts.filter((p) => p.start_time.endsWith("T00:00:00Z")).map((p) => p.start_time), [pts]);
  const multiDay = dayTicks.length > 1;
  const xFmt = multiDay ? fmtDay : fmtTime;
  const xTicks = multiDay ? dayTicks : undefined;

  return (
    <div className="stack">
      <Status loading={loading && !data} error={error} />
      <div className="kpis">
        <Kpi label="Mean absolute error" value={mw(m?.mae)} hint={`${pct(m?.nmae_pct)} of average output`} />
        <Kpi label="Bias (forecast − actual)" value={signedMw(m?.bias)} hint={m?.bias != null && m.bias > 0 ? "Over-forecasting wind" : "Under-forecasting wind"} tone={Math.abs(m?.bias ?? 0) > 300 ? "warn" : "good"} />
        <Kpi label="P90 absolute error" value={mw(m?.p90_ae)} hint="9 in 10 hours are within this" />
        <Kpi label="Hours within ±1 GW" value={pct(m?.pct_within_1gw, 0)} hint={`${m?.n ?? 0} hourly points scored`} />
        <Kpi label="Average wind output" value={gw(m?.mean_actual)} hint={`Forecast avg ${gw(m?.mean_forecast)}`} />
        <Kpi
          label="MAE with bias correction"
          value={mw(mc?.mae)}
          hint={gain != null ? `${gain >= 0 ? "▼" : "▲"} ${Math.abs(gain).toFixed(0)}% vs raw forecast` : undefined}
          tone={gain != null && gain > 5 ? "good" : undefined}
        />
      </div>

      <Card
        title="Actual vs forecast wind generation"
        subtitle={
          <>
            GB national wind (MW). Actuals every 30 min from <code>FUELHH</code>; forecast = latest <code>WINDFOR</code> {label} forecast. Drag the handles below to zoom.
          </>
        }
        actions={
          <div className="card-actions">
            {loading && data && <span className="badge">Updating…</span>}
            <label className="toggle">
              <input type="checkbox" checked={showCorrected} onChange={(e) => setShowCorrected(e.target.checked)} /> Bias-corrected forecast
            </label>
          </div>
        }
      >
        {!data ? (
          <Skeleton height={380} />
        ) : (
          <ResponsiveContainer width="100%" height={380}>
            <ComposedChart data={pts} syncId="mon" margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="start_time" ticks={xTicks} tickFormatter={xFmt} interval={multiDay ? 0 : "preserveStartEnd"} minTickGap={16} stroke="var(--axis)" fontSize={12} />
              <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)} GW`} stroke="var(--axis)" fontSize={12} width={56} />
              <Tooltip content={<TooltipBody />} />
              <Legend verticalAlign="top" height={28} iconType="plainline" />
              <Line name="Actual" type="monotone" dataKey="actual" stroke={C.actual} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line name={`Forecast (${label})`} type="monotone" dataKey="forecast" stroke={C.forecast} strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls isAnimationActive={false} />
              {showCorrected && (
                <Line name="Bias-corrected forecast" type="monotone" dataKey="forecast_corrected" stroke="var(--c-accent)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              )}
              <Brush dataKey="start_time" height={24} tickFormatter={fmtDateTime} stroke="var(--c-forecast)" travellerWidth={8} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </Card>

      <Card title="Forecast error by hour" subtitle="Red = forecast too high (less wind than planned → buy more). Green = forecast too low.">
        {!data ? (
          <Skeleton height={180} />
        ) : (
          <ResponsiveContainer width="100%" height={180}>
            <ComposedChart data={errPts} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="start_time" ticks={xTicks} tickFormatter={xFmt} interval={multiDay ? 0 : "preserveStartEnd"} minTickGap={16} stroke="var(--axis)" fontSize={12} />
              <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(1)}`} stroke="var(--axis)" fontSize={12} width={56} label={{ value: "GW", angle: -90, position: "insideLeft", fill: "var(--axis)", fontSize: 12 }} />
              <ReferenceLine y={0} stroke="var(--axis)" />
              <Tooltip content={<TooltipBody />} />
              <Bar dataKey="error" isAnimationActive={false}>
                {errPts.map((p) => (
                  <Cell key={p.start_time} fill={(p.error ?? 0) > 0 ? C.over : C.under} />
                ))}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </Card>

      {m && m.n > 0 && (
        <Insight>
          Using the <b>{label}</b> forecast, the typical miss is <b>{gw(m.mae)}</b> per hour ({pct(m.nmae_pct)} of average wind output). {biasSentence(m.bias)}{" "}
          {(m.over_forecast_p90 ?? 0) > 0 ? (
            <>
              To be covered against a wind shortfall in 9 out of 10 hours, plan for about <b>{mw(m.over_forecast_p90)}</b> less wind than forecast.
            </>
          ) : (
            <>In this period the forecast rarely over-stated wind, so little extra cover was needed.</>
          )}
          {gain != null && gain > 5 && (
            <>
              {" "}
              A simple self-calibrating correction (scaling by the actual/forecast ratio of the previous 14 days, using only data known at decision time) cuts the typical miss to{" "}
              <b>{gw(mc?.mae)}</b> - <b>{gain.toFixed(0)}% better</b>.
            </>
          )}
        </Insight>
      )}
    </div>
  );
}
