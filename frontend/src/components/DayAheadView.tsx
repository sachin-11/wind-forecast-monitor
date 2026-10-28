import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { fmtDateTime, fmtTime, gwh, mw, signedMw } from "../format";
import type { DayAheadPoint } from "../types";
import { useApi } from "../useApi";
import { Card, Insight, Kpi, Skeleton, Status } from "./ui";

function shift(date: string, days: number) {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function DayTooltip({ active, payload }: { active?: boolean; payload?: { payload: DayAheadPoint }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tt">
      <div className="tt-title">{fmtTime(p.start_time)} UK</div>
      <div className="tt-row">
        Raw forecast <b>{mw(p.forecast)}</b>
      </div>
      <div className="tt-row">
        Corrected plan <b>{mw(p.forecast_corrected)}</b>
      </div>
      <div className="tt-row">
        Likely range <b>
          {mw(p.p10)} – {mw(p.p90)}
        </b>
      </div>
      {p.actual != null && (
        <div className="tt-row">
          Actual <b>{mw(p.actual)}</b>
        </div>
      )}
    </div>
  );
}

export function DayAheadView({ min, max, cutoff }: { min: string; max: string; cutoff: string }) {
  const [date, setDate] = useState("2026-01-15");
  const [reveal, setReveal] = useState(true);
  const { data, error, loading } = useApi((s) => api.dayAhead(date, s), [date]);

  const pts = useMemo(
    () => (data?.points ?? []).map((p) => ({ ...p, band: p.p10 != null && p.p90 != null ? [p.p10, p.p90] : null })),
    [data],
  );
  const s = data?.summary;
  const plan = s?.corrected_mwh ?? null; // central planning value = bias-corrected forecast
  const buffer = plan != null && s?.p10_mwh != null ? plan - s.p10_mwh : null;
  const shortfall = plan != null && s?.actual_mwh != null ? plan - s.actual_mwh : null; // >0 => less wind than planned
  const covered = shortfall != null && buffer != null ? shortfall <= buffer : null;
  const hours = Math.max(1, data?.points.length ?? 1);

  return (
    <div className="stack">
      <div className="toolbar">
        <button className="chip" disabled={date <= min} onClick={() => setDate(shift(date, -1))} aria-label="Previous day">
          ←
        </button>
        <input type="date" min={min} max={max} value={date} onChange={(e) => e.target.value && setDate(e.target.value)} aria-label="Delivery day" />
        <button className="chip" disabled={date >= max} onClick={() => setDate(shift(date, 1))} aria-label="Next day">
          →
        </button>
        <span className="muted">
          Decision made <b>{data ? fmtDateTime(data.cutoff_utc) : "–"}</b> (D-1, {cutoff} UK) using the forecast published <b>{fmtDateTime(data?.publish_time)}</b>
        </span>
        <label className="toggle">
          <input type="checkbox" checked={reveal} onChange={(e) => setReveal(e.target.checked)} /> Show what actually happened
        </label>
      </div>
      <Status loading={loading && !data} error={error} />

      <div className="kpis">
        <Kpi label="Raw forecast (WINDFOR)" value={gwh(s?.forecast_mwh)} hint="Sum of hourly forecast for the day" />
        <Kpi label="Bias-corrected plan" value={gwh(plan)} hint={data?.scale ? `Forecast × ${data.scale.toFixed(2)} (trailing 14-day ratio)` : undefined} />
        <Kpi label="Low case (P10)" value={gwh(s?.p10_mwh)} hint="Sum of hourly P10s (conservative)" />
        <Kpi label="Suggested extra cover" value={gwh(buffer)} hint="Energy to secure vs. the plan" tone="warn" />
        {reveal && (
          <Kpi
            label="Actual wind energy"
            value={gwh(s?.actual_mwh)}
            hint={shortfall != null ? `${shortfall > 0 ? "Short" : "Long"} by ${gwh(Math.abs(shortfall))} vs plan` : undefined}
            tone={covered == null ? undefined : covered ? "good" : "bad"}
          />
        )}
      </div>

      <Card title={`Day-ahead view for ${date}`} subtitle="Dashed = raw forecast · teal = bias-corrected plan · band = P10–P90 range, calibrated only on errors known before the decision">
        {!data ? (
          <Skeleton height={360} />
        ) : (
          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart data={pts} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="start_time" tickFormatter={fmtTime} stroke="var(--axis)" fontSize={12} interval={2} />
              <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)} GW`} stroke="var(--axis)" fontSize={12} width={56} />
              <Tooltip content={<DayTooltip />} />
              <Legend verticalAlign="top" height={28} />
              <Area name="P10–P90 range" dataKey="band" stroke="none" fill="var(--c-accent)" fillOpacity={0.14} isAnimationActive={false} />
              <Line name="Raw forecast" dataKey="forecast" stroke="var(--c-forecast)" strokeWidth={2} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
              <Line name="Bias-corrected plan" dataKey="forecast_corrected" stroke="var(--c-accent)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
              {reveal && <Line name="Actual" dataKey="actual" stroke="var(--c-actual)" strokeWidth={2.5} dot={false} isAnimationActive={false} />}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </Card>

      {data && buffer != null && (
        <Insight>
          At the cut-off the raw forecast expected <b>{gwh(s?.forecast_mwh)}</b> of wind for {date}. Over the previous 14 days wind delivered{" "}
          <b>{data.scale != null ? `${(data.scale * 100).toFixed(0)}%` : "–"}</b> of what was forecast, so the corrected plan is <b>{gwh(plan)}</b>. Each hour has only a 1-in-10
          chance of falling below its P10, giving a conservative low case of <b>{gwh(s?.p10_mwh)}</b>; securing about <b>{gwh(buffer)}</b> of extra cover (or flexible capacity)
          protects against a shortfall.
          {reveal && shortfall != null && (
            <>
              {" "}
              Outcome: wind delivered <b>{gwh(s?.actual_mwh)}</b> ({signedMw(-shortfall / hours)} per hour vs plan), so the cover{" "}
              {covered ? "would have been sufficient" : "would not have been enough on this day"}.
            </>
          )}
        </Insight>
      )}
    </div>
  );
}
