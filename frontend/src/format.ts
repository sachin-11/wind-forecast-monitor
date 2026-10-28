const nf0 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** 12345 -> "12,345 MW" */
export const mw = (v?: number | null) => (isNum(v) ? `${nf0.format(v)} MW` : "–");

/** 12345 -> "12.3 GW" */
export const gw = (v?: number | null) => (isNum(v) ? `${nf1.format(v / 1000)} GW` : "–");

/** Signed MW, e.g. "+350 MW" / "−120 MW" */
export const signedMw = (v?: number | null) =>
  isNum(v) ? `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf0.format(Math.abs(v))} MW` : "–";

export const pct = (v?: number | null, digits = 1) => (isNum(v) ? `${v.toFixed(digits)}%` : "–");

/** MWh -> "12.3 GWh" */
export const gwh = (v?: number | null) => (isNum(v) ? `${nf1.format(v / 1000)} GWh` : "–");

const dtf = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const tf = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit" });
const df = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "2-digit", month: "short" });

export const fmtDateTime = (iso?: string | null) => (iso ? dtf.format(new Date(iso)) : "–");
export const fmtTime = (iso: string) => tf.format(new Date(iso));
export const fmtDay = (iso: string) => df.format(new Date(iso));

/** Plain-English summary of accuracy, used for the insight callouts. */
export function biasSentence(bias?: number) {
  if (!isNum(bias)) return "";
  if (Math.abs(bias) < 100) return "Forecasts are essentially unbiased on average.";
  return bias > 0
    ? `Forecasts run ${mw(bias)} too high on average - wind under-delivers, so the residual demand to buy is systematically understated.`
    : `Forecasts run ${mw(-bias)} too low on average - wind over-delivers, so purchases based on the forecast tend to be slightly too large.`;
}
