import type { AnalysisResponse, DayAheadResponse, Meta, Mode, SeriesResponse } from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export interface Query {
  start: string; // YYYY-MM-DD (UK day, inclusive)
  end: string; // YYYY-MM-DD (UK day, inclusive)
  mode: Mode;
  horizonH: number;
}

async function get<T>(path: string, params: Record<string, string | number>, signal?: AbortSignal): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  const res = await fetch(`${BASE}${path}?${qs}`, { signal });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

/** Convert the inclusive UI date range into the API's [start, end) UTC instants.
 *  January has no DST so UK local midnight == UTC midnight for the challenge window. */
export function toRange(start: string, end: string) {
  const e = new Date(`${end}T00:00:00Z`);
  e.setUTCDate(e.getUTCDate() + 1);
  return { start: `${start}T00:00:00Z`, end: e.toISOString().replace(".000", "") };
}

const params = (q: Query) => ({ ...toRange(q.start, q.end), mode: q.mode, horizon_h: q.horizonH });

export const api = {
  meta: (signal?: AbortSignal) => get<Meta>("/api/meta", {}, signal),
  series: (q: Query, signal?: AbortSignal) => get<SeriesResponse>("/api/series", params(q), signal),
  analysis: (q: Query, signal?: AbortSignal) => get<AnalysisResponse>("/api/analysis", params(q), signal),
  dayAhead: (date: string, signal?: AbortSignal) => get<DayAheadResponse>("/api/day-ahead", { delivery_date: date }, signal),
};
