// Small SVG chart builders. Rendered at the container's measured width (re-rendered on resize),
// so text stays at its real size on phones. Single y-axis per chart; no interpolation; no decoration.

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}
function niceRange(lo, hi) {
  const span = hi - lo || 1, step = niceMax(span / 4) / 1;
  const s = [1, 2, 2.5, 5, 10].map((m) => m * Math.pow(10, Math.floor(Math.log10(span / 4)))).find((x) => x >= span / 4) || step;
  return { min: Math.floor(lo / s) * s, max: Math.ceil(hi / s) * s, step: s };
}
const PAD = { l: 44, r: 12, t: 22, b: 28 };

function frame(w, h, ticks, y, fmt) {
  let g = "";
  for (const v of ticks) {
    const yy = y(v);
    g += `<line x1="${PAD.l}" x2="${w - PAD.r}" y1="${yy}" y2="${yy}" class="grid"/>`;
    g += `<text x="${PAD.l - 6}" y="${yy + 4}" class="tick" text-anchor="end">${esc(fmt(v))}</text>`;
  }
  return g;
}
function xLabels(labels, x, h, every) {
  const n = labels.length - 1;
  return labels.map((l, i) => ((n - i) % every === 0)
    ? `<text x="${x(i)}" y="${h - 8}" class="tick" text-anchor="middle">${esc(l)}</text>` : "").join("");
}

// Rounded-top bar path (4px data end, square at baseline).
function bar(x, y, w, h, r = 4) {
  if (h <= 0) return "";
  r = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

export function barChart({ width, height = 200, labels, values, fmt, tipFmt, label, highlightLast = true }) {
  const w = Math.max(280, width), h = height;
  const max = niceMax(Math.max(...values));
  const ticks = [0, max / 2, max];
  const iw = w - PAD.l - PAD.r, ih = h - PAD.t - PAD.b;
  const band = iw / labels.length, bw = Math.min(24, band * 0.6);
  const x = (i) => PAD.l + band * i + band / 2;
  const y = (v) => PAD.t + ih - (v / max) * ih;
  const every = band < 44 ? 2 : 1;
  let marks = "";
  values.forEach((v, i) => {
    const cls = highlightLast && i === values.length - 1 ? "m-accent" : "m-base";
    marks += `<path d="${bar(x(i) - bw / 2, y(v), bw, y(0) - y(v))}" class="${cls}"/>`;
    marks += `<rect x="${x(i) - band / 2}" y="${PAD.t}" width="${band}" height="${ih}" class="hit" data-tip="${esc(labels[i] + ": " + tipFmt(v))}"/>`;
  });
  const n = values.length - 1;
  const endLabel = `<text x="${x(n)}" y="${y(values[n]) - 6}" class="val" text-anchor="middle">${esc(fmt(values[n]))}</text>`;
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}">${frame(w, h, ticks, y, fmt)}${marks}${endLabel}${xLabels(labels, x, h, every)}</svg>`;
}

export function lineChart({ width, height = 180, labels, values, fmt, tipFmt, label }) {
  const w = Math.max(280, width), h = height;
  const r = niceRange(Math.min(...values), Math.max(...values));
  const ticks = []; for (let v = r.min; v <= r.max + 1e-9; v += r.step) ticks.push(+v.toFixed(6));
  const iw = w - PAD.l - PAD.r, ih = h - PAD.t - PAD.b, band = iw / labels.length;
  const x = (i) => PAD.l + band * i + band / 2;
  const y = (v) => PAD.t + ih - ((v - r.min) / (r.max - r.min)) * ih;
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  let marks = `<path d="${d}" class="line"/>`;
  values.forEach((v, i) => {
    marks += `<circle cx="${x(i)}" cy="${y(v)}" r="4" class="dot${i === values.length - 1 ? " end" : ""}"/>`;
    marks += `<rect x="${x(i) - band / 2}" y="${PAD.t}" width="${band}" height="${ih}" class="hit" data-tip="${esc(labels[i] + ": " + tipFmt(v))}"/>`;
  });
  const n = values.length - 1;
  const below = n > 0 && values[n] < values[n - 1];
  marks += `<text x="${x(n)}" y="${y(values[n]) + (below ? 20 : -10)}" class="val" text-anchor="middle">${esc(fmt(values[n]))}</text>`;
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}">${frame(w, h, ticks, y, fmt)}${marks}${xLabels(labels, x, h, band < 44 ? 2 : 1)}</svg>`;
}

// Two series on one ₹ crore scale (same unit, so one axis is honest).
export function groupedBars({ width, height = 200, labels, a, b, names, fmt, tipFmt, label }) {
  const w = Math.max(280, width), h = height;
  const max = niceMax(Math.max(...a, ...b)), ticks = [0, max / 2, max];
  const iw = w - PAD.l - PAD.r, ih = h - PAD.t - PAD.b, band = iw / labels.length;
  const bw = Math.min(18, (band * 0.7 - 2) / 2);
  const x = (i) => PAD.l + band * i + band / 2;
  const y = (v) => PAD.t + ih - (Math.max(0, v) / max) * ih;
  let marks = "";
  labels.forEach((l, i) => {
    marks += `<path d="${bar(x(i) - bw - 1, y(a[i]), bw, y(0) - y(a[i]))}" class="s1"/>`;
    marks += `<path d="${bar(x(i) + 1, y(b[i]), bw, y(0) - y(b[i]))}" class="s2"/>`;
    marks += `<rect x="${x(i) - band / 2}" y="${PAD.t}" width="${band}" height="${ih}" class="hit" data-tip="${esc(`${l}: ${names[0]} ${tipFmt(a[i])} · ${names[1]} ${tipFmt(b[i])}`)}"/>`;
  });
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}">${frame(w, h, ticks, y, fmt)}${marks}${xLabels(labels, x, h, 1)}</svg>`;
}

// Promises Ledger range strip: promised band and the actual on one labelled scale.
export function rangeStrip({ width, band, actual, scale, fmt, label }) {
  const w = Math.max(240, width), h = 58, l = 8, r = 8, iw = w - l - r;
  const lo = scale.min, hi = scale.max;
  const x = (v) => l + ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * iw;
  const by = 26;
  let s = `<line x1="${l}" x2="${w - r}" y1="${by}" y2="${by}" class="axis"/>`;
  s += `<rect x="${x(band.low)}" y="${by - 6}" width="${Math.max(2, x(band.high) - x(band.low))}" height="12" class="bandr" rx="2"/>`;
  s += `<text x="${l}" y="${h - 4}" class="tick">${esc(fmt(lo))}</text><text x="${w - r}" y="${h - 4}" class="tick" text-anchor="end">${esc(fmt(hi))}</text>`;
  s += `<text x="${(x(band.low) + x(band.high)) / 2}" y="${by + 22}" class="tick" text-anchor="middle">Promised ${esc(fmt(band.low))}–${esc(fmt(band.high))}</text>`;
  if (actual != null) {
    const ax = x(actual);
    s += `<line x1="${ax}" x2="${ax}" y1="${by - 12}" y2="${by + 12}" class="actual"/>`;
    const anchor = ax > w - 60 ? "end" : ax < 60 ? "start" : "middle";
    s += `<text x="${ax}" y="${by - 16}" class="val" text-anchor="${anchor}">Actual ${esc(fmt(actual))}</text>`;
  }
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}: promised ${esc(fmt(band.low))} to ${esc(fmt(band.high))}; actual ${actual == null ? "not available" : esc(fmt(actual))}">${s}</svg>`;
}

// Price sparkline with a soft area; colour follows the period's direction (and the label says it in words).
export function sparkline({ width, height = 120, values, labels, label }) {
  const w = Math.max(260, width), h = height, pad = 6;
  if (!values || values.length < 2) return "";
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const x = (i) => pad + (i / (values.length - 1)) * (w - 2 * pad);
  const y = (v) => pad + (1 - (v - lo) / span) * (h - 2 * pad - 14);
  const dir = values.at(-1) >= values[0] ? "up" : "down";
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = `${d}L${x(values.length - 1).toFixed(1)},${h - 14}L${x(0).toFixed(1)},${h - 14}Z`;
  let hits = "";
  const bw = (w - 2 * pad) / values.length;
  values.forEach((v, i) => { hits += `<rect x="${x(i) - bw / 2}" y="0" width="${bw}" height="${h - 14}" class="hit" data-tip="${esc(labels[i] + ": ₹" + v.toLocaleString("en-IN", { maximumFractionDigits: 2 }))}"/>`; });
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}">
    <path d="${area}" class="area ${dir}" opacity=".7"/><path d="${d}" class="line ${dir}"/>${hits}
    <text x="${pad}" y="${h - 2}" class="tick">${esc(labels[0])}</text><text x="${w - pad}" y="${h - 2}" class="tick" text-anchor="end">${esc(labels.at(-1))}</text></svg>`;
}
