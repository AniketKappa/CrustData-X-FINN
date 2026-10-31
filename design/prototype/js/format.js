// Display formatting (mirrors web/lib/format.ts in ARCHITECTURE §9). IST everywhere.
const TZ = "Asia/Kolkata";
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr1 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const cr = (v) => (v == null ? "—" : `₹${inr.format(v)} cr`);
export const crShort = (v) => (v == null ? "—" : inr.format(v).replace("-", "−"));
export const num1 = (v) => inr1.format(v);
export const price = (v) => (v == null ? "—" : `₹${inr2.format(v)}`);
export const pctv = (v, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);
export const times = (v) => (v == null ? "—" : `${v.toFixed(2)}×`);

// Change with an explicit word, never colour alone.
export function change(v, d = 1) {
  if (v == null || Number.isNaN(v)) return `<span class="chg">—</span>`;
  if (Math.abs(v) < 0.05) return `<span class="chg">flat</span>`;
  const up = v > 0;
  return `<span class="chg ${up ? "up" : "down"}">${up ? "up" : "down"} ${Math.abs(v).toFixed(d)}%</span>`;
}
export function pts(v) {
  if (Math.abs(v) < 0.05) return `<span class="chg">flat</span>`;
  return `<span class="chg ${v > 0 ? "up" : "down"}">${v > 0 ? "up" : "down"} ${Math.abs(v).toFixed(1)} pts</span>`;
}

export const dateLong = (iso) => new Intl.DateTimeFormat("en-IN", { timeZone: TZ, weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));
export const dt = (iso) => {
  const d = new Date(iso);
  const day = new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "numeric", month: "short" }).format(d);
  const tm = new Intl.DateTimeFormat("en-IN", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
  return `${day}, ${tm}`;
};

// Full value with its unit, for guidance and results ("15.0%", "₹4,500/t", "₹600 crore").
export const unitFmt = (unit) => (v) =>
  unit === "%" ? `${inr1.format(v)}%` : unit === "₹/t" ? `₹${inr.format(v)}/t` : unit === "₹ cr" ? `₹${inr.format(v)} crore` : `${inr.format(v)} ${unit}`;

export function timeAgo(iso, nowMs = Date.now()) {
  const t = new Date(iso).getTime(), m = Math.round((nowMs - t) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  if (h < 48) return "Yesterday";
  return new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "numeric", month: "short" }).format(new Date(iso));
}
export const shortDate = (iso) => new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "numeric", month: "short" }).format(new Date(iso));
export const clock = (iso) => new Intl.DateTimeFormat("en-IN", { timeZone: TZ, hour: "numeric", minute: "2-digit", hour12: true }).format(new Date(iso));
export const dayLong = (iso) => new Intl.DateTimeFormat("en-IN", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" }).format(new Date(iso));
export function greeting(iso) {
  const h = Number(new Intl.DateTimeFormat("en-IN", { timeZone: TZ, hour: "numeric", hour12: false }).format(new Date(iso)));
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}
export function pctPill(v) {
  if (v == null || Number.isNaN(v)) return `<span class="pill flat">—</span>`;
  const cls = Math.abs(v) < 0.05 ? "flat" : v > 0 ? "up" : "down";
  return `<span class="pill ${cls}">${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}%</span>`;
}
const AV = ["#2F5BEA", "#0E9F6E", "#7C3AED", "#DB2777", "#EA580C", "#0891B2", "#4F46E5", "#B45309", "#059669", "#DC2626"];
export function avatar(symbol, name, lg = false) {
  let h = 0;
  for (const ch of symbol || "?") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const words = (name || symbol || "?").replace(/\(.*?\)|ltd\.?|limited/gi, "").trim().split(/\s+/);
  const init = (words.length > 1 ? words[0][0] + words[1][0] : (symbol || words[0]).slice(0, 2)).toUpperCase();
  void h; void AV;   // one consistent avatar style (design system v3.1): no per-company colours
  return `<span class="avatar${lg ? " lg" : ""}" aria-hidden="true">${esc(init)}</span>`;
}
export const shortName = (n) => (n || "").replace(/\s+(Ltd\.?|Limited)$/i, "").replace(/\s*\(India\)/i, "");
