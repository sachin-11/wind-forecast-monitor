import type { Mode } from "../types";

interface Props {
  start: string;
  end: string;
  min: string;
  max: string;
  mode: Mode;
  horizonH: number;
  cutoff: string;
  onChange: (patch: Partial<{ start: string; end: string; mode: Mode; horizonH: number }>) => void;
}

const PRESETS: { label: string; start: string; end: string }[] = [
  { label: "Week 1", start: "2026-01-01", end: "2026-01-07" },
  { label: "Week 2", start: "2026-01-08", end: "2026-01-14" },
  { label: "Week 3", start: "2026-01-15", end: "2026-01-21" },
  { label: "Week 4+", start: "2026-01-22", end: "2026-01-31" },
  { label: "All Jan", start: "2026-01-01", end: "2026-01-31" },
];

export function Controls({ start, end, min, max, mode, horizonH, cutoff, onChange }: Props) {
  return (
    <div className="controls">
      <div className="control">
        <label htmlFor="start">From</label>
        <input id="start" type="date" min={min} max={end} value={start} onChange={(e) => e.target.value && onChange({ start: e.target.value })} />
      </div>
      <div className="control">
        <label htmlFor="end">To</label>
        <input id="end" type="date" min={start} max={max} value={end} onChange={(e) => e.target.value && onChange({ end: e.target.value })} />
      </div>
      <div className="control presets" role="group" aria-label="Quick ranges">
        {PRESETS.map((p) => (
          <button key={p.label} className={`chip ${p.start === start && p.end === end ? "active" : ""}`} onClick={() => onChange({ start: p.start, end: p.end })}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="control">
        <label>Which forecast?</label>
        <div className="segmented" role="radiogroup">
          <button role="radio" aria-checked={mode === "horizon"} className={mode === "horizon" ? "on" : ""} onClick={() => onChange({ mode: "horizon" })}>
            Fixed lead time
          </button>
          <button role="radio" aria-checked={mode === "decision"} className={mode === "decision" ? "on" : ""} onClick={() => onChange({ mode: "decision" })}>
            Day-ahead cut-off
          </button>
        </div>
      </div>

      {mode === "horizon" ? (
        <div className="control slider">
          <label htmlFor="horizon">
            Forecast horizon <strong>{horizonH}h</strong>
          </label>
          <input id="horizon" type="range" min={0} max={48} step={1} value={horizonH} onChange={(e) => onChange({ horizonH: Number(e.target.value) })} />
          <span className="hint">Latest forecast published ≥ {horizonH}h before each target time</span>
        </div>
      ) : (
        <div className="control slider">
          <label>Decision cut-off</label>
          <div className="pill">D-1 at {cutoff} UK time</div>
          <span className="hint">Latest forecast available before the day-ahead purchase decision</span>
        </div>
      )}
    </div>
  );
}
