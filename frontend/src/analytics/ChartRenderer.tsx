/**
 * Minimal SVG-based chart renderer for the analytic detail pages.
 *
 * This is intentionally library-free so the repo works without a
 * chart-library `npm install`. Each chart kind is rendered in roughly
 * 40-80 lines of SVG. The visual idiom is dark-mode with high-contrast
 * teal/amber accents, matching styles.css. For a production redesign
 * these would be replaced with Plotly or Recharts; the component API
 * (`<ChartRenderer kind={...} data={...} />`) stays the same.
 */
import React from "react";
import { ChartKind } from "./catalog";
import { StoredSession } from "../api";
import { PALETTE } from "./chartPalette";
import { eventLetter, sessionEventIntervals, sessionEvents } from "./eventIntervals";
import { safe } from "./util";

type Props = {
  kind: ChartKind;
  session: StoredSession;
  width?: number;
  height?: number;
};

// PALETTE is now imported from chartPalette.ts, which reads from
// the --chart-* CSS custom properties defined in styles.css. The
// hex literals previously lived here; they now live in a single
// source of truth and can be re-themed without editing TSX.

export const ChartRenderer: React.FC<Props> = ({ kind, session, width = 720, height = 340 }) => {
  const ext = session.extended;
  if (!ext) return <div style={{ color: PALETTE.sub }}>No extended-analytics bundle in this session.</div>;

  switch (kind) {
    case "timeseries_overlay":
      return <TimeseriesOverlay session={session} width={width} height={height} />;
    case "summary_table":
      return <SummaryTable session={session} kind={kind} />;
    case "stacked_bar":
      return <StressDecompositionBar session={session} width={width} height={Math.min(height, 200)} />;
    case "spectrum":
      return <SpectrumChart session={session} width={width} height={height} />;
    case "line":
      return <LineChart session={session} width={width} height={height} />;
    case "tachogram":
      return <Tachogram session={session} width={width} height={height} />;
    case "poincare":
      return <PoincarePlot session={session} width={width} height={Math.min(height, width)} />;
    case "histogram":
      return <Histogram session={session} width={width} height={height} />;
    case "radar":
      return <SyncQcComposite session={session} width={width} height={Math.min(height, 260)} />;
    case "strip":
      return <MotionStrip session={session} width={width} height={Math.min(height, 160)} />;
    case "gauge":
      return <BandDurationGauge session={session} width={width} />;
    case "forest":
      return <ForestPlot session={session} width={width} height={height} />;
    case "edr_respiration":
      return <EDRRespiration session={session} width={width} height={height} />;
    case "edr_quality":
      return <EDRQualityAudit session={session} width={width} height={height} />;
    case "stress_timeline":
      return <StressTimeline session={session} width={width} height={height} />;
    case "interval_profile":
      return <IntervalArousalProfile session={session} width={width} height={height} />;
    case "bland_altman":
    default:
      return <Placeholder kind={kind} session={session} />;
  }
};

// ---------------- Charts ----------------

const EVENT_LETTER_COLOR = "#FFD84D";
const EVENT_LABEL_BAND = 32;

function TimeseriesOverlay({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const ptsRaw = session.extended?.cleaned_timeseries ?? [];
  const hasHr = ptsRaw.some((p) => safe(p.hr_bpm as number | null | undefined) !== null);
  const hasEda = ptsRaw.some((p) => safe(p.eda_us as number | null | undefined) !== null);

  if (hasHr && !hasEda) {
    const pts = ptsRaw.filter(
      (p) =>
        safe(p.timestamp_ms as number | null | undefined) !== null &&
        safe(p.hr_bpm as number | null | undefined) !== null,
    );
    return <SingleSeriesChart session={session} pts={pts} field="hr_bpm" label="HR (bpm)" color={PALETTE.hr} width={width} height={height} />;
  }
  if (hasEda && !hasHr) {
    const pts = ptsRaw.filter(
      (p) =>
        safe(p.timestamp_ms as number | null | undefined) !== null &&
        safe(p.eda_us as number | null | undefined) !== null,
    );
    return <SingleSeriesChart session={session} pts={pts} field="eda_us" label="EDA (uS)" color={PALETTE.eda} width={width} height={height} />;
  }

  // Filter out any point whose hr_bpm, eda_us, or timestamp_ms is
  // null / NaN / ±Infinity — these would otherwise propagate into
  // Math.min / Math.max and produce NaN SVG coordinates.
  const pts = ptsRaw.filter(
    (p) =>
      safe(p.timestamp_ms as number | null | undefined) !== null &&
      safe(p.hr_bpm as number | null | undefined) !== null &&
      safe(p.eda_us as number | null | undefined) !== null,
  );
  if (pts.length < 2) return <Empty msg="Not enough timeseries data" />;
  const t0 = pts[0].timestamp_ms!;
  const t1 = pts[pts.length - 1].timestamp_ms!;
  const hr = pts.map((p) => p.hr_bpm!);
  const eda = pts.map((p) => p.eda_us!);
  const hrMin = Math.min(...hr), hrMax = Math.max(...hr);
  const edaMin = Math.min(...eda), edaMax = Math.max(...eda);
  const hrPeak = maxIndex(hr);
  const edaPeak = maxIndex(eda);
  const padX = 36;
  const topPad = 42;
  const panelGap = 44;
  const bottomPad = 48;
  const w = width - padX * 2;
  const panelH = Math.max(80, (height - topPad - panelGap - bottomPad) / 2);
  const hrTop = topPad;
  const edaTop = topPad + panelH + panelGap;
  const axisY = Math.min(height - 24, edaTop + panelH);
  const toX = (t: number) => padX + ((t - t0) / (t1 - t0 || 1)) * w;
  const toYHR = (v: number) => hrTop + ((hrMax - v) / (hrMax - hrMin || 1)) * panelH;
  const toYEDA = (v: number) => edaTop + ((edaMax - v) / (edaMax - edaMin || 1)) * panelH;
  const hrPath = pts.map((p, i) => `${i === 0 ? "M" : "L"}${toX(p.timestamp_ms!).toFixed(1)},${toYHR(p.hr_bpm!).toFixed(1)}`).join(" ");
  const edaPath = pts.map((p, i) => `${i === 0 ? "M" : "L"}${toX(p.timestamp_ms!).toFixed(1)},${toYEDA(p.eda_us!).toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} role="img" aria-label="HR and EDA timeseries overlay">
	      <rect width={width} height={height} fill={PALETTE.bg} />
      <EventLinesMs session={session} t0={t0} t1={t1} toX={toX} y1={hrTop} y2={height - 24} width={width} />
	      {/* HR panel */}
      <text x={padX} y={18} fill={PALETTE.hr} fontSize="12" fontWeight="600">HR (bpm)</text>
      <text x={padX} y={33} fill={PALETTE.sub} fontSize="10">{hrMin.toFixed(0)} - {hrMax.toFixed(0)}</text>
      <path d={hrPath} stroke={PALETTE.hr} strokeWidth={1.5} fill="none" />
      <circle cx={toX(pts[hrPeak].timestamp_ms!)} cy={toYHR(hrMax)} r={4} fill={PALETTE.hr} stroke={PALETTE.text} strokeWidth={1} />
      <text x={labelX(toX(pts[hrPeak].timestamp_ms!), width, 92)} y={Math.max(14, toYHR(hrMax) - 8)} fill={PALETTE.text} fontSize="10" fontWeight="700">
        peak HR {hrMax.toFixed(0)}
      </text>
      {/* EDA panel */}
      <text x={padX} y={edaTop - 18} fill={PALETTE.eda} fontSize="12" fontWeight="600">EDA (uS)</text>
      <text x={padX} y={edaTop - 4} fill={PALETTE.sub} fontSize="10">{edaMin.toFixed(2)} - {edaMax.toFixed(2)}</text>
      <path d={edaPath} stroke={PALETTE.eda} strokeWidth={1.5} fill="none" />
      <circle cx={toX(pts[edaPeak].timestamp_ms!)} cy={toYEDA(edaMax)} r={4} fill={PALETTE.eda} stroke={PALETTE.text} strokeWidth={1} />
      <text x={labelX(toX(pts[edaPeak].timestamp_ms!), width, 108)} y={Math.max(edaTop + 12, toYEDA(edaMax) - 8)} fill={PALETTE.text} fontSize="10" fontWeight="700">
        peak EDA {edaMax.toFixed(2)}
      </text>
      {/* Axes */}
      <line x1={padX} y1={axisY} x2={padX + w} y2={axisY} stroke={PALETTE.grid} />
      <text x={padX} y={height - 5} fill={PALETTE.sub} fontSize="10">0 s</text>
      <text x={width - padX - 40} y={height - 5} fill={PALETTE.sub} fontSize="10">{((t1 - t0) / 1000).toFixed(0)} s</text>
    </svg>
  );
}

function SingleSeriesChart({
  session, pts, field, label, color, width, height,
}: {
  session: StoredSession;
  pts: Array<Record<string, number | undefined>>;
  field: "hr_bpm" | "eda_us";
  label: string;
  color: string;
  width: number;
  height: number;
}) {
  if (pts.length < 2) return <Empty msg={`Not enough ${label} data`} />;
  const t0 = pts[0].timestamp_ms!;
  const t1 = pts[pts.length - 1].timestamp_ms!;
  const vals = pts.map((p) => p[field] as number);
  const vMin = Math.min(...vals), vMax = Math.max(...vals);
  const peak = maxIndex(vals);
  const pad = 40;
  const w = width - pad * 2;
  const h = height - pad * 2 - EVENT_LABEL_BAND;
  const toX = (t: number) => pad + ((t - t0) / (t1 - t0 || 1)) * w;
  const toY = (v: number) => pad + ((vMax - v) / (vMax - vMin || 1)) * h;
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${toX(p.timestamp_ms!).toFixed(1)},${toY(p[field] as number).toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} role="img" aria-label={label}>
	      <rect width={width} height={height} fill={PALETTE.bg} />
      <EventLinesMs session={session} t0={t0} t1={t1} toX={toX} y1={pad} y2={pad + h + EVENT_LABEL_BAND - 2} width={width} />
	      <text x={pad} y={24} fill={color} fontSize="12" fontWeight="600">{label}</text>
      <text x={pad} y={40} fill={PALETTE.sub} fontSize="10">{vMin.toFixed(2)} - {vMax.toFixed(2)}</text>
      <path d={path} stroke={color} strokeWidth={1.6} fill="none" />
      <circle cx={toX(pts[peak].timestamp_ms!)} cy={toY(vMax)} r={4} fill={color} stroke={PALETTE.text} strokeWidth={1} />
      <text x={labelX(toX(pts[peak].timestamp_ms!), width, 100)} y={Math.max(18, toY(vMax) - 8)} fill={PALETTE.text} fontSize="10" fontWeight="700">
        peak {vMax.toFixed(field === "hr_bpm" ? 0 : 2)}
      </text>
      <line x1={pad} y1={pad + h} x2={pad + w} y2={pad + h} stroke={PALETTE.grid} />
      <text x={pad} y={height - 8} fill={PALETTE.sub} fontSize="10">0 s</text>
      <text x={width - pad - 44} y={height - 8} fill={PALETTE.sub} fontSize="10">{((t1 - t0) / 1000).toFixed(0)} s</text>
    </svg>
  );
}

function StressDecompositionBar({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const d = session.extended?.stress_decomposition;
  if (!d) return <Empty msg="No decomposition available" />;
  const comps = d.components;
  const total = d.total;
  const colors = ["#00C896", "#E8872A", "#F5A623", "#B83A4A", "#A78BFA"];
  const bar = height - 80;
  let x = 40;
  const scale = (width - 80);
  return (
    <svg width={width} height={height} role="img" aria-label="Stress decomposition">
      <rect width={width} height={height} fill={PALETTE.bg} />
      <text x={40} y={24} fill={PALETTE.text} fontSize="13" fontWeight="600">
        Total composite: {total.toFixed(3)} · dominant: {d.dominant_driver}
      </text>
      {comps.map((c, i) => {
        const w = c.contribution * scale;
        const el = (
          <g key={c.name}>
            <rect x={x} y={40} width={w} height={bar} fill={colors[i]} opacity={0.9} />
            <text x={x + 4} y={60} fill="#000" fontSize="11" fontWeight="700">{c.name}</text>
            <text x={x + 4} y={75} fill="#000" fontSize="10">{c.contribution.toFixed(3)} / {c.weight.toFixed(2)}</text>
          </g>
        );
        x += w;
        return el;
      })}
      <line x1={40 + total * scale} y1={32} x2={40 + total * scale} y2={40 + bar + 8} stroke={PALETTE.text} strokeWidth={2} />
      <text x={40} y={height - 8} fill={PALETTE.sub} fontSize="10">0.0</text>
      <text x={width - 56} y={height - 8} fill={PALETTE.sub} fontSize="10">1.0 (max)</text>
    </svg>
  );
}

function SpectrumChart({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const psd = session.extended?.psd;
  if (!psd || psd.frequencies_hz.length === 0) return <Empty msg="Spectrum not available (recording too short)" />;
  const f = psd.frequencies_hz;
  const p = psd.psd_ms2_hz;
  const fMax = 0.5;
  const mask = f.map((hz) => hz <= fMax);
  const fVis = f.filter((_, i) => mask[i]);
  const pVis = p.filter((_, i) => mask[i]).map((v) => Math.log10(Math.max(v, 1e-6)));
  const pad = 40;
  const w = width - pad * 2, h = height - pad * 2;
  const pMin = Math.min(...pVis), pMax = Math.max(...pVis);
  const toX = (hz: number) => pad + (hz / fMax) * w;
  const toY = (lp: number) => pad + ((pMax - lp) / (pMax - pMin || 1)) * h;
  const path = fVis.map((hz, i) => `${i === 0 ? "M" : "L"}${toX(hz).toFixed(1)},${toY(pVis[i]).toFixed(1)}`).join(" ");
  const fs = session.result.feature_summary;
  const bands = [
    { lo: 0.003, hi: 0.04, label: "VLF", color: "#8B5CF6" },
    { lo: 0.04, hi: 0.15, label: "LF", color: "#3B82F6" },
    { lo: 0.15, hi: 0.40, label: "HF", color: "#10B981" },
  ];
  return (
    <svg width={width} height={height} role="img" aria-label="Power spectrum">
      <rect width={width} height={height} fill={PALETTE.bg} />
      {bands.map((b) => (
        <g key={b.label}>
          <rect x={toX(b.lo)} y={pad} width={toX(b.hi) - toX(b.lo)} height={h} fill={b.color} opacity={0.12} />
          <text x={toX((b.lo + b.hi) / 2) - 12} y={pad + 14} fill={b.color} fontSize="11" fontWeight="600">{b.label}</text>
        </g>
      ))}
      <path d={path} stroke={PALETTE.hr} strokeWidth={1.5} fill="none" />
      <line x1={pad} y1={pad + h} x2={pad + w} y2={pad + h} stroke={PALETTE.grid} />
      <line x1={pad} y1={pad} x2={pad} y2={pad + h} stroke={PALETTE.grid} />
      <text x={pad} y={height - 10} fill={PALETTE.sub} fontSize="10">0 Hz</text>
      <text x={width - pad - 24} y={height - 10} fill={PALETTE.sub} fontSize="10">0.5 Hz</text>
      <text x={4} y={pad + 6} fill={PALETTE.sub} fontSize="10">log₁₀ PSD</text>
      <text x={pad} y={24} fill={PALETTE.text} fontSize="11" fontWeight="700">
        LF/HF {fs.lf_hf_ratio == null ? "unavailable" : fs.lf_hf_ratio.toFixed(2)}
      </text>
      {fs.lf_ms2 != null && fs.hf_ms2 != null && (
        <text x={pad} y={40} fill={PALETTE.sub} fontSize="10">
          LF {fs.lf_ms2.toFixed(1)} ms2 · HF {fs.hf_ms2.toFixed(1)} ms2
        </text>
      )}
    </svg>
  );
}

function LineChart({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  // Generic: finds windowed stress if available, else spectral ratio.
  const w = session.extended?.windowed;
  const s = session.extended?.spectral_trajectory;
  const data = (() => {
    if (w && w.t_s.length > 1) return { x: w.t_s, y: w.stress, label: "Stress composite (windowed)", color: PALETTE.hr };
    if (s && s.t_s.length > 1) return { x: s.t_s, y: s.lf_hf_ratio.map((v) => v ?? NaN), label: "LF/HF ratio", color: PALETTE.accent };
    return null;
  })();
  if (!data) return <Empty msg="Not enough windows for a trajectory" />;
  const pad = 40;
  const W = width - pad * 2, H = height - pad * 2 - EVENT_LABEL_BAND;
  const validY = data.y.filter((v) => Number.isFinite(v)) as number[];
  const yMin = Math.min(...validY), yMax = Math.max(...validY);
  const xMin = data.x[0], xMax = data.x[data.x.length - 1];
  const toX = (x: number) => pad + ((x - xMin) / (xMax - xMin || 1)) * W;
  const toY = (y: number) => pad + ((yMax - y) / (yMax - yMin || 1)) * H;
  const segs: string[] = [];
  let current = "";
  for (let i = 0; i < data.x.length; i++) {
    if (!Number.isFinite(data.y[i])) { if (current) { segs.push(current); current = ""; } continue; }
    const c = `${i === 0 || !current ? "M" : "L"}${toX(data.x[i]).toFixed(1)},${toY(data.y[i] as number).toFixed(1)}`;
    current = current ? current + " " + c : c;
  }
  if (current) segs.push(current);
  const peakIndex = data.y.findIndex((v) => v === yMax);
  return (
    <svg width={width} height={height} role="img" aria-label={data.label}>
	      <rect width={width} height={height} fill={PALETTE.bg} />
      <EventLinesSeconds session={session} xMin={xMin} xMax={xMax} toX={toX} y1={pad} y2={pad + H + EVENT_LABEL_BAND - 2} width={width} />
	      <text x={pad} y={20} fill={data.color} fontSize="12" fontWeight="600">{data.label}</text>
      {segs.map((path, i) => <path key={i} d={path} stroke={data.color} strokeWidth={1.8} fill="none" />)}
      {peakIndex >= 0 && (
        <>
          <circle cx={toX(data.x[peakIndex])} cy={toY(yMax)} r={4} fill={data.color} stroke={PALETTE.text} strokeWidth={1} />
          <text x={labelX(toX(data.x[peakIndex]), width, 108)} y={Math.max(18, toY(yMax) - 8)} fill={PALETTE.text} fontSize="10" fontWeight="700">
            peak {yMax.toFixed(2)}
          </text>
        </>
      )}
      <line x1={pad} y1={pad + H} x2={pad + W} y2={pad + H} stroke={PALETTE.grid} />
      <text x={pad} y={pad + H + 14} fill={PALETTE.sub} fontSize="10">{xMin.toFixed(0)} s</text>
      <text x={pad + W - 30} y={pad + H + 14} fill={PALETTE.sub} fontSize="10">{xMax.toFixed(0)} s</text>
      <text x={6} y={pad + 6} fill={PALETTE.sub} fontSize="10">{yMax.toFixed(2)}</text>
      <text x={6} y={pad + H} fill={PALETTE.sub} fontSize="10">{yMin.toFixed(2)}</text>
    </svg>
  );
}

function Tachogram({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const rr = session.extended?.rr_series_ms ?? [];
  if (rr.length < 3) return <Empty msg="No RR series" />;
  const pad = 40;
  const W = width - pad * 2, H = height - pad * 2;
  const rMin = Math.min(...rr), rMax = Math.max(...rr);
  const med = median(rr);
  const jumpThreshold = Math.max(250, med * 0.25);
  const jumps = rr
    .map((v, i) => ({ v, i, jump: i === 0 ? 0 : Math.abs(v - rr[i - 1]) }))
    .filter((p) => p.jump > jumpThreshold)
    .slice(0, 20);
  const toX = (i: number) => pad + (i / (rr.length - 1)) * W;
  const toY = (v: number) => pad + ((rMax - v) / (rMax - rMin || 1)) * H;
  const path = rr.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} role="img" aria-label="RR tachogram">
      <rect width={width} height={height} fill={PALETTE.bg} />
      <path d={path} stroke={PALETTE.hr} strokeWidth={1.2} fill="none" />
      {jumps.map((p) => (
        <circle key={p.i} cx={toX(p.i)} cy={toY(p.v)} r={3.5} fill={PALETTE.bad} stroke={PALETTE.text} strokeWidth={0.8} />
      ))}
      <line x1={pad} y1={toY(1000)} x2={pad + W} y2={toY(1000)} stroke={PALETTE.grid} strokeDasharray="3,3" />
      <text x={pad + 4} y={toY(1000) - 4} fill={PALETTE.sub} fontSize="10">1000 ms (= 60 bpm)</text>
      <text x={pad} y={22} fill={PALETTE.text} fontSize="11" fontWeight="700">
        {jumps.length} abrupt jump{jumps.length === 1 ? "" : "s"} highlighted
      </text>
      <text x={6} y={pad + 6} fill={PALETTE.sub} fontSize="10">{rMax.toFixed(0)} ms</text>
      <text x={6} y={pad + H} fill={PALETTE.sub} fontSize="10">{rMin.toFixed(0)} ms</text>
      <text x={pad} y={height - 8} fill={PALETTE.sub} fontSize="10">beat 0</text>
      <text x={pad + W - 60} y={height - 8} fill={PALETTE.sub} fontSize="10">beat {rr.length - 1}</text>
    </svg>
  );
}

function PoincarePlot({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const rr = session.extended?.rr_series_ms ?? [];
  if (rr.length < 10) return <Empty msg="Not enough beats for Poincaré" />;
  const pairs = rr.slice(0, -1).map((v, i) => [v, rr[i + 1]]);
  const all = pairs.flat();
  const vMin = Math.min(...all) * 0.95;
  const vMax = Math.max(...all) * 1.05;
  const pad = 40;
  const sz = Math.min(width, height) - pad * 2;
  const toX = (v: number) => pad + ((v - vMin) / (vMax - vMin)) * sz;
  const toY = (v: number) => pad + sz - ((v - vMin) / (vMax - vMin)) * sz;
  const mean = all.reduce((a, b) => a + b, 0) / all.length;

  // Prefer backend-computed SD1 / SD2 / ratio / ellipse area when
  // available (Brennan et al. 2001 closed form, computed on the
  // L&T-corrected RR series in features.py). Fall back to local
  // recomputation when the fields are missing — e.g. on older
  // analysis payloads.
  const fs = session.result.feature_summary;
  const sd1 = safe(fs.sd1_ms) ?? Math.sqrt(pairs.reduce((s, [a, b]) => s + Math.pow((b - a), 2), 0) / (2 * pairs.length));
  const sd2 = safe(fs.sd2_ms) ?? Math.sqrt(pairs.reduce((s, [a, b]) => s + Math.pow((a + b - 2 * mean), 2), 0) / (2 * pairs.length));
  const ratio = safe(fs.sd1_sd2_ratio) ?? (sd2 > 0 ? sd1 / sd2 : null);
  const ellipseArea = safe(fs.ellipse_area_ms2) ?? Math.PI * sd1 * sd2;

  return (
    <svg width={width} height={height} role="img" aria-label="Poincaré plot with SD1/SD2 ellipse">
      <rect width={width} height={height} fill={PALETTE.bg} />
      <line x1={toX(vMin)} y1={toY(vMin)} x2={toX(vMax)} y2={toY(vMax)} stroke={PALETTE.grid} strokeDasharray="3,3" />
      {pairs.map(([a, b], i) => (
        <circle key={i} cx={toX(a)} cy={toY(b)} r={2} fill={PALETTE.hr} opacity={0.55} />
      ))}
      <ellipse
        cx={toX(mean)}
        cy={toY(mean)}
        rx={(sd2 / (vMax - vMin)) * sz}
        ry={(sd1 / (vMax - vMin)) * sz}
        transform={`rotate(-45 ${toX(mean)} ${toY(mean)})`}
        stroke={PALETTE.eda}
        strokeWidth={1.5}
        fill="none"
      />
      {/* SD1 axis (perpendicular to identity line) */}
      <line
        x1={toX(mean) + (-sd1 / (vMax - vMin)) * sz * Math.SQRT1_2}
        y1={toY(mean) + (-sd1 / (vMax - vMin)) * sz * Math.SQRT1_2}
        x2={toX(mean) + (sd1 / (vMax - vMin)) * sz * Math.SQRT1_2}
        y2={toY(mean) + (sd1 / (vMax - vMin)) * sz * Math.SQRT1_2}
        stroke={PALETTE.resp}
        strokeWidth={1}
        strokeDasharray="2,2"
      />
      {/* SD2 axis (along identity line) */}
      <line
        x1={toX(mean) + (-sd2 / (vMax - vMin)) * sz * Math.SQRT1_2}
        y1={toY(mean) + (sd2 / (vMax - vMin)) * sz * Math.SQRT1_2}
        x2={toX(mean) + (sd2 / (vMax - vMin)) * sz * Math.SQRT1_2}
        y2={toY(mean) + (-sd2 / (vMax - vMin)) * sz * Math.SQRT1_2}
        stroke={PALETTE.accent}
        strokeWidth={1}
        strokeDasharray="2,2"
      />
      <text x={pad} y={20} fill={PALETTE.text} fontSize="12" fontWeight="600">
        SD1 = {sd1.toFixed(1)} ms · SD2 = {sd2.toFixed(1)} ms
      </text>
      <text x={pad} y={36} fill={PALETTE.sub} fontSize="11">
        SD1/SD2 = {ratio !== null ? ratio.toFixed(3) : "—"} · ellipse area = {ellipseArea.toFixed(0)} ms²
      </text>
      <text x={pad} y={pad + sz + 14} fill={PALETTE.sub} fontSize="10">RR(n) (ms)</text>
      <text x={6} y={pad + 4} fill={PALETTE.sub} fontSize="10">RR(n+1)</text>
    </svg>
  );
}

function Histogram({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const rr = session.extended?.rr_series_ms ?? [];
  if (rr.length < 10) return <Empty msg="Not enough beats for histogram" />;
  const bins = 30;
  const lo = 300, hi = 2000;
  const counts = new Array(bins).fill(0);
  for (const v of rr) {
    if (v >= lo && v < hi) counts[Math.min(bins - 1, Math.floor(((v - lo) / (hi - lo)) * bins))]++;
  }
  const maxC = Math.max(...counts);
  const med = median(rr);
  const outside = rr.filter((v) => v < lo || v > hi).length;
  const pad = 40;
  const W = width - pad * 2, H = height - pad * 2;
  const bw = W / bins;
  return (
    <svg width={width} height={height} role="img" aria-label="RR histogram">
      <rect width={width} height={height} fill={PALETTE.bg} />
      {counts.map((c, i) => (
        <rect key={i} x={pad + i * bw + 1} y={pad + H - (c / maxC) * H} width={bw - 2} height={(c / maxC) * H} fill={PALETTE.hr} opacity={0.8} />
      ))}
      <line x1={pad + ((600 - lo) / (hi - lo)) * W} y1={pad} x2={pad + ((600 - lo) / (hi - lo)) * W} y2={pad + H} stroke={PALETTE.eda} strokeDasharray="3,3" />
      <line x1={pad + ((1000 - lo) / (hi - lo)) * W} y1={pad} x2={pad + ((1000 - lo) / (hi - lo)) * W} y2={pad + H} stroke={PALETTE.eda} strokeDasharray="3,3" />
      <line x1={pad + ((med - lo) / (hi - lo)) * W} y1={pad} x2={pad + ((med - lo) / (hi - lo)) * W} y2={pad + H} stroke={PALETTE.text} strokeWidth={2} />
      <text x={labelX(pad + ((med - lo) / (hi - lo)) * W, width, 110)} y={pad + 28} fill={PALETTE.text} fontSize="10" fontWeight="700">
        median {med.toFixed(0)} ms
      </text>
      <text x={pad} y={height - 8} fill={PALETTE.sub} fontSize="10">300 ms</text>
      <text x={width - pad - 40} y={height - 8} fill={PALETTE.sub} fontSize="10">2000 ms</text>
      <text x={pad + 4} y={pad + 12} fill={PALETTE.sub} fontSize="10">count (max={maxC}) · outside bounds {outside}</text>
    </svg>
  );
}

function SyncQcComposite({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const score = session.result.sync_qc_score;
  const band = session.result.sync_qc_band;
  const reasons = session.result.sync_qc_failure_reasons;
  const color = band === "green" ? PALETTE.good : band === "yellow" ? PALETTE.warn : PALETTE.bad;
  const pad = 20;
  const W = width - pad * 2;
  return (
    <svg width={width} height={height} role="img" aria-label="Sync-QC composite">
      <rect width={width} height={height} fill={PALETTE.bg} />
      <text x={pad} y={30} fill={PALETTE.text} fontSize="14" fontWeight="600">Sync-QC composite score</text>
      <rect x={pad} y={50} width={W} height={30} fill={PALETTE.grid} />
      <rect x={pad} y={50} width={(W * score) / 100} height={30} fill={color} />
      <text x={pad + 8} y={70} fill="#000" fontSize="13" fontWeight="700">{score.toFixed(1)} / 100 — {band.toUpperCase()}</text>
      <text x={pad} y={110} fill={PALETTE.sub} fontSize="11" fontWeight="600">Reasons:</text>
      {reasons.slice(0, 5).map((r, i) => (
        <text key={i} x={pad} y={130 + i * 16} fill={PALETTE.sub} fontSize="11">· {r}</text>
      ))}
      {reasons.length === 0 && <text x={pad} y={130} fill={PALETTE.sub} fontSize="11">· All sub-components within thresholds.</text>}
    </svg>
  );
}

function MotionStrip({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const mar = session.result.movement_artifact_ratio;
  const color = mar > 0.2 ? PALETTE.bad : mar > 0.05 ? PALETTE.warn : PALETTE.good;
  const pts = (session.extended?.cleaned_timeseries ?? [])
    .filter((p) =>
      safe(p.timestamp_ms) !== null &&
      safe(p.acc_x) !== null &&
      safe(p.acc_y) !== null &&
      safe(p.acc_z) !== null,
    )
    .map((p) => ({
      t: p.timestamp_ms!,
      mag: Math.sqrt(Math.pow(p.acc_x!, 2) + Math.pow(p.acc_y!, 2) + Math.pow(p.acc_z!, 2)),
      hr: safe(p.hr_bpm),
    }));
  if (pts.length > 2) {
    const t0 = pts[0].t;
    const t1 = pts[pts.length - 1].t;
    const vals = pts.map((p) => p.mag);
    const vMin = Math.min(...vals);
    const vMax = Math.max(...vals);
    const pad = 40;
    const W = width - pad * 2;
    const H = height - pad * 2 - EVENT_LABEL_BAND;
    const toX = (t: number) => pad + ((t - t0) / (t1 - t0 || 1)) * W;
    const toY = (v: number) => pad + ((vMax - v) / (vMax - vMin || 1)) * H;
    const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${toX(p.t).toFixed(1)},${toY(p.mag).toFixed(1)}`).join(" ");
    const peak = maxIndex(vals);
    return (
      <svg width={width} height={height} role="img" aria-label="Motion magnitude timeline">
        <rect width={width} height={height} fill={PALETTE.bg} />
        <EventLinesMs session={session} t0={t0} t1={t1} toX={toX} y1={pad} y2={pad + H + EVENT_LABEL_BAND - 2} width={width} />
        <text x={pad} y={22} fill={color} fontSize="12" fontWeight="700">
          Motion magnitude timeline · artifact ratio {(mar * 100).toFixed(1)}%
        </text>
        <path d={path} stroke={color} strokeWidth={1.6} fill="none" />
        <circle cx={toX(pts[peak].t)} cy={toY(vals[peak])} r={4} fill={color} stroke={PALETTE.text} strokeWidth={1} />
        <text x={labelX(toX(pts[peak].t), width, 112)} y={Math.max(18, toY(vals[peak]) - 8)} fill={PALETTE.text} fontSize="10" fontWeight="700">
          peak motion {vals[peak].toFixed(2)} g
        </text>
        <line x1={pad} y1={pad + H} x2={pad + W} y2={pad + H} stroke={PALETTE.grid} />
        <text x={pad} y={pad + H + 14} fill={PALETTE.sub} fontSize="10">0 s</text>
        <text x={pad + W - 42} y={pad + H + 14} fill={PALETTE.sub} fontSize="10">{((t1 - t0) / 1000).toFixed(0)} s</text>
        <text x={6} y={pad + 6} fill={PALETTE.sub} fontSize="10">{vMax.toFixed(2)} g</text>
        <text x={6} y={pad + H} fill={PALETTE.sub} fontSize="10">{vMin.toFixed(2)} g</text>
      </svg>
    );
  }
  return (
    <svg width={width} height={height} role="img" aria-label="Motion strip">
      <rect width={width} height={height} fill={PALETTE.bg} />
      <text x={20} y={30} fill={PALETTE.text} fontSize="13" fontWeight="600">
        Motion-artifact ratio: {(mar * 100).toFixed(1)}%
      </text>
      <rect x={20} y={55} width={width - 40} height={24} fill={PALETTE.grid} />
      <rect x={20} y={55} width={(width - 40) * mar} height={24} fill={color} />
      <text x={20} y={100} fill={PALETTE.sub} fontSize="11">
        &lt; 5% typical for seated protocols · &gt; 20% indicates movement or poor electrode adherence.
      </text>
    </svg>
  );
}

function BandDurationGauge({ session, width }: { session: StoredSession; width: number }) {
  const ts = session.extended?.cleaned_timeseries ?? [];
  const dur = ts.length > 1 ? (ts[ts.length - 1].timestamp_ms! - ts[0].timestamp_ms!) / 1000 : 0;
  const bands = [
    { name: "HF", min: 60 },
    { name: "LF", min: 120 },
    { name: "VLF", min: 300 },
  ];
  const maxMin = Math.max(dur, 300) * 1.15;
  const pad = 20;
  return (
    <svg width={width} height={180} role="img" aria-label="Band-duration gauge">
      <rect width={width} height={180} fill={PALETTE.bg} />
      <text x={pad} y={24} fill={PALETTE.text} fontSize="13" fontWeight="600">Recording duration: {dur.toFixed(0)} s</text>
      {bands.map((b, i) => {
        const y = 48 + i * 40;
        const passed = dur >= b.min;
        const color = passed ? PALETTE.good : PALETTE.warn;
        const w = width - pad * 2;
        return (
          <g key={b.name}>
            <text x={pad} y={y + 14} fill={PALETTE.sub} fontSize="11">{b.name} (≥ {b.min} s)</text>
            <rect x={pad + 60} y={y} width={w - 60} height={20} fill={PALETTE.grid} />
            <rect x={pad + 60} y={y} width={((w - 60) * Math.min(dur, maxMin)) / maxMin} height={20} fill={color} />
            <line x1={pad + 60 + ((w - 60) * b.min) / maxMin} y1={y - 4} x2={pad + 60 + ((w - 60) * b.min) / maxMin} y2={y + 24} stroke={PALETTE.text} strokeWidth={2} />
            <text x={pad + 60 + ((w - 60) * b.min) / maxMin + 4} y={y + 14} fill={PALETTE.text} fontSize="11">
              {passed ? "✓" : `short by ${(b.min - dur).toFixed(0)} s`}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function ForestPlot({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const inf = session.extended?.inference;
  if (!inf) return <Empty msg="Inference statistics unavailable" />;
  const rows = [
    { name: "HR mean 95% CI", mean: inf.hr_mean_ci95.mean, lo: inf.hr_mean_ci95.lower, hi: inf.hr_mean_ci95.upper, unit: "bpm" },
    { name: "EDA mean 95% CI", mean: inf.eda_mean_ci95.mean, lo: inf.eda_mean_ci95.lower, hi: inf.eda_mean_ci95.upper, unit: "µS" },
  ];
  const d = { hr: inf.hr_change_effect_size_d, eda: inf.eda_change_effect_size_d };
  const p = { hr: inf.hr_trend_pvalue, eda: inf.eda_trend_pvalue };
  const pad = 20;
  return (
    <svg width={width} height={height} role="img" aria-label="Forest plot">
      <rect width={width} height={height} fill={PALETTE.bg} />
      {rows.map((r, i) => {
        const y = 40 + i * 60;
        const vMin = r.lo - (r.hi - r.lo) * 0.3;
        const vMax = r.hi + (r.hi - r.lo) * 0.3;
        const toX = (v: number) => pad + 160 + ((v - vMin) / (vMax - vMin)) * (width - pad - 180);
        return (
          <g key={r.name}>
            <text x={pad} y={y} fill={PALETTE.sub} fontSize="11">{r.name}</text>
            <line x1={toX(r.lo)} y1={y + 10} x2={toX(r.hi)} y2={y + 10} stroke={PALETTE.hr} strokeWidth={2} />
            <circle cx={toX(r.mean)} cy={y + 10} r={5} fill={PALETTE.hr} />
            <text x={pad} y={y + 26} fill={PALETTE.text} fontSize="11">
              {r.mean.toFixed(2)} [{r.lo.toFixed(2)}, {r.hi.toFixed(2)}] {r.unit}
            </text>
          </g>
        );
      })}
      <text x={pad} y={height - 40} fill={PALETTE.sub} fontSize="11">
        Cohen's d (first vs second half): HR={d.hr.toFixed(3)}, EDA={d.eda.toFixed(3)}
      </text>
      <text x={pad} y={height - 20} fill={PALETTE.sub} fontSize="11">
        Trend p (FDR): HR={p.hr.toFixed(4)}, EDA={p.eda.toFixed(4)}
      </text>
    </svg>
  );
}

function SummaryTable({ session, kind: _kind }: { session: StoredSession; kind: ChartKind }) {
  const fs = session.result.feature_summary;
  const ds = session.extended?.descriptive_stats;
  const metrics = [
    { label: "RMSSD", value: fs.rmssd_ms, max: 100, unit: "ms", color: PALETTE.hr },
    { label: "SDNN", value: fs.sdnn_ms, max: 250, unit: "ms", color: PALETTE.accent },
    { label: "Mean HR", value: fs.mean_hr_bpm, max: 120, unit: "bpm", color: PALETTE.eda },
    { label: "EDA tonic", value: fs.eda_mean_us, max: 20, unit: "uS", color: PALETTE.resp },
    { label: "Stress v1", value: fs.stress_score, max: 1, unit: "", color: PALETTE.warn },
    { label: "Stress v2", value: fs.stress_score_v2 ?? null, max: 1, unit: "", color: PALETTE.bad },
  ].filter((m) => typeof m.value === "number" && Number.isFinite(m.value));
  const chartWidth = 860;
  const rowH = 26;
  const chartHeight = 32 + metrics.length * rowH;
  const barX = 130;
  const barW = chartWidth - barX - 92;
  return (
    <div style={{ background: PALETTE.bg, padding: 20 }}>
      <svg width={chartWidth} height={chartHeight} role="img" aria-label="Summary metric bar chart" style={{ width: "100%", height: "auto", marginBottom: 16 }}>
        <rect width={chartWidth} height={chartHeight} fill={PALETTE.bg} />
        <text x={0} y={14} fill={PALETTE.text} fontSize="12" fontWeight="700">Summary metric bars</text>
        {metrics.map((m, i) => {
          const y = 28 + i * rowH;
          const value = m.value as number;
          const width = Math.max(2, Math.min(1, value / m.max) * barW);
          return (
            <g key={m.label}>
              <text x={0} y={y + 14} fill={PALETTE.sub} fontSize="11">{m.label}</text>
              <rect x={barX} y={y + 3} width={barW} height={14} fill={PALETTE.grid} />
              <rect x={barX} y={y + 3} width={width} height={14} fill={m.color} opacity={0.9} />
              <text x={barX + barW + 10} y={y + 14} fill={PALETTE.text} fontSize="11" fontWeight="700">
                {value.toFixed(m.max <= 1 ? 3 : m.max <= 20 ? 2 : 1)} {m.unit}
              </text>
            </g>
          );
        })}
      </svg>
      <table style={{ width: "100%", borderCollapse: "collapse", color: PALETTE.text, fontSize: 13 }}>
        <thead>
          <tr>
            <th style={cellHead}>Metric</th>
            <th style={cellHead}>Value</th>
            <th style={cellHead}>Unit / reference note</th>
          </tr>
        </thead>
        <tbody>
          <tr><td style={cell}>RMSSD</td><td style={cellNum}>{fs.rmssd_ms.toFixed(2)}</td><td style={cellSub}>ms · norm 40–80 (Shaffer &amp; Ginsberg 2017)</td></tr>
          <tr><td style={cell}>SDNN</td><td style={cellNum}>{fs.sdnn_ms.toFixed(2)}</td><td style={cellSub}>ms · &lt;50 restricted autonomic range</td></tr>
          <tr><td style={cell}>Mean HR</td><td style={cellNum}>{fs.mean_hr_bpm.toFixed(2)}</td><td style={cellSub}>bpm · &gt;90 resting suggests sympathetic dominance</td></tr>
          <tr><td style={cell}>EDA tonic (mean SCL)</td><td style={cellNum}>{fs.eda_mean_us.toFixed(3)}</td><td style={cellSub}>µS · typical 2–20 (Boucsein 2012)</td></tr>
          <tr><td style={cell}>EDA phasic index</td><td style={cellNum}>{fs.eda_phasic_index.toFixed(3)}</td><td style={cellSub}>|first diff| mean</td></tr>
          {ds && (<>
            <tr><td style={cell}>HR range (min · max)</td><td style={cellNum}>{ds.hr_bpm.min.toFixed(1)} · {ds.hr_bpm.max.toFixed(1)}</td><td style={cellSub}>bpm · SD={ds.hr_bpm.std.toFixed(2)}</td></tr>
            <tr><td style={cell}>HR 5th–95th pctile</td><td style={cellNum}>{ds.hr_bpm.p05.toFixed(1)} – {ds.hr_bpm.p95.toFixed(1)}</td><td style={cellSub}>bpm</td></tr>
            <tr><td style={cell}>EDA range (min · max)</td><td style={cellNum}>{ds.eda_us.min.toFixed(3)} · {ds.eda_us.max.toFixed(3)}</td><td style={cellSub}>µS · SD={ds.eda_us.std.toFixed(3)}</td></tr>
          </>)}
        </tbody>
      </table>
    </div>
  );
}

function Placeholder({ kind, session: _ }: { kind: ChartKind; session: StoredSession }) {
  return (
    <div style={{ background: PALETTE.bg, padding: 28, color: PALETTE.sub, textAlign: "center", borderRadius: 6 }}>
      Chart renderer for <code>{kind}</code> is scheduled for v2. The data is present in the analysis JSON; download the analysis via view 1 to inspect programmatically.
    </div>
  );
}

function Empty({ msg }: { msg: string }) {
  return <div style={{ background: PALETTE.bg, padding: 28, color: PALETTE.sub, textAlign: "center" }}>{msg}</div>;
}

function EDRQualityAudit({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const edr = session.extended?.edr_proxy;
  const q = edr?.quality;
  if (!edr || !q) return <Empty msg="No respiration-proxy quality bundle is available for this session" />;

  const overall = q.overall_confidence ?? q.signal_confidence ?? 0;
  const rows = [
    { label: "Signal confidence", value: q.signal_confidence ?? 0, note: "Duration, usable cycles, rhythm stability, and plausible rate." },
    { label: "Source confidence", value: q.source_confidence ?? 0, note: "How strong the underlying RR provenance is." },
    { label: "Cycle pairing", value: q.paired_cycle_fraction ?? 0, note: "How many peaks can be paired into rough inhale-exhale cycles." },
    { label: "Rhythm stability", value: q.interval_cv != null ? Math.max(0, 1 - q.interval_cv) : 0, note: "Breath-interval regularity, treated cautiously." },
  ];
  const pad = 34;
  const top = 82;
  const rowGap = 52;
  const barW = width - 320;
  const verdictColor = overall >= 0.8 ? PALETTE.good : overall >= 0.6 ? PALETTE.resp : overall >= 0.4 ? PALETTE.warn : PALETTE.bad;
  const note = edr.rr_source_note ?? session.result.feature_summary.rr_source_note ?? "RR provenance note unavailable.";
  const summary = [
    `Duration ${fmtMaybe(q.duration_s, 1)} s`,
    `${q.peak_count} peaks`,
    `${q.trough_count} troughs`,
    `${q.usable_breath_count} usable intervals`,
    edr.mean_rpm != null ? `mean ${edr.mean_rpm.toFixed(1)} RPM` : "mean RPM unavailable",
  ].join(" · ");

  return (
    <svg width={width} height={height} role="img" aria-label="Respiration proxy quality audit">
      <rect width={width} height={height} fill={PALETTE.bg} />
      <text x={pad} y={26} fill={PALETTE.text} fontSize="14" fontWeight="700">Respiration-proxy quality audit</text>
      <text x={pad} y={48} fill={PALETTE.sub} fontSize="11">{summary}</text>
      <text x={pad} y={68} fill={PALETTE.sub} fontSize="11">{note}</text>
      <rect x={width - 170} y={18} width={136} height={42} rx={8} fill={verdictColor} opacity={0.16} stroke={verdictColor} />
      <text x={width - 158} y={35} fill={verdictColor} fontSize="11" fontWeight="700">Overall confidence</text>
      <text x={width - 158} y={52} fill={PALETTE.text} fontSize="16" fontWeight="700">
        {Math.round(overall * 100)}% · {(q.verdict ?? "unknown").toUpperCase()}
      </text>
      {rows.map((row, i) => {
        const y = top + i * rowGap;
        const pct = Math.max(0, Math.min(1, row.value));
        return (
          <g key={row.label}>
            <text x={pad} y={y} fill={PALETTE.text} fontSize="12" fontWeight="600">{row.label}</text>
            <text x={pad} y={y + 15} fill={PALETTE.sub} fontSize="10">{row.note}</text>
            <rect x={220} y={y - 12} width={barW} height={14} rx={7} fill={PALETTE.grid} />
            <rect x={220} y={y - 12} width={barW * pct} height={14} rx={7} fill={verdictColor} />
            <text x={220 + barW + 10} y={y} fill={PALETTE.text} fontSize="11">{Math.round(pct * 100)}%</text>
          </g>
        );
      })}
      <line x1={pad} y1={height - 78} x2={width - pad} y2={height - 78} stroke={PALETTE.grid} />
      <text x={pad} y={height - 56} fill={PALETTE.text} fontSize="11" fontWeight="700">How to use this page</text>
      <text x={pad} y={height - 38} fill={PALETTE.sub} fontSize="11">
        Use strong or usable ratings as permission to reason carefully from respiration rate and RSA.
      </text>
      <text x={pad} y={height - 22} fill={PALETTE.sub} fontSize="11">
        Use weak or insufficient ratings as a warning not to infer fine breath-shape or overstate room-by-room stress from this proxy alone.
      </text>
    </svg>
  );
}

function fmtMaybe(value: number | null | undefined, digits = 0) {
  return value == null || !Number.isFinite(value) ? "unavailable" : value.toFixed(digits);
}

function EDRRespiration({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const w = session.extended?.windowed;
  const edrProxy = session.extended?.edr_proxy;
  if (!w || w.t_s.length < 2) return <Empty msg="Not enough windows for respiration trace" />;

  const rpm = w.mean_rpm;
  const rsa = w.rsa_amplitude;
  const t = w.t_s;
  const edrT = edrProxy?.time_s ?? [];
  const edrY = edrProxy?.signal ?? [];
  const rrSource = edrProxy?.rr_source ?? session.result.feature_summary.rr_source ?? "none";
  const edrPeaks = new Set((edrProxy?.peak_times_s ?? []).map((v) => Number(v.toFixed(3))));
  const edrTroughs = new Set((edrProxy?.trough_times_s ?? []).map((v) => Number(v.toFixed(3))));

  // Filter out nulls for scaling
  const validRpm = rpm.filter((v): v is number => v != null);
  const validRsa = rsa.filter((v): v is number => v != null);
  const hasProxy = edrT.length > 2 && edrY.length === edrT.length;
  if (!hasProxy && validRpm.length < 2 && validRsa.length < 2) return <Empty msg="EDR could not be computed (recording too short or too few beats)" />;

  const pad = 40;
  const W = width - pad * 2;
  const panelGap = 18;
  const panelCount = hasProxy ? 3 : 2;
  const proxyNoteGap = hasProxy ? 30 : 0;
  const hPanel = (height - pad * 2 - panelGap * (panelCount - 1) - proxyNoteGap) / panelCount;
  const tMin = hasProxy ? edrT[0] : t[0];
  const tMax = hasProxy ? edrT[edrT.length - 1] : t[t.length - 1];
  const toX = (tv: number) => pad + ((tv - tMin) / (tMax - tMin || 1)) * W;

  // EDR waveform panel (top)
  const edrTop = pad;
  const validEdr = hasProxy ? edrY.filter((v): v is number => Number.isFinite(v)) : [];
  const edrMin = validEdr.length > 0 ? Math.min(...validEdr) : -1;
  const edrMax = validEdr.length > 0 ? Math.max(...validEdr) : 1;
  const toYEdR = (v: number) => edrTop + ((edrMax - v) / (edrMax - edrMin || 1)) * hPanel;
  const edrSegs: string[] = [];
  if (hasProxy) {
    edrSegs.push(
      edrT.map((tv, i) => `${i === 0 ? "M" : "L"}${toX(tv).toFixed(1)},${toYEdR(edrY[i]).toFixed(1)}`).join(" ")
    );
  }

  // RPM panel (top)
  const rpmTop = hasProxy ? pad + hPanel + panelGap + proxyNoteGap : pad;
  const rpmMin = validRpm.length > 0 ? Math.min(...validRpm) * 0.9 : 0;
  const rpmMax = validRpm.length > 0 ? Math.max(...validRpm) * 1.1 : 30;
  const toYRpm = (v: number) => rpmTop + ((rpmMax - v) / (rpmMax - rpmMin || 1)) * hPanel;
  const rpmSegs: string[] = [];
  let curSeg = "";
  for (let i = 0; i < t.length; i++) {
    if (rpm[i] == null) { if (curSeg) { rpmSegs.push(curSeg); curSeg = ""; } continue; }
    const cmd = `${!curSeg ? "M" : "L"}${toX(t[i]).toFixed(1)},${toYRpm(rpm[i]!).toFixed(1)}`;
    curSeg = curSeg ? curSeg + " " + cmd : cmd;
  }
  if (curSeg) rpmSegs.push(curSeg);

  // RSA panel (bottom)
  const rsaTop = rpmTop + hPanel + panelGap;
  const rsaMin = validRsa.length > 0 ? Math.min(...validRsa) * 0.9 : 0;
  const rsaMax = validRsa.length > 0 ? Math.max(...validRsa) * 1.1 : 30;
  const toYRsa = (v: number) => rsaTop + ((rsaMax - v) / (rsaMax - rsaMin || 1)) * hPanel;
  const rsaSegs: string[] = [];
  curSeg = "";
  for (let i = 0; i < t.length; i++) {
    if (rsa[i] == null) { if (curSeg) { rsaSegs.push(curSeg); curSeg = ""; } continue; }
    const cmd = `${!curSeg ? "M" : "L"}${toX(t[i]).toFixed(1)},${toYRsa(rsa[i]!).toFixed(1)}`;
    curSeg = curSeg ? curSeg + " " + cmd : cmd;
  }
  if (curSeg) rsaSegs.push(curSeg);

  // Normal breathing band (12-20 RPM)
  const rpmBandTop = toYRpm(Math.min(20, rpmMax));
  const rpmBandBot = toYRpm(Math.max(12, rpmMin));
  const rrSourceLabel = rrSource === "native_polar"
    ? "native Polar RR"
    : rrSource === "derived_from_ecg"
      ? "raw-ECG-derived RR"
      : rrSource === "derived_from_bpm"
        ? "BPM-derived RR surrogate"
        : rrSource.replace(/_/g, " ");

  return (
	    <svg width={width} height={height} role="img" aria-label="RR-derived respiration proxy">
	      <rect width={width} height={height} fill={PALETTE.bg} />
      <EventLinesSeconds session={session} xMin={tMin} xMax={tMax} toX={toX} y1={pad} y2={height - 24} width={width} />
        {/* EDR waveform panel */}
      {hasProxy && (
        <>
          <text x={pad} y={edrTop - 8} fill={PALETTE.text} fontSize="12" fontWeight="600">EDR proxy waveform (RR-derived)</text>
          <text x={pad + 210} y={edrTop - 8} fill={PALETTE.sub} fontSize="10">
            Source: {rrSourceLabel}
          </text>
          {edrSegs.map((path, i) => <path key={`edr-${i}`} d={path} stroke={PALETTE.accent} strokeWidth={1.8} fill="none" />)}
          {edrT.map((tv, i) => {
            const key = Number(tv.toFixed(3));
            if (!edrPeaks.has(key) && !edrTroughs.has(key)) return null;
            return (
              <circle
                key={`edr-mark-${i}`}
                cx={toX(tv)}
                cy={toYEdR(edrY[i])}
                r={edrPeaks.has(key) ? 3.1 : 2.5}
                fill={edrPeaks.has(key) ? PALETTE.resp : PALETTE.warn}
                stroke={PALETTE.text}
                strokeWidth={0.8}
              />
            );
          })}
          <text x={pad} y={edrTop + hPanel + 16} fill={PALETTE.sub} fontSize="9">
            Purple dots = inferred inhalation peaks; amber dots = inferred troughs. This is a respiration proxy, not a direct airflow trace.
          </text>
          <line x1={pad} y1={edrTop + hPanel} x2={pad + W} y2={edrTop + hPanel} stroke={PALETTE.grid} />
        </>
      )}
	      {/* RPM panel */}
      <text x={pad} y={rpmTop - 8} fill={PALETTE.resp} fontSize="12" fontWeight="600">Breathing rate (RPM)</text>
      <rect x={pad} y={rpmBandTop} width={W} height={Math.max(0, rpmBandBot - rpmBandTop)} fill={PALETTE.resp} opacity={0.08} />
      <text x={pad + W - 100} y={rpmBandTop + 14} fill={PALETTE.sub} fontSize="10">12–20 RPM normal</text>
      {rpmSegs.map((path, i) => <path key={`rpm-${i}`} d={path} stroke={PALETTE.resp} strokeWidth={2} fill="none" />)}
      <text x={6} y={rpmTop + 6} fill={PALETTE.sub} fontSize="10">{rpmMax.toFixed(0)}</text>
      <text x={6} y={rpmTop + hPanel} fill={PALETTE.sub} fontSize="10">{rpmMin.toFixed(0)}</text>
      <line x1={pad} y1={rpmTop + hPanel} x2={pad + W} y2={rpmTop + hPanel} stroke={PALETTE.grid} />
      {/* RSA panel */}
      <text x={pad} y={rsaTop - 8} fill={PALETTE.hr} fontSize="12" fontWeight="600">RSA amplitude (vagal tone proxy)</text>
      {rsaSegs.map((path, i) => <path key={`rsa-${i}`} d={path} stroke={PALETTE.hr} strokeWidth={2} fill="none" />)}
      <text x={6} y={rsaTop + 6} fill={PALETTE.sub} fontSize="10">{rsaMax.toFixed(1)}</text>
      <text x={6} y={rsaTop + hPanel} fill={PALETTE.sub} fontSize="10">{rsaMin.toFixed(1)}</text>
      <line x1={pad} y1={rsaTop + hPanel} x2={pad + W} y2={rsaTop + hPanel} stroke={PALETTE.grid} />
      {/* Time axis */}
      <text x={pad} y={height - 5} fill={PALETTE.sub} fontSize="10">{tMin.toFixed(0)} s</text>
      <text x={pad + W - 40} y={height - 5} fill={PALETTE.sub} fontSize="10">{tMax.toFixed(0)} s</text>
    </svg>
  );
}

function StressTimeline({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const w = session.extended?.windowed;
  if (!w || w.t_s.length < 2) return <Empty msg="Not enough windows for stress trajectory" />;

  const t = w.t_s;
  const stress = w.stress_v2 ?? w.stress;
  const channels = w.stress_v2
    ? [
        { values: w.v2_hr_contribution ?? [], color: PALETTE.hr, label: "HR" },
        { values: w.v2_eda_contribution ?? [], color: PALETTE.eda, label: "EDA tonic" },
        { values: w.v2_phasic_contribution ?? [], color: PALETTE.warn, label: "EDA phasic" },
        { values: w.v2_vagal_contribution ?? [], color: PALETTE.bad, label: "Vagal deficit" },
        { values: w.v2_sympathovagal_contribution ?? [], color: "#7C9CFF", label: "LF_nu balance" },
        { values: w.v2_rigidity_contribution ?? [], color: "#C26BFF", label: "SD1/SD2 rigidity" },
        { values: w.v2_rsa_contribution ?? [], color: PALETTE.resp, label: "RSA deficit" },
      ]
    : [
        { values: w.hr_contribution, color: PALETTE.hr, label: "HR" },
        { values: w.eda_contribution, color: PALETTE.eda, label: "EDA" },
        { values: w.hrv_contribution, color: PALETTE.bad, label: "HRV deficit" },
        { values: w.rsa_contribution, color: PALETTE.resp, label: "RSA deficit" },
      ];

  const pad = 44;
  const W = width - pad * 2;
  const H = height - pad * 2 - EVENT_LABEL_BAND;
  const tMin = t[0], tMax = t[t.length - 1];
  const toX = (tv: number) => pad + ((tv - tMin) / (tMax - tMin || 1)) * W;
  const toY = (v: number) => pad + H - (Math.min(v, 1.0) * H);

  // Compute cumulative stacks per time point
  const stacks: number[][] = channels.map(() => new Array(t.length).fill(0));
  for (let i = 0; i < t.length; i++) {
    let cumulative = 0;
    for (let c = 0; c < channels.length; c++) {
      const value = channels[c].values[i];
      stacks[c][i] = cumulative;
      cumulative += typeof value === "number" && Number.isFinite(value) ? value : 0;
    }
  }

  // Build SVG area paths for each channel (bottom-to-top stacking)
  const areaPaths = channels.map((ch, c) => {
    const topPts = t.map((tv, i) => {
      const value = ch.values[i];
      const y = stacks[c][i] + (typeof value === "number" && Number.isFinite(value) ? value : 0);
      return `${toX(tv).toFixed(1)},${toY(y).toFixed(1)}`;
    });
    const botPts = t.map((tv, i) => `${toX(tv).toFixed(1)},${toY(stacks[c][i]).toFixed(1)}`).reverse();
    return `M${topPts.join(" L")} L${botPts.join(" L")} Z`;
  });

  // Stress composite line (total)
  const stressLine = t.map((tv, i) => `${i === 0 ? "M" : "L"}${toX(tv).toFixed(1)},${toY(stress[i]).toFixed(1)}`).join(" ");
  const peakIndex = maxIndex(stress);
  const peak = stress[peakIndex] ?? 0;
  const legendStep = Math.max(84, Math.floor((W - 90) / (channels.length + 1)));

  // Reference band boundaries
  const lowY = toY(0.25);
  const highY = toY(0.50);

  return (
	    <svg width={width} height={height} role="img" aria-label="Stress composite trajectory">
	      <rect width={width} height={height} fill={PALETTE.bg} />
      <EventLinesSeconds session={session} xMin={tMin} xMax={tMax} toX={toX} y1={pad} y2={pad + H + EVENT_LABEL_BAND - 2} width={width} />

	      {/* Reference bands */}
      <rect x={pad} y={pad} width={W} height={highY - pad} fill={PALETTE.bad} opacity={0.06} />
      <rect x={pad} y={lowY} width={W} height={pad + H - lowY} fill={PALETTE.good} opacity={0.06} />

      {/* Band labels */}
      <text x={pad + 4} y={highY - 4} fill={PALETTE.bad} fontSize="9" opacity={0.7}>elevated (0.50+)</text>
      <text x={pad + 4} y={lowY + 12} fill={PALETTE.good} fontSize="9" opacity={0.7}>low (&lt;0.25)</text>

      {/* Reference lines */}
      <line x1={pad} y1={lowY} x2={pad + W} y2={lowY} stroke={PALETTE.good} strokeWidth={1} strokeDasharray="4,4" opacity={0.5} />
      <line x1={pad} y1={highY} x2={pad + W} y2={highY} stroke={PALETTE.bad} strokeWidth={1} strokeDasharray="4,4" opacity={0.5} />

      {/* Stacked area fills */}
      {areaPaths.map((d, i) => (
        <path key={channels[i].label} d={d} fill={channels[i].color} opacity={0.35} />
      ))}

      {/* Total stress line */}
      <path d={stressLine} stroke={PALETTE.text} strokeWidth={2} fill="none" />
      <circle cx={toX(t[peakIndex])} cy={toY(peak)} r={4.5} fill={PALETTE.text} stroke={PALETTE.bg} strokeWidth={1.5} />
      <text x={labelX(toX(t[peakIndex]), width, 112)} y={Math.max(18, toY(peak) - 8)} fill={PALETTE.text} fontSize="10" fontWeight="700">
        peak stress {peak.toFixed(3)}
      </text>

      {/* Legend */}
      {channels.map((ch, i) => (
        <g key={ch.label}>
          <rect x={pad + i * legendStep} y={height - 18} width={10} height={10} fill={ch.color} opacity={0.7} />
          <text x={pad + i * legendStep + 14} y={height - 9} fill={PALETTE.sub} fontSize="10">{ch.label}</text>
        </g>
      ))}
      <rect x={pad + channels.length * legendStep} y={height - 18} width={10} height={10} fill={PALETTE.text} opacity={0.7} />
      <text x={pad + channels.length * legendStep + 14} y={height - 9} fill={PALETTE.sub} fontSize="10">Total</text>

      {/* Axes */}
      <line x1={pad} y1={pad} x2={pad} y2={pad + H} stroke={PALETTE.grid} />
      <line x1={pad} y1={pad + H} x2={pad + W} y2={pad + H} stroke={PALETTE.grid} />
      <text x={4} y={pad + 6} fill={PALETTE.sub} fontSize="10">1.0</text>
      <text x={4} y={toY(0.5) + 4} fill={PALETTE.sub} fontSize="10">0.5</text>
      <text x={4} y={pad + H + 4} fill={PALETTE.sub} fontSize="10">0.0</text>
      <text x={pad} y={pad + H + 14} fill={PALETTE.sub} fontSize="10">{tMin.toFixed(0)} s</text>
      <text x={pad + W - 30} y={pad + H + 14} fill={PALETTE.sub} fontSize="10">{tMax.toFixed(0)} s</text>

      {/* Title */}
      <text x={pad} y={20} fill={PALETTE.text} fontSize="12" fontWeight="600">
        {w.stress_v2 ? "Stress v2 composite (windowed)" : "Stress composite (windowed)"}
      </text>
      <text x={pad + 220} y={20} fill={PALETTE.sub} fontSize="10">
        mean={stress.length > 0 ? (stress.reduce((a, b) => a + b, 0) / stress.length).toFixed(3) : "—"}
        {" "}peak={stress.length > 0 ? peak.toFixed(3) : "—"}
      </text>
    </svg>
  );
}

function IntervalArousalProfile({ session, width, height }: { session: StoredSession; width: number; height: number }) {
  const rows = intervalArousalRows(session);
  if (rows.length === 0) return <Empty msg="No room intervals available for arousal profile" />;
  const padL = 70;
  const padR = 30;
  const padT = 44;
  const padB = 86;
  const W = width - padL - padR;
  const H = height - padT - padB;
  const minVal = Math.min(-0.25, ...rows.map((row) => row.arousal));
  const maxVal = Math.max(0.25, ...rows.map((row) => row.arousal));
  const maxAbs = Math.max(Math.abs(minVal), Math.abs(maxVal), 0.25);
  const yMin = -maxAbs;
  const yMax = maxAbs;
  const zeroY = padT + ((yMax - 0) / (yMax - yMin || 1)) * H;
  const barGap = 14;
  const barW = Math.max(22, (W - barGap * (rows.length - 1)) / rows.length);
  const toY = (v: number) => padT + ((yMax - v) / (yMax - yMin || 1)) * H;
  return (
    <svg width={width} height={height} role="img" aria-label="Stress v2 interval arousal profile">
      <rect width={width} height={height} fill={PALETTE.bg} />
      <text x={padL} y={22} fill={PALETTE.text} fontSize="12" fontWeight="600">Stress v2 interval arousal profile</text>
      <text x={padL + 220} y={22} fill={PALETTE.sub} fontSize="10">0 = participant baseline, positive = above baseline, negative = below baseline</text>
      <line x1={padL} y1={zeroY} x2={padL + W} y2={zeroY} stroke={PALETTE.text} strokeWidth={1.4} />
      <line x1={padL} y1={padT} x2={padL} y2={padT + H} stroke={PALETTE.grid} />
      {[yMax, yMax / 2, 0, yMin / 2, yMin].map((tick) => (
        <g key={tick}>
          <line x1={padL} y1={toY(tick)} x2={padL + W} y2={toY(tick)} stroke={PALETTE.grid} strokeDasharray="3,3" opacity={0.55} />
          <text x={8} y={toY(tick) + 4} fill={PALETTE.sub} fontSize="10">{tick >= 0 ? "+" : ""}{tick.toFixed(2)}</text>
        </g>
      ))}
      {rows.map((row, i) => {
        const x = padL + i * (barW + barGap);
        const y = toY(row.arousal);
        const top = Math.min(y, zeroY);
        const barH = Math.max(2, Math.abs(zeroY - y));
        const positive = row.arousal >= 0;
        const color = positive ? PALETTE.bad : PALETTE.good;
        return (
          <g key={row.key}>
            <rect x={x} y={top} width={barW} height={barH} rx={4} fill={color} opacity={0.9} />
            <text x={x + barW / 2} y={positive ? top - 8 : top + barH + 14} textAnchor="middle" fill={PALETTE.text} fontSize="10" fontWeight="700">
              {row.arousal >= 0 ? "+" : ""}{row.arousal.toFixed(3)}
            </text>
            <text x={x + barW / 2} y={height - 48} textAnchor="middle" fill={PALETTE.text} fontSize="11" fontWeight="700">
              {row.label}
            </text>
            <text x={x + barW / 2} y={height - 34} textAnchor="middle" fill={PALETTE.sub} fontSize="10">
              {row.driver}
            </text>
            <text x={x + barW / 2} y={height - 20} textAnchor="middle" fill={PALETTE.sub} fontSize="10">
              v2 {row.stressV2.toFixed(3)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function EventLinesMs({
  session, t0, t1, toX, y1, y2, width,
}: {
  session: StoredSession;
  t0: number;
  t1: number;
  toX: (t: number) => number;
  y1: number;
  y2: number;
  width: number;
}) {
  const events = sessionEvents(session).filter((e) => e.utc_ms >= t0 && e.utc_ms <= t1);
  if (events.length === 0) return null;
  return (
    <g aria-label="Event markers">
      {events.map((event, i) => {
        const x = toX(event.utc_ms);
        return (
          <g key={`${event.event_code}-${event.utc_ms}-${i}`}>
            <line x1={x} y1={y1} x2={x} y2={y2 - 20} stroke={PALETTE.accent} strokeWidth={1.2} strokeDasharray="4,3" opacity={0.78} />
            <EventLetter x={x} y={y2 - 11} width={width} letter={eventLetter(session, event.event_code)} offset={i % 2} />
          </g>
        );
      })}
    </g>
  );
}

function EventLinesSeconds({
  session, xMin, xMax, toX, y1, y2, width,
}: {
  session: StoredSession;
  xMin: number;
  xMax: number;
  toX: (t: number) => number;
  y1: number;
  y2: number;
  width: number;
}) {
  const origin = sessionTimeOriginMs(session);
  const events = sessionEvents(session)
    .map((event) => ({ ...event, t_s: eventSecond(event.utc_ms, origin, xMin, xMax) }))
    .filter((event) => event.t_s >= xMin && event.t_s <= xMax);
  if (events.length === 0) return null;
  return (
    <g aria-label="Event markers">
      {events.map((event, i) => {
        const x = toX(event.t_s);
        return (
          <g key={`${event.event_code}-${event.utc_ms}-${i}`}>
            <line x1={x} y1={y1} x2={x} y2={y2 - 20} stroke={PALETTE.accent} strokeWidth={1.2} strokeDasharray="4,3" opacity={0.78} />
            <EventLetter x={x} y={y2 - 11} width={width} letter={eventLetter(session, event.event_code)} offset={i % 2} />
          </g>
        );
      })}
    </g>
  );
}

function EventLetter({
  x, y, width, letter, offset,
}: {
  x: number;
  y: number;
  width: number;
  letter: string;
  offset: number;
}) {
  const cx = Math.max(14, Math.min(width - 14, x));
  const cy = y + offset * 13;
  return (
    <g aria-label={`Event ${letter}`}>
      <circle cx={cx} cy={cy} r={8.5} fill={EVENT_LETTER_COLOR} stroke="#111" strokeWidth={1.2} />
      <text x={cx} y={cy + 3.6} textAnchor="middle" fill="#111" fontSize="10" fontWeight="900">
        {letter}
      </text>
    </g>
  );
}

function sessionTimeOriginMs(session: StoredSession): number | null {
  const first = session.extended?.cleaned_timeseries?.find((p) => typeof p.timestamp_ms === "number");
  return typeof first?.timestamp_ms === "number" ? first.timestamp_ms : null;
}

function intervalArousalRows(session: StoredSession): Array<{
  key: string;
  label: string;
  arousal: number;
  stressV2: number;
  driver: string;
}> {
  const intervals = sessionEventIntervals(session);
  const windowed = session.extended?.windowed;
  if (!windowed || intervals.length === 0) return [];
  const origin = sessionTimeOriginMs(session);
  if (origin == null) return [];
  return intervals
    .map((interval) => {
      const onsetS = (interval.onsetMs - origin) / 1000;
      const offsetS = (interval.offsetMs - origin) / 1000;
      const idx = windowed.t_s
        .map((t, i) => (t >= onsetS && t <= offsetS ? i : -1))
        .filter((i) => i >= 0);
      if (idx.length === 0) return null;
      const arousal = meanOf(idx.map((i) => windowed.arousal_index?.[i]));
      const stressV2 = meanOf(idx.map((i) => windowed.stress_v2?.[i]));
      if (arousal == null || stressV2 == null) return null;
      return {
        key: interval.key,
        label: interval.label,
        arousal,
        stressV2,
        driver: dominantDriverLabel(windowed, idx),
      };
    })
    .filter((row): row is { key: string; label: string; arousal: number; stressV2: number; driver: string } => row !== null);
}

function dominantDriverLabel(sessionWindowed: NonNullable<StoredSession["extended"]>["windowed"], idx: number[]): string {
  const specs = [
    { label: "HR", values: sessionWindowed?.v2_hr_contribution },
    { label: "EDA tonic", values: sessionWindowed?.v2_eda_contribution },
    { label: "EDA phasic", values: sessionWindowed?.v2_phasic_contribution },
    { label: "vagal deficit", values: sessionWindowed?.v2_vagal_contribution },
    { label: "LF_nu", values: sessionWindowed?.v2_sympathovagal_contribution },
    { label: "rigidity", values: sessionWindowed?.v2_rigidity_contribution },
    { label: "RSA", values: sessionWindowed?.v2_rsa_contribution },
  ];
  const rows = specs
    .map((spec) => ({ label: spec.label, mean: meanOf(idx.map((i) => spec.values?.[i])) }))
    .filter((row): row is { label: string; mean: number } => row.mean != null)
    .sort((a, b) => b.mean - a.mean);
  return rows[0]?.label ?? "mixed";
}

function meanOf(values: Array<number | null | undefined>): number | null {
  const ys = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (ys.length === 0) return null;
  return ys.reduce((sum, v) => sum + v, 0) / ys.length;
}

function eventSecond(utcMs: number, originMs: number | null, xMin: number, xMax: number): number {
  const relativeS = utcMs / 1000;
  if (relativeS >= xMin && relativeS <= xMax) return relativeS;
  return originMs == null ? relativeS : (utcMs - originMs) / 1000;
}

function maxIndex(values: number[]): number {
  if (values.length === 0) return 0;
  let best = 0;
  for (let i = 1; i < values.length; i++) {
    if (values[i] > values[best]) best = i;
  }
  return best;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

function labelX(x: number, width: number, labelWidth: number): number {
  return Math.max(8, Math.min(x + 8, width - labelWidth));
}

const cellHead: React.CSSProperties = { textAlign: "left", padding: "8px 10px", color: PALETTE.hr, borderBottom: `1px solid ${PALETTE.grid}`, fontWeight: 600 };
const cell: React.CSSProperties = { padding: "8px 10px", borderBottom: `1px solid ${PALETTE.grid}` };
const cellNum: React.CSSProperties = { ...cell, fontFamily: "ui-monospace, Menlo, monospace", color: PALETTE.text };
const cellSub: React.CSSProperties = { ...cell, color: PALETTE.sub, fontSize: 12 };
