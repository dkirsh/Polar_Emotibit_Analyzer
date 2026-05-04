import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getSession, StoredSession } from "../api";
import { PALETTE } from "../analytics/chartPalette";
import { EventInterval, sessionEventIntervals } from "../analytics/eventIntervals";

type MetricKey = "arousal" | "stress";

type RoomMetric = {
  n: number;
  mean: number | null;
  sd: number | null;
  values: number[];
};

type RoomRow = {
  interval: EventInterval;
  seconds: number;
  arousal: RoomMetric;
  stress: RoomMetric;
};

type PairwiseDifference = {
  left: string;
  right: string;
  metric: MetricKey;
  p: number | null;
  d: number | null;
};

const CHART_W = 1120;
const CHART_H = 640;
const AROUSAL_COLOR = "#00C896";
const STRESS_COLOR = "#E8872A";

export const RoomSummaryPage: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [session, setSession] = useState<StoredSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    setError(null);
    getSession(sessionId).then(setSession).catch((e) => setError((e as Error).message));
  }, [sessionId]);

  const rows = useMemo(() => (session ? roomSummaryRows(session) : []), [session]);
  const comparisons = useMemo(() => significantRoomDifferences(rows), [rows]);

  if (error) return (
    <main className="page">
      <div className="error-banner">{error}</div>
      <Link to="/" style={{ color: "#00C896" }}>Home</Link>
    </main>
  );
  if (!session) return <main className="page"><div className="loading-panel">Reading saved analysis session...</div></main>;

  return (
    <main className="page room-summary-page" role="main" aria-label="Room marker summary">
      <nav aria-label="Breadcrumb" style={{ marginBottom: 14, display: "flex", gap: 16, alignItems: "center", fontSize: 13 }}>
        <Link to="/" style={{ color: "#00C896" }}>Home</Link>
        <span style={{ color: "#6B6B6B" }}>/</span>
        <Link to={`/results/${encodeURIComponent(session.session_id)}`} style={{ color: "#00C896" }}>Cover</Link>
        <span style={{ color: "#6B6B6B" }}>/</span>
        <span style={{ color: "#6B6B6B" }}>Room summary</span>
      </nav>

      <div className="identity-bar" role="banner" aria-label="Session identity">
        <div className="session-line">
          Session {session.session_id} · Subject {session.subject_id} · {session.session_date}
          {session.operator ? ` · ${session.operator}` : ""}
        </div>
        <div className="meta-line">
          Mean arousal and Stress V2 by room marker · p and d compare room pairs
        </div>
      </div>

      <div className="chart-frame large">
        <RoomSummaryChart rows={rows} comparisons={comparisons} />
      </div>
    </main>
  );
};

function roomSummaryRows(session: StoredSession): RoomRow[] {
  const intervals = sessionEventIntervals(session);
  const roomIntervals = intervals.filter((i) => /^room\d*$/i.test(i.key));
  const selected = roomIntervals.length > 0
    ? roomIntervals
    : intervals.filter((i) => i.key.toLowerCase() !== "baseline");
  const windowed = session.extended?.windowed;
  const t = windowed?.t_s ?? [];
  const arousal = windowed?.arousal_index ?? [];
  const stress = windowed?.stress_v2 ?? windowed?.stress ?? [];
  const originMs = sessionStartMs(session);

  if (!windowed || t.length === 0 || originMs === null) return [];

  return selected.map((interval) => {
    const startS = (interval.onsetMs - originMs) / 1000;
    const endS = (interval.offsetMs - originMs) / 1000;
    const lo = Math.min(startS, endS);
    const hi = Math.max(startS, endS);
    return {
      interval,
      seconds: Math.max(0, hi - lo),
      arousal: metricForInterval(t, arousal, lo, hi),
      stress: metricForInterval(t, stress, lo, hi),
    };
  });
}

function sessionStartMs(session: StoredSession): number | null {
  const cleaned = session.extended?.cleaned_timeseries ?? [];
  const timestamps = cleaned
    .map((p) => p.timestamp_ms)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (timestamps.length > 0) return Math.min(...timestamps);
  const events = session.markers_summary?.event_markers ?? [];
  const eventTimes = events
    .map((p) => p.utc_ms)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  return eventTimes.length > 0 ? Math.min(...eventTimes) : null;
}

function metricForInterval(t: number[], values: Array<number | null | undefined>, lo: number, hi: number): RoomMetric {
  const selected: number[] = [];
  for (let i = 0; i < t.length; i += 1) {
    const time = t[i];
    const value = values[i];
    if (
      typeof time === "number" &&
      Number.isFinite(time) &&
      time >= lo &&
      time <= hi &&
      typeof value === "number" &&
      Number.isFinite(value)
    ) {
      selected.push(value);
    }
  }
  const stats = meanSd(selected);
  return { ...stats, values: selected };
}

function meanSd(values: number[]): { n: number; mean: number | null; sd: number | null } {
  if (values.length === 0) return { n: 0, mean: null, sd: null };
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  if (values.length < 2) return { n: values.length, mean, sd: null };
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
  return { n: values.length, mean, sd: Math.sqrt(Math.max(0, variance)) };
}

function significantRoomDifferences(rows: RoomRow[]): PairwiseDifference[] {
  const differences: PairwiseDifference[] = [];
  for (let i = 0; i < rows.length; i += 1) {
    for (let j = i + 1; j < rows.length; j += 1) {
      for (const metric of ["arousal", "stress"] as MetricKey[]) {
        const diff = compareMetrics(rows[i][metric], rows[j][metric]);
        if (diff.p !== null && diff.p < 0.05) {
          differences.push({
            left: rows[i].interval.label,
            right: rows[j].interval.label,
            metric,
            p: diff.p,
            d: diff.d,
          });
        }
      }
    }
  }
  return differences.sort((a, b) => (a.p ?? 1) - (b.p ?? 1)).slice(0, 10);
}

function compareMetrics(a: RoomMetric, b: RoomMetric): { p: number | null; d: number | null } {
  if (a.mean === null || b.mean === null || a.sd === null || b.sd === null || a.n < 2 || b.n < 2) {
    return { p: null, d: null };
  }
  const se = Math.sqrt((a.sd ** 2) / a.n + (b.sd ** 2) / b.n);
  const pooledVariance = ((a.n - 1) * a.sd ** 2 + (b.n - 1) * b.sd ** 2) / Math.max(1, a.n + b.n - 2);
  const pooledSd = Math.sqrt(Math.max(0, pooledVariance));
  const d = pooledSd > 0 ? (b.mean - a.mean) / pooledSd : null;
  if (se <= 0) return { p: null, d };
  const t = Math.abs((b.mean - a.mean) / se);
  return { p: Math.max(0, Math.min(1, 2 * (1 - normalCdf(t)))), d };
}

function normalCdf(x: number): number {
  return 0.5 * (1 + erf(x / Math.SQRT2));
}

function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * ax);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-ax * ax);
  return sign * y;
}

function RoomSummaryChart({ rows, comparisons }: { rows: RoomRow[]; comparisons: PairwiseDifference[] }) {
  if (rows.length === 0) return <div style={{ color: PALETTE.sub }}>No room-marker intervals with windowed arousal or Stress V2 data.</div>;

  const padL = 72;
  const padR = 44;
  const padT = 72;
  const padB = 164;
  const plotW = CHART_W - padL - padR;
  const plotH = CHART_H - padT - padB;
  const values = rows.flatMap((r) => [r.arousal.mean, r.stress.mean]).filter((v): v is number => v !== null);
  const minY = Math.min(-0.1, ...values);
  const maxY = Math.max(0.1, ...values);
  const roomW = plotW / rows.length;
  const barW = Math.max(10, Math.min(38, roomW * 0.26));
  const zeroY = toY(0, minY, maxY, padT, plotH);
  const sigArousal = comparisons.filter((c) => c.metric === "arousal");
  const sigStress = comparisons.filter((c) => c.metric === "stress");

  return (
    <svg width={CHART_W} height={CHART_H} role="img" aria-label="Mean arousal and stress per room marker with significant pairwise differences">
      <rect width={CHART_W} height={CHART_H} fill={PALETTE.bg} />
      <text x={padL} y={28} fill={PALETTE.text} fontSize="18" fontWeight="700">Mean arousal and Stress V2 by room marker</text>
      <text x={padL} y={50} fill={PALETTE.sub} fontSize="12">Pairwise room differences are marked when p &lt; .05; d is Cohen's d.</text>

      {[0, 0.25, 0.5, 0.75, 1, -0.25, -0.5, -0.75, -1]
        .filter((tick) => tick >= minY && tick <= maxY)
        .map((tick) => {
          const y = toY(tick, minY, maxY, padT, plotH);
          return (
            <g key={tick}>
              <line x1={padL} y1={y} x2={CHART_W - padR} y2={y} stroke={tick === 0 ? "#6B6B6B" : PALETTE.grid} strokeWidth={tick === 0 ? 1.2 : 1} />
              <text x={padL - 12} y={y + 4} textAnchor="end" fill={PALETTE.sub} fontSize="10">{tick.toFixed(2)}</text>
            </g>
          );
        })}

      <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke={PALETTE.grid} />
      <line x1={padL} y1={zeroY} x2={CHART_W - padR} y2={zeroY} stroke="#808080" strokeWidth={1.2} />

      {rows.map((row, index) => {
        const cx = padL + roomW * index + roomW / 2;
        const arousalBar = barGeometry(row.arousal.mean, cx - barW - 4, barW, minY, maxY, padT, plotH, zeroY);
        const stressBar = barGeometry(row.stress.mean, cx + 4, barW, minY, maxY, padT, plotH, zeroY);
        return (
          <g key={row.interval.key}>
            <rect x={arousalBar.x} y={arousalBar.y} width={arousalBar.w} height={arousalBar.h} rx={3} fill={AROUSAL_COLOR} />
            <rect x={stressBar.x} y={stressBar.y} width={stressBar.w} height={stressBar.h} rx={3} fill={STRESS_COLOR} />
            <text x={cx} y={padT + plotH + 24} textAnchor="middle" fill={PALETTE.text} fontSize="12" fontWeight="700">{row.interval.letter}</text>
            <text x={cx} y={padT + plotH + 42} textAnchor="middle" fill={PALETTE.sub} fontSize="11">{shortLabel(row.interval.label)}</text>
            <text x={cx} y={padT + plotH + 58} textAnchor="middle" fill={PALETTE.sub} fontSize="10">{row.seconds.toFixed(0)} s</text>
            <text x={cx - barW / 2 - 4} y={Math.min(arousalBar.y, zeroY) - 8} textAnchor="middle" fill={AROUSAL_COLOR} fontSize="10">
              {formatMean(row.arousal.mean)}
            </text>
            <text x={cx + barW / 2 + 4} y={Math.min(stressBar.y, zeroY) - 8} textAnchor="middle" fill={STRESS_COLOR} fontSize="10">
              {formatMean(row.stress.mean)}
            </text>
          </g>
        );
      })}

      <g transform={`translate(${padL}, ${CHART_H - 86})`}>
        <rect x={0} y={0} width={14} height={14} fill={AROUSAL_COLOR} rx={2} />
        <text x={22} y={12} fill={PALETTE.text} fontSize="12">Mean arousal</text>
        <rect x={142} y={0} width={14} height={14} fill={STRESS_COLOR} rx={2} />
        <text x={164} y={12} fill={PALETTE.text} fontSize="12">Stress V2</text>
        <text x={0} y={38} fill={AROUSAL_COLOR} fontSize="11">{differenceLine("Arousal", sigArousal)}</text>
        <text x={0} y={58} fill={STRESS_COLOR} fontSize="11">{differenceLine("Stress V2", sigStress)}</text>
      </g>

      <text x={CHART_W - padR} y={CHART_H - 18} textAnchor="end" fill={PALETTE.sub} fontSize="10">
        p is an approximate Welch/normal two-sample test over windowed samples.
      </text>
    </svg>
  );
}

function barGeometry(value: number | null, x: number, w: number, minY: number, maxY: number, padT: number, plotH: number, zeroY: number) {
  if (value === null) return { x, y: zeroY - 1, w, h: 2 };
  const y = toY(value, minY, maxY, padT, plotH);
  return {
    x,
    y: Math.min(y, zeroY),
    w,
    h: Math.max(2, Math.abs(zeroY - y)),
  };
}

function toY(value: number, minY: number, maxY: number, padT: number, plotH: number): number {
  return padT + ((maxY - value) / (maxY - minY || 1)) * plotH;
}

function shortLabel(label: string): string {
  return label.length > 14 ? `${label.slice(0, 13)}...` : label;
}

function formatMean(value: number | null): string {
  return value === null ? "n/a" : value.toFixed(2);
}

function formatP(value: number | null): string {
  if (value === null) return "n/a";
  if (value < 0.001) return "<.001";
  return value.toFixed(3).replace(/^0/, "");
}

function formatD(value: number | null): string {
  return value === null ? "n/a" : value.toFixed(2);
}

function differenceLine(label: string, differences: PairwiseDifference[]): string {
  if (differences.length === 0) return `${label}: no room pairs p < .05`;
  const listed = differences.slice(0, 4).map((d) => `${d.left} vs ${d.right} p=${formatP(d.p)} d=${formatD(d.d)}`);
  const suffix = differences.length > 4 ? `; +${differences.length - 4} more` : "";
  return `${label}: ${listed.join("; ")}${suffix}`;
}
