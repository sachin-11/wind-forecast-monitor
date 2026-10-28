import { useEffect, useState } from "react";
import type { Query } from "./api";
import { api } from "./api";
import { AccuracyView } from "./components/AccuracyView";
import { Controls } from "./components/Controls";
import { DayAheadView } from "./components/DayAheadView";
import { MonitorView } from "./components/MonitorView";
import { useApi } from "./useApi";

type Tab = "monitor" | "accuracy" | "dayahead";

const TABS: { id: Tab; label: string; blurb: string }[] = [
  { id: "monitor", label: "Forecast monitor", blurb: "See the forecast that was available at decision time against what the wind actually did." },
  { id: "accuracy", label: "Accuracy analysis", blurb: "Quantify forecast error by lead time, time of day and day, to size the risk in every purchase." },
  { id: "dayahead", label: "Day-ahead planner", blurb: "Replay any January decision: the forecast a trader saw, a calibrated uncertainty band, and the outcome." },
];

const MIN = "2026-01-01";
const MAX = "2026-01-31";

export default function App() {
  const [tab, setTab] = useState<Tab>("monitor");
  const [query, setQuery] = useState<Query>({ start: "2026-01-08", end: "2026-01-14", mode: "horizon", horizonH: 24 });
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem("theme") ? localStorage.getItem("theme") === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    } catch {
      return false;
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* storage unavailable */
    }
  }, [dark]);
  const meta = useApi((s) => api.meta(s), []);
  const cutoff = meta.data?.decision_cutoff_local ?? "09:00";
  const active = TABS.find((t) => t.id === tab)!;

  return (
    <div className="app">
      <div className="sticky-head">
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden>
            <rect width="32" height="32" rx="7" fill="#123a6b" />
            <g stroke="#5eead4" strokeWidth="2.4" strokeLinecap="round" fill="none">
              <path d="M16 16 16 5" />
              <path d="M16 16 25.5 21.5" />
              <path d="M16 16 6.5 21.5" />
            </g>
            <circle cx="16" cy="16" r="2.6" fill="#fff" />
          </svg>
          <div>
            <h1>Wind Forecast Monitor</h1>
            <span>GB national wind generation · day-ahead purchasing support</span>
          </div>
        </div>
        <div className="topbar-right">
          <div className="topbar-meta">
            <span className={`dot ${meta.error ? "down" : "up"}`} />
            {meta.error ? "API unreachable" : meta.data?.data_source === "sample" ? "Offline sample data (DATA_SOURCE=sample)" : "Live data: Elexon BMRS"}
          </div>
          <button className="theme-btn" onClick={() => setDark((d) => !d)} aria-label="Toggle dark mode" title="Toggle dark mode">
            {dark ? "☀" : "☾"}
          </button>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>
      </div>

      <main className="content">
        <p className="lede">{active.blurb}</p>
        {tab !== "dayahead" && (
          <Controls {...query} min={MIN} max={MAX} cutoff={cutoff} onChange={(patch) => setQuery((q) => ({ ...q, ...patch }))} />
        )}
        {tab === "monitor" && <MonitorView query={query} />}
        {tab === "accuracy" && <AccuracyView query={query} />}
        {tab === "dayahead" && <DayAheadView min={MIN} max={MAX} cutoff={cutoff} />}
      </main>

      <footer className="footer">
        <div>
          Data: <a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream">FUELHH</a> (actual, fuelType WIND, 30-min) and{" "}
          <a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream">WINDFOR</a> (forecast, hourly) from Elexon BMRS. Scope: deliveries in January 2026.
        </div>
        <div className="muted">
          Error = forecast − actual. Only forecasts published before the decision time are used; forecasts are scored on the hourly grid where both series exist.
        </div>
      </footer>
    </div>
  );
}
