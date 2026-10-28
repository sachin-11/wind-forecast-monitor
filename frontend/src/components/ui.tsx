import type { ReactNode } from "react";

export function Card({ title, subtitle, children, actions }: { title?: string; subtitle?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <p className="muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className={`kpi ${tone ?? ""}`}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {hint && <span className="kpi-hint">{hint}</span>}
    </div>
  );
}

export function Insight({ children }: { children: ReactNode }) {
  return (
    <div className="insight">
      <span className="insight-icon" aria-hidden>
        ◆
      </span>
      <div>{children}</div>
    </div>
  );
}

export function Status({ loading, error }: { loading: boolean; error: string | null }) {
  if (error)
    return (
      <div className="status error" role="alert">
        Couldn’t load data: {error}
      </div>
    );
  if (loading) return <div className="status loading">Loading data from Elexon BMRS…</div>;
  return null;
}

export function Skeleton({ height = 320 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} />;
}
