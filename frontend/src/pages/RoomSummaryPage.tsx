import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getSession, StoredSession, SummaryMetric } from "../api";
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

type ArousalPairwiseComparison = {
  left: RoomRow;
  right: RoomRow;
  meanDiff: number | null;
  p: number | null;
  d: number | null;
};

type ConditionAggregateCondition = NonNullable<StoredSession["condition_aggregate"]>["conditions"][number];
type ConditionMetricKey = "arousal_index" | "stress_v2" | "self_report_valence" | "self_report_arousal";

const CHART_W = 1120;
const CHART_H = 640;
const AROUSAL_ONLY_CHART_H = 470;
const AROUSAL_COLOR = "#00C896";
const STRESS_COLOR = "#E8872A";
const VALENCE_COLOR = "#5E7CE2";
const MIN_WINDOWS_FOR_INFERENCE = 4;

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
  const rankedRows = useMemo(() => rankedArousalRows(rows), [rows]);
  const adjacentArousalComparisons = useMemo(() => adjacentRankedArousalComparisons(rankedRows), [rankedRows]);
  const conditionRows = session?.condition_aggregate?.conditions ?? [];

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
          Room type aggregates from the Latin-square order file
        </div>
      </div>

      {conditionRows.length > 0 ? (
        <>
          <div className="chart-frame large room-summary-chart-spacer">
            <ConditionAggregateMetricChart
              rows={conditionRows}
              metric="arousal_index"
              title="Unified physiological arousal by room type"
              subtitle="Stress V2 arousal index: HR, EDA tonic/phasic, HRV vagal deficit, respiration/RSA, and balance terms where available. Higher is more aroused."
              color={AROUSAL_COLOR}
              domainZero
              digits={3}
            />
          </div>
          <div className="chart-frame large room-summary-chart-spacer">
            <ConditionAggregateMetricChart
              rows={conditionRows}
              metric="stress_v2"
              title="Stress V2 by room type"
              subtitle="Raw Stress V2 composite by room type. Higher means more stress-like physiological activation on the 0-to-1 heuristic scale."
              color={STRESS_COLOR}
              domainZero
              digits={3}
            />
          </div>
          <div className="chart-frame large room-summary-chart-spacer">
            <ConditionAggregateMetricChart
              rows={conditionRows}
              metric="self_report_valence"
              title="Self-report valence by room type"
              subtitle="Valence is read from the Order & Affect files. Higher means more positive affect."
              color={VALENCE_COLOR}
              digits={2}
            />
          </div>
          <ConditionAggregateTable rows={conditionRows} />
        </>
      ) : (
        <>
          <div className="chart-frame large room-summary-chart-spacer">
            <RankedArousalChart ranked={rankedRows} adjacentComparisons={adjacentArousalComparisons} />
          </div>
          <ArousalRankTable ranked={rankedRows} adjacentComparisons={adjacentArousalComparisons} />
          <div className="chart-frame large room-summary-chart-spacer">
            <RoomSummaryChart rows={rows} comparisons={comparisons} />
          </div>
        </>
      )}
    </main>
  );
};

function roomSummaryRows(session: StoredSession): RoomRow[] {
  const aggregateRows = conditionAggregateRows(session);
  if (aggregateRows.length > 0) return aggregateRows;

  const exactRows = exactRoomSummaryRows(session);
  if (exactRows.length > 0) return exactRows;

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

function conditionAggregateRows(session: StoredSession): RoomRow[] {
  const aggregate = session.condition_aggregate;
  if (!aggregate?.conditions?.length) return [];
  return aggregate.conditions
    .slice()
    .sort((a, b) => a.condition.localeCompare(b.condition))
    .map((condition) => {
      const interval: EventInterval = {
        key: condition.condition,
        letter: condition.condition,
        label: `Condition ${condition.condition}`,
        onsetCode: "",
        offsetCode: "",
        onsetMs: 0,
        offsetMs: 0,
      };
      return {
        interval,
        seconds: 25,
        arousal: summaryMetric(condition.arousal_index),
        stress: summaryMetric(condition.stress_v2),
      };
    });
}

function summaryMetric(metric: { n: number; mean: number | null; sd: number | null } | null | undefined): RoomMetric {
  return {
    n: metric?.n ?? 0,
    mean: metric?.mean ?? null,
    sd: metric?.sd ?? null,
    values: [],
  };
}

function conditionMetric(row: ConditionAggregateCondition, metric: ConditionMetricKey): SummaryMetric {
  const value = row[metric] as SummaryMetric | undefined;
  return value ?? emptySummaryMetric();
}

function emptySummaryMetric(): SummaryMetric {
  return { n: 0, mean: null, sd: null, min: null, max: null };
}

function rankedConditionRows(rows: ConditionAggregateCondition[], metric: ConditionMetricKey): ConditionAggregateCondition[] {
  return rows
    .filter((row) => conditionMetric(row, metric).mean !== null)
    .slice()
    .sort((a, b) => {
      const aMean = conditionMetric(a, metric).mean ?? Infinity;
      const bMean = conditionMetric(b, metric).mean ?? Infinity;
      if (aMean !== bMean) return aMean - bMean;
      return a.condition.localeCompare(b.condition);
    });
}

function exactRoomSummaryRows(session: StoredSession): RoomRow[] {
  const stats = (session.room_stats ?? []).filter((row) => /^room\d+$/i.test(row.room_key));
  const baseline = (session.room_stats ?? []).find((row) => row.room_key?.toLowerCase() === "baseline");
  const baselineStress = typeof baseline?.stress_v2 === "number" && Number.isFinite(baseline.stress_v2)
    ? baseline.stress_v2
    : null;
  if (stats.length === 0 || baselineStress === null) return [];

  return stats
    .slice()
    .sort((a, b) => a.onset_ms - b.onset_ms)
    .map((row) => {
      const visitLabel = `visit ${row.room_number}`;
      const condition = row.room_type && row.room_type !== row.room_key ? row.room_type : row.room_key;
      const label = `${condition} (${visitLabel})`;
      const arousal = typeof row.stress_v2 === "number" && Number.isFinite(row.stress_v2)
        ? clamp(2 * (row.stress_v2 - baselineStress), -1, 1)
        : null;
      const interval: EventInterval = {
        key: row.room_key,
        letter: condition,
        label,
        onsetCode: `${row.room_key}_onset`,
        offsetCode: `${row.room_key}_offset`,
        onsetMs: row.onset_ms,
        offsetMs: row.offset_ms,
      };
      return {
        interval,
        seconds: row.duration_s,
        arousal: exactMetric(arousal, row.sample_count),
        stress: exactMetric(row.stress_v2, row.sample_count),
      };
    });
}

function exactMetric(value: number | null | undefined, n: number): RoomMetric {
  return typeof value === "number" && Number.isFinite(value)
    ? { n, mean: value, sd: null, values: [value] }
    : { n: 0, mean: null, sd: null, values: [] };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
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

function rankedArousalRows(rows: RoomRow[]): RoomRow[] {
  return rows
    .filter((row) => row.arousal.mean !== null)
    .sort((a, b) => (a.arousal.mean ?? Infinity) - (b.arousal.mean ?? Infinity));
}

function adjacentRankedArousalComparisons(ranked: RoomRow[]): ArousalPairwiseComparison[] {
  return ranked.slice(0, -1).map((row, index) => {
    const next = ranked[index + 1];
    const diff = compareMetrics(row.arousal, next.arousal);
    const leftMean = row.arousal.mean;
    const rightMean = next.arousal.mean;
    return {
      left: row,
      right: next,
      meanDiff: leftMean !== null && rightMean !== null ? rightMean - leftMean : null,
      p: diff.p,
      d: diff.d,
    };
  });
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

function ConditionAggregateMetricChart({
  rows,
  metric,
  title,
  subtitle,
  color,
  domainZero = false,
  digits,
}: {
  rows: ConditionAggregateCondition[];
  metric: ConditionMetricKey;
  title: string;
  subtitle: string;
  color: string;
  domainZero?: boolean;
  digits: number;
}) {
  const ranked = rankedConditionRows(rows, metric);
  if (ranked.length === 0) return <div style={{ color: PALETTE.sub }}>No condition-level values available for this measure.</div>;

  const padL = 78;
  const padR = 40;
  const padT = 82;
  const padB = 82;
  const plotW = CHART_W - padL - padR;
  const plotH = AROUSAL_ONLY_CHART_H - padT - padB;
  const means = ranked
    .map((row) => conditionMetric(row, metric).mean)
    .filter((value): value is number => value !== null);
  const minValue = Math.min(...ranked.map((row) => {
    const rowMetric = conditionMetric(row, metric);
    return rowMetric.sd !== null && rowMetric.mean !== null ? rowMetric.mean - rowMetric.sd : rowMetric.mean ?? Infinity;
  }));
  const maxValue = Math.max(...ranked.map((row) => {
    const rowMetric = conditionMetric(row, metric);
    return rowMetric.sd !== null && rowMetric.mean !== null ? rowMetric.mean + rowMetric.sd : rowMetric.mean ?? -Infinity;
  }));
  const rawMin = Number.isFinite(minValue) ? minValue : Math.min(...means);
  const rawMax = Number.isFinite(maxValue) ? maxValue : Math.max(...means);
  const spread = Math.max(0.05, rawMax - rawMin);
  const minY = domainZero ? Math.min(0, rawMin - spread * 0.12) : rawMin - spread * 0.18;
  const maxY = domainZero ? Math.max(0, rawMax + spread * 0.12) : rawMax + spread * 0.18;
  const roomW = plotW / ranked.length;
  const barW = Math.max(28, Math.min(62, roomW * 0.5));
  const bottomY = toY(minY, minY, maxY, padT, plotH);
  const zeroY = toY(0, minY, maxY, padT, plotH);
  const baseY = domainZero && minY < 0 && maxY > 0 ? zeroY : bottomY;
  const ticks = chartTicks(minY, maxY, 5);

  return (
    <svg width={CHART_W} height={AROUSAL_ONLY_CHART_H} role="img" aria-label={title}>
      <rect width={CHART_W} height={AROUSAL_ONLY_CHART_H} fill={PALETTE.bg} />
      <text x={padL} y={30} fill={PALETTE.text} fontSize="18" fontWeight="700">{title}</text>
      <text x={padL} y={52} fill={PALETTE.sub} fontSize="12">{subtitle}</text>

      {ticks.map((tick) => {
        const y = toY(tick, minY, maxY, padT, plotH);
        return (
          <g key={tick.toFixed(4)}>
            <line x1={padL} y1={y} x2={CHART_W - padR} y2={y} stroke={Math.abs(tick) < 1e-9 ? "#808080" : PALETTE.grid} strokeWidth={Math.abs(tick) < 1e-9 ? 1.2 : 1} />
            <text x={padL - 14} y={y + 4} textAnchor="end" fill={PALETTE.sub} fontSize="10">{tick.toFixed(digits)}</text>
          </g>
        );
      })}

      <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke={PALETTE.grid} />
      <line x1={padL} y1={baseY} x2={CHART_W - padR} y2={baseY} stroke="#8A8A8A" strokeWidth={1.2} />

      {ranked.map((row, index) => {
        const rowMetric = conditionMetric(row, metric);
        const mean = rowMetric.mean ?? 0;
        const sd = rowMetric.sd;
        const cx = padL + roomW * index + roomW / 2;
        const y = toY(mean, minY, maxY, padT, plotH);
        const top = Math.min(y, baseY);
        const barH = Math.max(2, Math.abs(baseY - y));
        const sdLo = sd !== null ? toY(mean - sd, minY, maxY, padT, plotH) : null;
        const sdHi = sd !== null ? toY(mean + sd, minY, maxY, padT, plotH) : null;
        const labelY = Math.min(top - 8, padT + plotH - 4);
        return (
          <g key={row.condition}>
            <rect x={cx - barW / 2} y={top} width={barW} height={barH} rx={4} fill={color} opacity={0.94} />
            {sdLo !== null && sdHi !== null ? (
              <g>
                <line x1={cx} y1={sdHi} x2={cx} y2={sdLo} stroke={PALETTE.text} strokeWidth={1.1} opacity={0.7} />
                <line x1={cx - 7} y1={sdHi} x2={cx + 7} y2={sdHi} stroke={PALETTE.text} strokeWidth={1.1} opacity={0.7} />
                <line x1={cx - 7} y1={sdLo} x2={cx + 7} y2={sdLo} stroke={PALETTE.text} strokeWidth={1.1} opacity={0.7} />
              </g>
            ) : null}
            <text x={cx} y={labelY} textAnchor="middle" fill={color} fontSize="11" fontWeight="700">
              {formatPlain(mean, digits)}
            </text>
            <text x={cx} y={padT + plotH + 28} textAnchor="middle" fill={PALETTE.text} fontSize="14" fontWeight="800">{row.condition}</text>
            <text x={cx} y={padT + plotH + 47} textAnchor="middle" fill={PALETTE.sub} fontSize="10">n={rowMetric.n}</text>
          </g>
        );
      })}

      <text x={CHART_W - padR} y={AROUSAL_ONLY_CHART_H - 20} textAnchor="end" fill={PALETTE.sub} fontSize="10">
        Room types are sorted low to high; the highest value is on the right.
      </text>
    </svg>
  );
}

function ConditionAggregateTable({ rows }: { rows: ConditionAggregateCondition[] }) {
  const ranked = rankedConditionRows(rows, "stress_v2");
  return (
    <section className="room-summary-table" aria-label="Condition aggregate arousal and valence">
      <h2>Room type aggregate values</h2>
      {ranked.length === 0 ? (
        <p>No room type aggregates are available.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Room type</th>
              <th>Unified arousal</th>
              <th>Arousal SD</th>
              <th>Arousal n</th>
              <th>Self-report valence</th>
              <th>Valence SD</th>
              <th>Valence n</th>
              <th>Stress V2</th>
              <th>HRV RMSSD</th>
              <th>RSA amp</th>
              <th>Self-report arousal</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((row) => {
              const arousal = conditionMetric(row, "arousal_index");
              const valence = conditionMetric(row, "self_report_valence");
              const stress = row.stress_v2;
              const hrv = row.rmssd;
              const rsa = row.rsa_amplitude;
              const reportedArousal = conditionMetric(row, "self_report_arousal");
              return (
                <tr key={row.condition}>
                  <td>{row.condition}</td>
                  <td className="num">{formatSigned(arousal.mean, 3)}</td>
                  <td className="num">{formatPlain(arousal.sd, 3)}</td>
                  <td className="num">{arousal.n}</td>
                  <td className="num">{formatPlain(valence.mean, 2)}</td>
                  <td className="num">{formatPlain(valence.sd, 2)}</td>
                  <td className="num">{valence.n}</td>
                  <td className="num">{formatPlain(stress.mean, 3)}</td>
                  <td className="num">{formatPlain(hrv.mean, 1)}</td>
                  <td className="num">{formatPlain(rsa.mean, 1)}</td>
                  <td className="num">{formatPlain(reportedArousal.mean, 2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
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
        <text x={0} y={44} fill={STRESS_COLOR} fontSize="11">{differenceLine("Stress V2", sigStress)}</text>
      </g>

      <text x={CHART_W - padR} y={CHART_H - 18} textAnchor="end" fill={PALETTE.sub} fontSize="10">
        p is an approximate Welch/normal two-sample test over windowed samples.
      </text>
    </svg>
  );
}

function RankedArousalChart({
  ranked,
  adjacentComparisons,
}: {
  ranked: RoomRow[];
  adjacentComparisons: ArousalPairwiseComparison[];
}) {
  if (ranked.length === 0) return <div style={{ color: PALETTE.sub }}>No room-marker arousal data available.</div>;

  const padL = 78;
  const padR = 38;
  const padT = 78;
  const padB = 92;
  const plotW = CHART_W - padL - padR;
  const plotH = AROUSAL_ONLY_CHART_H - padT - padB;
  const values = ranked.map((row) => row.arousal.mean ?? 0);
  const maxAbs = Math.max(0.05, ...values.map((value) => Math.abs(value))) * 1.16;
  const roomW = plotW / ranked.length;
  const barW = Math.max(24, Math.min(58, roomW * 0.48));
  const zeroY = arousalY(0, maxAbs, padT, plotH);
  const ticks = [-maxAbs, -maxAbs / 2, 0, maxAbs / 2, maxAbs];
  const significantNeighbors = adjacentComparisons
    .map((comparison, index) => ({ ...comparison, index }))
    .filter((comparison) => isInferenceReady(comparison.left, comparison.right) && comparison.p !== null && comparison.p < 0.05);

  return (
    <svg width={CHART_W} height={AROUSAL_ONLY_CHART_H} role="img" aria-label="Ranked arousal by room, negative plotted upward">
      <rect width={CHART_W} height={AROUSAL_ONLY_CHART_H} fill={PALETTE.bg} />
      <text x={padL} y={30} fill={PALETTE.text} fontSize="18" fontWeight="700">Arousal by room, ranked high to low on plot</text>
      <text x={padL} y={52} fill={PALETTE.sub} fontSize="12">ERP-style polarity: negative values plot upward; brackets require p &lt; .05 and enough windows.</text>

      {ticks.map((tick) => {
        const y = arousalY(tick, maxAbs, padT, plotH);
        return (
          <g key={tick.toFixed(4)}>
            <line x1={padL} y1={y} x2={CHART_W - padR} y2={y} stroke={tick === 0 ? "#808080" : PALETTE.grid} strokeWidth={tick === 0 ? 1.2 : 1} />
            <text x={padL - 14} y={y + 4} textAnchor="end" fill={PALETTE.sub} fontSize="10">{tick.toFixed(2)}</text>
          </g>
        );
      })}

      <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke={PALETTE.grid} />
      <line x1={padL} y1={zeroY} x2={CHART_W - padR} y2={zeroY} stroke="#8A8A8A" strokeWidth={1.2} />

      {ranked.map((row, index) => {
        const mean = row.arousal.mean ?? 0;
        const cx = padL + roomW * index + roomW / 2;
        const y = arousalY(mean, maxAbs, padT, plotH);
        const top = Math.min(y, zeroY);
        const barH = Math.max(2, Math.abs(zeroY - y));
        const rank = index + 1;
        return (
          <g key={row.interval.key}>
            <rect x={cx - barW / 2} y={top} width={barW} height={barH} rx={4} fill={AROUSAL_COLOR} opacity={0.94} />
            <text x={cx} y={top - 8} textAnchor="middle" fill={AROUSAL_COLOR} fontSize="11" fontWeight="700">
              {mean.toFixed(3)}
            </text>
            <text x={cx} y={padT + plotH + 26} textAnchor="middle" fill={PALETTE.text} fontSize="12" fontWeight="800">{rank}</text>
            <text x={cx} y={padT + plotH + 44} textAnchor="middle" fill={PALETTE.text} fontSize="11" fontWeight="700">{row.interval.label}</text>
            <text x={cx} y={padT + plotH + 61} textAnchor="middle" fill={PALETTE.sub} fontSize="10">{row.interval.letter}</text>
          </g>
        );
      })}

      {significantNeighbors.map((comparison, bracketIndex) => {
        const x1 = padL + roomW * comparison.index + roomW / 2;
        const x2 = padL + roomW * (comparison.index + 1) + roomW / 2;
        const y1 = arousalY(comparison.left.arousal.mean ?? 0, maxAbs, padT, plotH);
        const y2 = arousalY(comparison.right.arousal.mean ?? 0, maxAbs, padT, plotH);
        const y = Math.max(padT + 6, Math.min(y1, y2) - 24 - (bracketIndex % 2) * 18);
        return (
          <g key={`${comparison.left.interval.key}-${comparison.right.interval.key}`}>
            <path
              d={`M${x1.toFixed(1)},${(y + 8).toFixed(1)} L${x1.toFixed(1)},${y.toFixed(1)} L${x2.toFixed(1)},${y.toFixed(1)} L${x2.toFixed(1)},${(y + 8).toFixed(1)}`}
              fill="none"
              stroke={PALETTE.text}
              strokeWidth={1.2}
            />
            <text x={(x1 + x2) / 2} y={y - 5} textAnchor="middle" fill={PALETTE.text} fontSize="10" fontWeight="700">
              p={formatP(comparison.p)}
            </text>
          </g>
        );
      })}

      <text x={CHART_W - padR} y={AROUSAL_ONLY_CHART_H - 20} textAnchor="end" fill={PALETTE.sub} fontSize="10">
        Rank 1 is highest on the plot after ERP-style negative-up polarity.
      </text>
    </svg>
  );
}

function ArousalRankTable({
  ranked,
  adjacentComparisons,
}: {
  ranked: RoomRow[];
  adjacentComparisons: ArousalPairwiseComparison[];
}) {
  return (
    <section className="room-summary-table" aria-label="Arousal rank order and adjacent differences">
      <h2>Arousal rank order and adjacent differences</h2>
      {ranked.length === 0 ? (
        <p>No rooms are available for arousal ranking.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Room</th>
              <th>Arousal</th>
              <th>n</th>
              <th>SD</th>
              <th>Next room</th>
              <th>Next arousal</th>
              <th>Next n</th>
              <th>Next SD</th>
              <th>Gap</th>
              <th>p vs next</th>
              <th>d vs next</th>
              <th>Inference</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((row, index) => {
              const comparison = adjacentComparisons[index] ?? null;
              const ready = comparison !== null && isInferenceReady(comparison.left, comparison.right);
              const significant = ready && comparison?.p !== null && comparison?.p !== undefined && comparison.p < 0.05;
              return (
              <tr key={row.interval.key}>
                <td className="num">{index + 1}</td>
                <td>{row.interval.label}</td>
                <td className="num">{formatSigned(row.arousal.mean, 3)}</td>
                <td className="num">{row.arousal.n}</td>
                <td className="num">{formatPlain(row.arousal.sd, 3)}</td>
                <td>{comparison?.right.interval.label ?? "none"}</td>
                <td className="num">{formatSigned(comparison?.right.arousal.mean ?? null, 3)}</td>
                <td className="num">{comparison?.right.arousal.n ?? "n/a"}</td>
                <td className="num">{formatPlain(comparison?.right.arousal.sd ?? null, 3)}</td>
                <td className="num">{formatSigned(comparison?.meanDiff ?? null, 3)}</td>
                <td className="num">{formatP(comparison?.p ?? null)}</td>
                <td className="num">{formatD(comparison?.d ?? null)}</td>
                <td className={significant ? "sig yes" : "sig"}>
                  {comparison ? inferenceLabel(comparison) : "n/a"}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
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

function chartTicks(minY: number, maxY: number, count: number): number[] {
  if (count <= 1 || !Number.isFinite(minY) || !Number.isFinite(maxY)) return [0];
  const step = (maxY - minY) / (count - 1 || 1);
  return Array.from({ length: count }, (_, index) => minY + step * index);
}

function arousalY(value: number, maxAbs: number, padT: number, plotH: number): number {
  return padT + ((value + maxAbs) / (maxAbs * 2 || 1)) * plotH;
}

function isInferenceReady(left: RoomRow, right: RoomRow): boolean {
  return left.arousal.n >= MIN_WINDOWS_FOR_INFERENCE && right.arousal.n >= MIN_WINDOWS_FOR_INFERENCE;
}

function inferenceLabel(comparison: ArousalPairwiseComparison): string {
  if (!isInferenceReady(comparison.left, comparison.right)) return "exploratory";
  return comparison.p !== null && comparison.p < 0.05 ? "yes" : "no";
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

function formatPlain(value: number | null, digits: number): string {
  return value === null ? "n/a" : value.toFixed(digits);
}

function formatSigned(value: number | null, digits: number): string {
  if (value === null) return "n/a";
  return value >= 0 ? `+${value.toFixed(digits)}` : value.toFixed(digits);
}

function differenceLine(label: string, differences: PairwiseDifference[]): string {
  if (differences.length === 0) return `${label}: no room pairs p < .05`;
  const listed = differences.slice(0, 4).map((d) => `${d.left} vs ${d.right} p=${formatP(d.p)} d=${formatD(d.d)}`);
  const suffix = differences.length > 4 ? `; +${differences.length - 4} more` : "";
  return `${label}: ${listed.join("; ")}${suffix}`;
}
