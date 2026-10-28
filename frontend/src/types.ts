export type Mode = "horizon" | "decision";

export interface Metrics {
  n: number;
  mae?: number;
  rmse?: number;
  bias?: number;
  median_ae?: number;
  p90_ae?: number;
  p99_ae?: number;
  max_ae?: number;
  nmae_pct?: number | null;
  mean_actual?: number;
  mean_forecast?: number;
  over_forecast_p90?: number;
  over_forecast_p95?: number;
  under_forecast_p90?: number;
  pct_within_1gw?: number;
  corr?: number | null;
  mean_lead_h?: number | null;
}

export interface SeriesPoint {
  start_time: string;
  actual: number | null;
  forecast: number | null;
  forecast_corrected?: number | null;
  publish_time: string | null;
  lead_h: number | null;
  error: number | null;
}

export interface SeriesResponse {
  mode: Mode;
  horizon_h: number;
  points: SeriesPoint[];
  metrics: Metrics;
  metrics_corrected: Metrics;
}

export interface HorizonRow {
  horizon_h: number;
  n: number;
  mae: number;
  rmse: number;
  bias: number;
  p90_ae: number;
  nmae_pct: number;
  mae_corrected: number;
  bias_corrected: number;
}

export interface AnalysisResponse {
  mode: Mode;
  horizon_h: number;
  metrics: Metrics;
  metrics_corrected: Metrics;
  horizon_curve: HorizonRow[];
  decision_metrics: Metrics;
  decision_metrics_corrected: Metrics;
  hour_of_day: { hour: number; mae: number; bias: number; n: number }[];
  daily: { date: string; mae: number; bias: number; mean_actual: number; mean_forecast: number; n: number }[];
  histogram: { from: number; to: number; count: number }[];
  quantiles: Record<string, number>;
  worst_misses: SeriesPoint[];
}

export interface DayAheadPoint extends SeriesPoint {
  p10?: number;
  p90?: number;
}

export interface DayAheadResponse {
  delivery_date: string;
  cutoff_utc: string;
  publish_time: string | null;
  scale: number | null;
  points: DayAheadPoint[];
  band_quantiles: Record<string, number>;
  metrics: Metrics;
  metrics_corrected: Metrics;
  summary: { forecast_mwh: number | null; corrected_mwh: number | null; p10_mwh: number | null; actual_mwh: number | null };
}

export interface Meta {
  window_start: string;
  window_end: string;
  max_horizon_h: number;
  decision_cutoff_local: string;
  correction_days: number;
  timezone: string;
  data_source: string;
}
