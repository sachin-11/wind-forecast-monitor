import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Query } from "../api";
import { biasSentence, fmtDateTime, gw, mw, pct, signedMw } from "../format";
import { useApi } from "../useApi";
import { Card, Insight, Kpi, Skeleton, Status } from "./ui";

const kGW = (v: number) => (v / 1000).toFixed(1);

export function AccuracyView({ query }: { query: Query }) {
  const { data, error, loading } = useApi((s) => api.analysis(query, s), [query.start, query.end, query.mode, query.horizonH]);
  const label = query.mode === "horizon" ? `${query.horizonH}h-ahead` : "day-ahead";
  const curve = data?.horizon_curve ?? [];
  const first = curve[0];
  const last = curve[curve.length - 1];
  const slope = first && last && last.horizon_h > first.horizon_h ? (last.mae - first.mae) / (last.horizon_h - first.horizon_h) : null;
  const dm = data?.decision_metrics;
  const dmc = data?.decision_metrics_corrected;
  const gain = dm?.mae && dmc?.mae ? (1 - dmc.mae / dm.mae) * 100 : null;
  const worstHour = data?.hour_of_day.reduce((a, b) => (b.mae > a.mae ? b : a), data.hour_of_day[0]);
  const worstDay = data?.daily.reduce((a, b) => (b.mae > a.mae ? b : a), data.daily[0]);

  return (
    <div className="stack">
      <Status loading={loading && !data} error={error} />

      <div className="kpis">
        <Kpi label="Error at 0h lead (MAE)" value={mw(first?.mae)} hint={`${pct(first?.nmae_pct)} of output`} />
        <Kpi label="Error at 24h lead (MAE)" value={mw(curve.find((c) => c.horizon_h === 24)?.mae)} />
        <Kpi label="Error at 48h lead (MAE)" value={mw(last?.mae)} hint={`${pct(last?.nmae_pct)} of output`} tone="warn" />
        <Kpi label="Day-ahead decision MAE" value={mw(dm?.mae)} hint={dm?.mean_lead_h ? `avg lead ${dm.mean_lead_h.toFixed(0)}h` : undefined} />
        <Kpi
          label="Day-ahead MAE, bias-corrected"
          value={mw(dmc?.mae)}
          hint={gain != null ? `${gain >= 0 ? "▼" : "▲"} ${Math.abs(gain).toFixed(0)}% vs raw forecast` : undefined}
          tone={gain != null && gain > 5 ? "good" : undefined}
        />
        <Kpi label="Cost of each extra hour" value={slope != null ? `+${slope.toFixed(0)} MW` : "–"} hint="MAE added per hour of lead time" />
      </div>

      {data && curve.length > 0 && (
        <Insight>
          Forecast error grows steadily with lead time: from <b>{gw(first.mae)}</b> for the freshest forecast to <b>{gw(last.mae)}</b> 48 hours out
          {slope != null && <> (≈ {slope.toFixed(0)} MW extra error per hour)</>}. At the day-ahead decision point the average lead is{" "}
          <b>{dm?.mean_lead_h?.toFixed(0)}h</b>, giving a typical miss of <b>{gw(dm?.mae)}</b> and a P90 miss of <b>{gw(dm?.p90_ae)}</b>. {biasSentence(dm?.bias)}
          {gain != null && gain > 5 && (
            <>
              {" "}
              Because the bias is persistent, re-scaling each forecast by the actual/forecast ratio of the previous 14 days (data a trader already has) reduces day-ahead MAE to{" "}
              <b>{gw(dmc?.mae)}</b> - a <b>{gain.toFixed(0)}% improvement</b> at zero extra cost.
            </>
          )}
        </Insight>
      )}

      <div className="grid-2">
        <Card title="Accuracy vs forecast horizon" subtitle="How much worse forecasts get the further ahead they are made">
          {!data ? (
            <Skeleton />
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={curve} margin={{ top: 8, right: 16, left: 8, bottom: 16 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="horizon_h" type="number" domain={[0, 48]} ticks={[0, 6, 12, 18, 24, 30, 36, 42, 48]} stroke="var(--axis)" fontSize={12} label={{ value: "Lead time (hours)", position: "insideBottom", offset: -8, fill: "var(--axis)", fontSize: 12 }} />
                <YAxis tickFormatter={kGW} stroke="var(--axis)" fontSize={12} width={48} label={{ value: "GW", angle: -90, position: "insideLeft", fill: "var(--axis)", fontSize: 12 }} />
                <Tooltip formatter={(v: number, n: string) => [mw(v), n]} labelFormatter={(h) => `${h}h ahead`} />
                <Legend verticalAlign="top" height={28} />
                {query.mode === "horizon" && <ReferenceLine x={query.horizonH} stroke="var(--c-forecast)" strokeDasharray="3 3" label={{ value: "selected", fill: "var(--c-forecast)", fontSize: 11, position: "top" }} />}
                {dm?.mae && <ReferenceLine y={dm.mae} stroke="var(--c-accent)" strokeDasharray="6 4" label={{ value: "day-ahead MAE", fill: "var(--c-accent)", fontSize: 11, position: "insideTopRight" }} />}
                <Line name="MAE" dataKey="mae" stroke="var(--c-forecast)" strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
                <Line name="MAE (bias-corrected)" dataKey="mae_corrected" stroke="var(--c-accent)" strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
                <Line name="P90 abs error" dataKey="p90_ae" stroke="var(--c-over)" strokeWidth={2} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
                <Line name="Bias" dataKey="bias" stroke="var(--c-muted)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title={`Error distribution (${label})`} subtitle="Forecast − actual, 500 MW bins. Right of zero = wind over-forecast.">
          {!data ? (
            <Skeleton />
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.histogram} margin={{ top: 8, right: 16, left: 8, bottom: 16 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="from" tickFormatter={kGW} stroke="var(--axis)" fontSize={12} label={{ value: "Error (GW)", position: "insideBottom", offset: -8, fill: "var(--axis)", fontSize: 12 }} />
                <YAxis stroke="var(--axis)" fontSize={12} width={40} />
                <Tooltip formatter={(v: number) => [`${v} hours`, "Count"]} labelFormatter={(f: number) => `${signedMw(f)} to ${signedMw(f + 500)}`} />
                <Bar dataKey="count" isAnimationActive={false}>
                  {data.histogram.map((b) => (
                    <Cell key={b.from} fill={b.from >= 0 ? "var(--c-over)" : "var(--c-under)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Error by time of day" subtitle="Mean absolute error by UK hour - when are forecasts least reliable?">
          {!data ? (
            <Skeleton />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={data.hour_of_day} margin={{ top: 8, right: 16, left: 8, bottom: 16 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="hour" tickFormatter={(h) => `${String(h).padStart(2, "0")}:00`} stroke="var(--axis)" fontSize={12} interval={2} />
                <YAxis tickFormatter={kGW} stroke="var(--axis)" fontSize={12} width={48} />
                <Tooltip formatter={(v: number, n: string) => [n === "Bias" ? signedMw(v) : mw(v), n]} labelFormatter={(h) => `${String(h).padStart(2, "0")}:00 UK`} />
                <Legend verticalAlign="top" height={28} />
                <Bar name="MAE" dataKey="mae" fill="var(--c-forecast)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                <Line name="Bias" dataKey="bias" stroke="var(--c-over)" dot={false} strokeWidth={2} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Daily accuracy" subtitle="Mean absolute error per delivery day">
          {!data ? (
            <Skeleton />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={data.daily} margin={{ top: 8, right: 16, left: 8, bottom: 16 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(8)} stroke="var(--axis)" fontSize={12} />
                <YAxis tickFormatter={kGW} stroke="var(--axis)" fontSize={12} width={48} />
                <Tooltip formatter={(v: number, n: string) => [n === "Bias" ? signedMw(v) : mw(v), n]} />
                <Legend verticalAlign="top" height={28} />
                <Bar name="MAE" dataKey="mae" fill="var(--c-accent)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                <Line name="Bias" dataKey="bias" stroke="var(--c-over)" dot={false} strokeWidth={2} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {data && (worstHour || worstDay) && (
        <Insight>
          {worstHour && (
            <>
              Hardest hour of the day: <b>{String(worstHour.hour).padStart(2, "0")}:00</b> (MAE {mw(worstHour.mae)}).{" "}
            </>
          )}
          {worstDay && (
            <>
              Worst day in range: <b>{worstDay.date}</b> (MAE {mw(worstDay.mae)}) - usually a weather front arriving earlier or later than predicted.
            </>
          )}
        </Insight>
      )}

      <Card title="Largest misses" subtitle={`Top 5 hourly errors for the ${label} forecast`}>
        {!data ? (
          <Skeleton height={160} />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Target time (UK)</th>
                  <th>Actual</th>
                  <th>Forecast</th>
                  <th>Error</th>
                  <th>Forecast published</th>
                  <th>Lead</th>
                </tr>
              </thead>
              <tbody>
                {data.worst_misses.map((r) => (
                  <tr key={r.start_time}>
                    <td>{fmtDateTime(r.start_time)}</td>
                    <td>{mw(r.actual)}</td>
                    <td>{mw(r.forecast)}</td>
                    <td className={(r.error ?? 0) > 0 ? "neg" : "pos"}>{signedMw(r.error)}</td>
                    <td>{fmtDateTime(r.publish_time)}</td>
                    <td>{r.lead_h?.toFixed(1)}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
