import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getSession, StoredSession, WindowedFeatures } from "../api";
import {
  AnalyticEntry,
  ChartKind,
  GROUP_META,
  adjacentAnalytics,
  analyticsByGroup,
  getAnalytic,
} from "../analytics/catalog";
import { ChartRenderer } from "../analytics/ChartRenderer";
import { EventInterval, sessionEventIntervals } from "../analytics/eventIntervals";
import { annotateGlossaryTerms } from "../analytics/util";

/**
 * Analytic detail page — the full presentation for a single analytic.
 * Title and caption in the writer's voice, the chart, a "What it
 * shows" paragraph, a "How to read it" paragraph, an "Architectural
 * meaning" paragraph relating the measure to cognitive-neuroscience-of-
 * architecture dependent variables, optional caveats, references, and
 * prev/next chaining within the group.
 */
export const AnalyticDetailPage: React.FC = () => {
  const { sessionId, analyticId } = useParams<{ sessionId: string; analyticId: string }>();
  const [session, setSession] = useState<StoredSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [largeChart, setLargeChart] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    setError(null);
    getSession(sessionId).then(setSession).catch((e) => setError((e as Error).message));
  }, [sessionId]);

  if (error) return (
    <main className="page">
      <div className="error-banner">{error}</div>
      <div className="notice">
        This chart can render only after the upload pipeline has saved a completed session. Replace
        {" "}<code>YOUR_SESSION_ID</code> with the actual Session ID you typed on the first screen.
      </div>
      <Link to="/" style={{ color: "#00C896" }}>← New analysis</Link>
    </main>
  );
  if (!session || !analyticId || !sessionId) return <main className="page"><div className="loading-panel">Reading saved analysis session…</div></main>;
  const a = getAnalytic(analyticId);
  if (!a) return (
    <main className="page">
      <div className="error-banner">Unknown analytic: {analyticId}</div>
      <Link to={`/results/${encodeURIComponent(sessionId)}`}>← Cover</Link>
    </main>
  );

  const meta = GROUP_META[a.group];
  const { prev, next } = adjacentAnalytics(analyticId);
  const groupHref = `/results/${encodeURIComponent(sessionId)}/group/${a.group}`;
  const groupAnalytics = analyticsByGroup(a.group);
  const displayHeading = a.question ?? a.title;
  const chartLabel = a.question ? a.title : undefined;
  const scienceCaption = captionsForAnalytic(a, session);
  const respirationSource = session.extended?.edr_proxy?.rr_source ?? session.result.feature_summary.rr_source;
  const respirationSourceNote = session.extended?.edr_proxy?.rr_source_note ?? session.result.feature_summary.rr_source_note;
  const standardChartHeight = a.chartKind === "edr_respiration"
    ? 560
    : a.chartKind === "timeseries_overlay"
      ? 620
      : 430;
  const largeChartHeight = a.chartKind === "edr_respiration"
    ? 760
    : a.chartKind === "timeseries_overlay"
      ? 820
      : 620;
  const fullWidthChartLayout = largeChart || a.chartKind === "timeseries_overlay";
  const downloadSvg = () => {
    const svg = document.querySelector<SVGSVGElement>("#chart-frame svg");
    if (!svg) return;
    const clone = svg.cloneNode(true) as SVGSVGElement;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
    clone.setAttribute("overflow", "visible");
    clone.removeAttribute("style");
    try {
      const bbox = svg.getBBox();
      const pad = 18;
      clone.setAttribute("viewBox", `${bbox.x - pad} ${bbox.y - pad} ${bbox.width + pad * 2} ${bbox.height + pad * 2}`);
      clone.setAttribute("width", `${Math.ceil(bbox.width + pad * 2)}`);
      clone.setAttribute("height", `${Math.ceil(bbox.height + pad * 2)}`);
    } catch {
      // If getBBox fails, fall back to the rendered SVG geometry.
    }
    const source = new XMLSerializer().serializeToString(clone);
    const blob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${session.session_id}_${a.id}.svg`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="page analytic-detail-page" role="main" aria-label={`Analytic: ${a.title}`}>
      <nav aria-label="Breadcrumb" style={{ marginBottom: 14, display: "flex", gap: 16, alignItems: "center", fontSize: 13 }}>
        <Link to="/" style={{ color: "#00C896" }}>Home</Link>
        <span style={{ color: "#6B6B6B" }}>/</span>
        <Link to={`/results/${encodeURIComponent(session.session_id)}`} style={{ color: "#00C896" }}>Cover</Link>
        <span style={{ color: "#6B6B6B" }}>/</span>
        <Link to={groupHref} style={{ color: meta.hue }}>{meta.title}</Link>
        <span style={{ color: "#6B6B6B" }}>/</span>
        <span style={{ color: "#6B6B6B" }}>{String(a.order).padStart(2, "0")}</span>
        <span style={{ flex: 1 }} />
        <Link to="/" style={{ color: "#00C896", fontWeight: 700 }}>Add / replace files</Link>
      </nav>

      <div className="analytic-layout with-side-nav">
        <aside className="analytic-side-nav" aria-label={meta.title}>
          <Link
            to={`/results/${encodeURIComponent(session.session_id)}/group/${a.group}`}
            className="analytic-side-title"
          >
            {meta.title}
          </Link>
          <nav aria-label={`${meta.title} graphs`}>
            {groupAnalytics.map((item) => (
              <Link
                key={item.id}
                to={`/results/${encodeURIComponent(session.session_id)}/analytic/${item.id}`}
                className={item.id === a.id ? "analytic-side-link active" : "analytic-side-link"}
              >
                <span>{String(item.order).padStart(2, "0")}</span>
                <b>{item.question ?? item.title}</b>
                {item.question && <em>{item.title}</em>}
              </Link>
            ))}
          </nav>
        </aside>

        <article className="analytic-content">
      {/* Title block — science-writer voice */}
      <header style={{ borderLeft: `3px solid ${meta.hue}`, paddingLeft: 18, marginBottom: 28 }}>
        {a.question && (
          <div style={{ color: meta.hue, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
            Research question
          </div>
        )}
        <h1 style={{ fontFamily: "Georgia, serif", fontSize: "1.85rem", color: "#E8E8E8", lineHeight: 1.3 }}>
          {displayHeading}
        </h1>
        {chartLabel && <div className="chart-name-label">{chartLabel}</div>}
      </header>

      {scienceCaption && (
        <section className="science-caption" aria-label="Caption">
          <h2>Caption for document or slide</h2>
          <p>{scienceCaption.short}</p>
          <h2 className="student-caption-heading">Student explanation</h2>
          <p>{scienceCaption.long}</p>
          {a.question && <p className="chart-context-note">{a.caption}</p>}
        </section>
      )}

      {/* Chart */}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginBottom: 8 }}>
        <button className="download-btn" type="button" aria-pressed={largeChart} onClick={() => setLargeChart((value) => !value)}>
          {largeChart ? "Standard chart view" : "Large chart view"}
        </button>
        <button className="download-btn" type="button" onClick={downloadSvg}>
          Download chart SVG
        </button>
      </div>
      <div className={fullWidthChartLayout ? "chart-with-event-key large" : "chart-with-event-key"}>
        <div id="chart-frame" className={fullWidthChartLayout ? "chart-frame large" : "chart-frame"}>
          <ChartRenderer
            kind={a.chartKind}
            session={session}
            width={largeChart ? 1180 : 920}
            height={largeChart ? largeChartHeight : standardChartHeight}
          />
        </div>
        <EventIntervalLegend session={session} />
      </div>
      {a.id === "q-s-07-edr-respiration" && (
        <div
          style={{
            marginTop: 10,
            marginBottom: 14,
            padding: "10px 12px",
            borderRadius: 6,
            background:
              respirationSource === "native_polar"
                ? "rgba(0, 200, 150, 0.10)"
                : respirationSource === "derived_from_ecg"
                  ? "rgba(74, 111, 168, 0.14)"
                  : "rgba(232, 135, 42, 0.14)",
            borderLeft:
              respirationSource === "native_polar"
                ? "3px solid #00C896"
                : respirationSource === "derived_from_ecg"
                  ? "3px solid #4A6FA8"
                  : "3px solid #E8872A",
            color: "#D8D8D8",
            fontSize: 13,
            lineHeight: 1.55,
          }}
        >
          <b>Respiration provenance:</b> {respirationSourceNote ?? respirationProvenanceNote(respirationSource)}
        </div>
      )}
      <EventMarkerApplicabilityNote analytic={a} session={session} />
      <EventIntervalTable session={session} />

      {/* Interpretation triplet. Glossary terms in each prose block
          surface as dotted-underline hover tooltips on first occurrence;
          the helper at annotateGlossaryTerms matches the 35-term
          glossary so readers can look up jargon without leaving the
          page. */}
      <section aria-label="Interpretation" style={{ display: "grid", gridTemplateColumns: "1fr", gap: 18, marginBottom: 22 }}>
        <InterpretationBlock title="What this chart shows" hue={meta.hue}>
          {annotateGlossaryTerms(whatItShowsForAnalytic(a, session))}
        </InterpretationBlock>
        <InterpretationBlock title="How to read it" hue={meta.hue}>
          {annotateGlossaryTerms(howToReadForAnalytic(a, session))}
        </InterpretationBlock>
        <InterpretationBlock title="What it means for cognitive neuroscience of architecture" hue={meta.hue}>
          {annotateGlossaryTerms(architecturalMeaningForAnalytic(a, session))}
        </InterpretationBlock>
        {a.caveats && (
          <InterpretationBlock title="Caveat" hue="#E8872A">
            {annotateGlossaryTerms(a.caveats)}
          </InterpretationBlock>
        )}
        {a.scienceNote && (
          <InterpretationBlock title="Science rationale" hue="#A78BFA">
            {annotateGlossaryTerms(a.scienceNote)}
          </InterpretationBlock>
        )}
      </section>

      {/* Calibration guide — equation + next-step task */}
      {a.calibrationGuide && (
        <section style={{ background: "#141E2A", border: "1px solid #2A3A4A", borderLeft: "3px solid #4A6FA8", borderRadius: 6, padding: "16px 22px", marginBottom: 22 }}>
          <h3 style={{ fontFamily: "Georgia, serif", fontSize: "0.92rem", color: "#4A6FA8", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Calibration &amp; next steps
          </h3>
          <pre style={{ fontSize: 13, color: "#E8E8E8", lineHeight: 1.7, whiteSpace: "pre-wrap", fontFamily: "ui-monospace, Menlo, monospace", margin: 0 }}>
            {a.calibrationGuide}
          </pre>
        </section>
      )}

      {/* Minimum preconditions */}
      {a.minimumPreconditions && a.minimumPreconditions.length > 0 && (
        <div style={{ background: "#2A1E0C", borderLeft: "3px solid #E8872A", padding: "12px 16px", borderRadius: 5, marginBottom: 22, fontSize: 13, color: "#FEE8C8" }}>
          <b>Required for this chart to render correctly:</b>
          <ul style={{ marginLeft: 20, marginTop: 6 }}>
            {a.minimumPreconditions.map((m, i) => <li key={i}>{m}</li>)}
          </ul>
        </div>
      )}

      {/* References */}
      {a.references && a.references.length > 0 && (
        <section style={{ background: "#141414", border: "1px solid #2F2F2F", borderRadius: 8, padding: "16px 22px", marginBottom: 22 }}>
          <h3 style={{ fontFamily: "Georgia, serif", fontSize: "0.92rem", color: "#00C896", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            References
          </h3>
          <ul style={{ listStyle: "none", padding: 0, fontSize: 12.5, color: "#B8B8B8", lineHeight: 1.6 }}>
            {a.references.map((r, i) => (
              <li key={i} style={{ paddingLeft: 14, textIndent: "-14px", marginBottom: 6 }}>
                · {r.apa}{r.doi ? ` doi:${r.doi}` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Prev / next chaining within the group */}
      <nav aria-label="Previous and next graphs" className="graph-step-nav">
        {prev ? (
          <Link to={`/results/${encodeURIComponent(session.session_id)}/analytic/${prev.id}`} style={chainCard(meta.hue, "prev")}>
            <div style={chainLabel(meta.hue)}>← Previous graph</div>
            <div style={chainTitle}>{prev.title}</div>
          </Link>
        ) : null}
        {next ? (
          <Link to={`/results/${encodeURIComponent(session.session_id)}/analytic/${next.id}`} style={chainCard(meta.hue, "next")}>
            <div style={{ ...chainLabel(meta.hue), textAlign: "right" }}>Next graph →</div>
            <div style={{ ...chainTitle, textAlign: "right" }}>{next.title}</div>
          </Link>
        ) : null}
      </nav>
        </article>
      </div>
    </main>
  );
};

function InterpretationBlock({
  title, hue, children,
}: {
  title: string;
  hue: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ background: "#1E1E1E", border: "1px solid #2F2F2F", borderLeft: `3px solid ${hue}`, borderRadius: 6, padding: "16px 22px" }}>
      <h3 style={{ fontFamily: "Georgia, serif", fontSize: "0.95rem", color: hue, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {title}
      </h3>
      <p style={{ fontSize: 14, color: "#E8E8E8", lineHeight: 1.65 }}>{children}</p>
    </div>
  );
}

function chainCard(hue: string, _dir: "prev" | "next"): React.CSSProperties {
  return {
    flex: 1,
    background: "#1E1E1E",
    border: "1px solid #2F2F2F",
    borderTop: `3px solid ${hue}`,
    borderRadius: 6,
    padding: "14px 18px",
    textDecoration: "none",
    color: "#E8E8E8",
  };
}

function chainLabel(hue: string): React.CSSProperties {
  return { color: hue, fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 };
}

const chainTitle: React.CSSProperties = { fontSize: 13, color: "#E8E8E8", fontWeight: 500, lineHeight: 1.4 };

const TIME_ALIGNED_CHARTS: ChartKind[] = [
  "timeseries_overlay",
  "line",
  "strip",
  "edr_respiration",
  "stress_timeline",
];

function EventMarkerApplicabilityNote({ analytic, session }: { analytic: AnalyticEntry; session: StoredSession }) {
  const intervals = sessionEventIntervals(session);
  if (intervals.length === 0 || TIME_ALIGNED_CHARTS.includes(analytic.chartKind)) return null;
  const reason = markerReason(analytic.chartKind);
  return (
    <div className="event-marker-note">
      Room-entry and room-exit markers are not drawn inside this plot because {reason}. Use the room key and interval-means table below for room-by-room interpretation.
    </div>
  );
}

function markerReason(kind: ChartKind): string {
  switch (kind) {
    case "spectrum":
      return "the x-axis is frequency, not time";
    case "tachogram":
      return "the x-axis is beat index, not elapsed time";
    case "histogram":
      return "the x-axis is interval value, not elapsed time";
    case "poincare":
      return "the axes are successive RR intervals, not elapsed time";
    case "summary_table":
      return "this analytic is a numeric summary table rather than a time plot";
    case "stacked_bar":
    case "radar":
    case "gauge":
    case "forest":
    case "bland_altman":
    default:
      return "the chart summarizes values rather than plotting a time axis";
  }
}

function EventIntervalLegend({ session }: { session: StoredSession }) {
  const intervals = sessionEventIntervals(session);
  if (intervals.length === 0) return null;
  return (
    <aside className="event-legend" aria-label="Room letter legend">
      <h2>Room key</h2>
      <p>Letters match the vertical event lines.</p>
      <ol>
        {intervals.map((interval) => (
          <li key={interval.key}>
            <span>{interval.letter}</span>
            <b>{interval.label}</b>
            <em>{formatRelativeRange(session, interval)}</em>
          </li>
        ))}
      </ol>
    </aside>
  );
}

function EventIntervalTable({ session }: { session: StoredSession }) {
  const intervals = sessionEventIntervals(session);
  const ts = session.extended?.cleaned_timeseries ?? [];
  if (intervals.length === 0 || ts.length === 0) return null;
  const rows = allIntervalStats(session);
  return (
    <section className="interval-summary" aria-label="Interval summary table">
      <h2>Interval means</h2>
      <div className="interval-table-scroll">
        <table>
          <thead>
            <tr>
              <th>Key</th>
              <th>Interval</th>
              <th>Seconds</th>
              <th>Arousal</th>
              <th>Main driver</th>
              <th>HR mean</th>
              <th>HR SD</th>
              <th>EDA mean</th>
              <th>Stress v2</th>
              <th>Resp. rate</th>
              <th>RMSSD</th>
              <th>RSA amp.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.interval.key}>
                <td><span className="interval-letter">{row.interval.letter}</span></td>
                <td>{row.interval.label}</td>
                <td className="num">{formatRelativeRange(session, row.interval)}</td>
                <td className="num">{fmtSigned(row.arousal?.mean, 3)}</td>
                <td>{row.dominantDriver?.label ?? "-"}</td>
                <td className="num">{fmt(row.hr?.mean, 1)}</td>
                <td className="num">{fmt(row.hr?.sd, 1)}</td>
                <td className="num">{fmt(row.eda?.mean, 2)}</td>
                <td className="num">{fmt(row.stressV2?.mean, 3)}</td>
                <td className="num">{fmt(row.rpm?.mean, 1)}</td>
                <td className="num">{fmt(row.rmssd?.mean, 1)}</td>
                <td className="num">{fmt(row.rsa?.mean, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function intervalStats(session: StoredSession, interval: EventInterval) {
  const ts = session.extended?.cleaned_timeseries ?? [];
  const windowed = session.extended?.windowed;
  const points = ts.filter((p) => {
    const t = p.timestamp_ms;
    return typeof t === "number" && t >= interval.onsetMs && t <= interval.offsetMs;
  });
  const x0 = sessionTimeOriginMs(session);
  const onsetS = x0 == null ? interval.onsetMs / 1000 : (interval.onsetMs - x0) / 1000;
  const offsetS = x0 == null ? interval.offsetMs / 1000 : (interval.offsetMs - x0) / 1000;
  const windowIndexes = windowed?.t_s
    .map((t, i) => (t >= onsetS && t <= offsetS ? i : -1))
    .filter((i) => i >= 0) ?? [];
  const dominantDriver = dominantWindowContribution(windowed, windowIndexes);

  return {
    interval,
    hr: numberStats(points.map((p) => p.hr_bpm)),
    eda: numberStats(points.map((p) => p.eda_us)),
    stress: numberStats(windowIndexes.map((i) => windowed?.stress[i])),
    stressV2: numberStats(windowIndexes.map((i) => windowed?.stress_v2?.[i])),
    arousal: numberStats(windowIndexes.map((i) => windowed?.arousal_index?.[i])),
    rpm: numberStats(windowIndexes.map((i) => windowed?.mean_rpm[i])),
    rmssd: numberStats(windowIndexes.map((i) => windowed?.rmssd[i])),
    rsa: numberStats(windowIndexes.map((i) => windowed?.rsa_amplitude[i])),
    dominantDriver,
  };
}

function allIntervalStats(session: StoredSession) {
  return sessionEventIntervals(session).map((interval) => intervalStats(session, interval));
}

function numberStats(values: Array<number | null | undefined>) {
  const ys = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (ys.length === 0) return null;
  const mean = ys.reduce((sum, v) => sum + v, 0) / ys.length;
  const variance = ys.length > 1
    ? ys.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / (ys.length - 1)
    : 0;
  return {
    n: ys.length,
    mean,
    sd: Math.sqrt(variance),
    min: Math.min(...ys),
    max: Math.max(...ys),
  };
}

function formatRelativeRange(session: StoredSession, interval: EventInterval): string {
  const origin = sessionTimeOriginMs(session);
  const start = origin == null ? interval.onsetMs / 1000 : (interval.onsetMs - origin) / 1000;
  const end = origin == null ? interval.offsetMs / 1000 : (interval.offsetMs - origin) / 1000;
  return `${start.toFixed(0)}-${end.toFixed(0)}s`;
}

function sessionTimeOriginMs(session: StoredSession): number | null {
  const first = session.extended?.cleaned_timeseries?.find((p) => typeof p.timestamp_ms === "number");
  return typeof first?.timestamp_ms === "number" ? first.timestamp_ms : null;
}

function fmt(value: number | null | undefined, digits: number): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "-";
}

function fmtSigned(value: number | null | undefined, digits: number): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`
    : "-";
}

function captionsForAnalytic(a: AnalyticEntry, session: StoredSession): { short: string; long: string } {
  const finding = findingForAnalytic(a.id, session);
  const intervalDigest = intervalArousalDigest(a, session);
  const readerMove = firstSentence(a.howToRead);
  const meaning = firstSentence(a.architecturalMeaning);
  const caveat = a.caveats ? firstSentence(a.caveats) : "";
  return {
    short: [
      finding,
      intervalDigest.short,
      readerMove,
      meaning,
      caveat || "Treat this as evidence about this session, not as a clinical diagnosis.",
    ].filter(Boolean).join(" "),
    long: [
      finding,
      intervalDigest.long,
      `This is what the chart is showing: ${a.whatItShows}`,
      `To read the figure, ${lowerFirst(a.howToRead)}`,
      `The reason it matters for architecture-cognition work is this: ${a.architecturalMeaning}`,
      a.caveats ? `The main caution is that ${lowerFirst(a.caveats)}` : "The main caution is that this is a session-level physiological interpretation, so it should be read with the quality flags and study design rather than as a standalone diagnosis.",
    ].filter(Boolean).join(" "),
  };
}

function findingForAnalytic(id: string, session: StoredSession): string {
  const r = session.result;
  const fs = r.feature_summary;
  const ext = session.extended;
  const flags = r.quality_flags.join(" ");
  const stressV2 = fs.stress_score_v2 ?? null;
  const ts = ext?.cleaned_timeseries ?? [];
  const rr = ext?.rr_series_ms ?? [];

  switch (id) {
    case "ns-01-hr-eda-timeseries": {
      const hr = seriesStats(ts.map((p) => p.hr_bpm));
      const eda = seriesStats(ts.map((p) => p.eda_us));
      if (!hr && !eda) return "Finding: this session does not contain enough HR or EDA samples to draw a physiological time-course. The empty trace is itself the finding: upload or parsing must be checked before interpretation.";
      if (hr && eda) return `Finding: HR runs from ${hr.min.toFixed(0)} to ${hr.max.toFixed(0)} bpm and ${hr.direction} by ${Math.abs(hr.delta).toFixed(1)} bpm, while EDA runs from ${eda.min.toFixed(2)} to ${eda.max.toFixed(2)} uS and ${eda.direction} by ${Math.abs(eda.delta).toFixed(2)} uS. Read the two panels together: matching rises point to a shared autonomic response; a split pattern means the cardiac and skin-conductance channels are telling different parts of the story.`;
      if (hr) return `Finding: this is a Polar-only time course. HR runs from ${hr.min.toFixed(0)} to ${hr.max.toFixed(0)} bpm and ${hr.direction} by ${Math.abs(hr.delta).toFixed(1)} bpm; read sustained steps rather than single-sample spikes.`;
      return `Finding: this is an EmotiBit-only time course. EDA runs from ${eda!.min.toFixed(2)} to ${eda!.max.toFixed(2)} uS and ${eda!.direction} by ${Math.abs(eda!.delta).toFixed(2)} uS; read slow tonic drift separately from sharp phasic bursts.`;
    }
    case "ns-02-hrv-time-domain":
      return `Finding: RMSSD is ${fs.rmssd_ms.toFixed(1)} ms, SDNN is ${fs.sdnn_ms.toFixed(1)} ms, and mean HR is ${fs.mean_hr_bpm.toFixed(1)} bpm. Read RMSSD as short-term vagal flexibility, SDNN as broader variability, and mean HR as the cardiac load against which that flexibility should be judged.`;
    case "ns-03-psd-frequency-domain":
      return fs.lf_hf_ratio == null
        ? "Finding: this recording does not support a stable frequency-domain HRV estimate. The spectrum should be read as unavailable rather than as a low-power physiological result."
        : `Finding: LF/HF is ${fs.lf_hf_ratio.toFixed(2)} with LF=${fmtNullable(fs.lf_ms2)} ms2 and HF=${fmtNullable(fs.hf_ms2)} ms2. Read the shaded bands by asking where the visible spectral mass sits; here the numeric summary is ${fs.lf_ms2 != null && fs.hf_ms2 != null && fs.lf_ms2 >= fs.hf_ms2 ? "LF-heavy" : "HF-heavy or balanced"}, not a standalone diagnosis.`;
    case "ns-04-eda-tonic-phasic": {
      const eda = seriesStats(ts.map((p) => p.eda_us));
      return eda
        ? `Finding: mean tonic SCL is ${fs.eda_mean_us.toFixed(2)} uS, with an observed range of ${eda.min.toFixed(2)}-${eda.max.toFixed(2)} uS and a phasic index of ${fs.eda_phasic_index.toFixed(3)}. Read the mean as the slow arousal level and the jagged departures as event-linked orienting responses.`
        : "Finding: EDA is not present in this session, so tonic and phasic electrodermal interpretation is unavailable.";
    }
    case "ns-05-stress-decomposition": {
      const d = ext?.stress_decomposition;
      if (!d) return "Finding: no stress decomposition can be computed for this session because one or more required channels are missing.";
      const strongest = [...d.components].sort((a, b) => b.contribution - a.contribution)[0];
      const intervalSentence = stressIntervalFinding(session);
      return `Finding: the experimental stress composite is ${d.total.toFixed(3)}, led by ${d.dominant_driver}; the largest plotted contribution is ${strongest.name} at ${strongest.contribution.toFixed(3)}. ${intervalSentence} Read the stacked bar by asking which colour occupies most of the total, because that identifies the physiological channel driving the score.`;
    }
    case "ns-06-stress-timeline": {
      const s = seriesStats(ext?.windowed?.stress_v2 ?? ext?.windowed?.stress ?? []);
      if (!s) return "Finding: the recording does not contain enough windows for a stress trajectory.";
      const intervalSentence = stressIntervalFinding(session);
      return `Finding: windowed stress peaks at ${s.max.toFixed(3)}, averages ${s.mean.toFixed(3)}, and ${s.direction} by ${Math.abs(s.delta).toFixed(3)} across the session. ${intervalSentence} Read the white line for total stress and the coloured stacked areas for which physiological channel is responsible at each moment.`;
    }
    case "dg-01-sync-qc":
      return `Finding: synchronization quality is ${r.sync_qc_band.toUpperCase()} at ${r.sync_qc_score.toFixed(0)}/100, with gate "${r.sync_qc_gate}". Read the bar as the trust gate for all time-aligned claims; ${r.sync_qc_failure_reasons.length ? `the main warning is ${r.sync_qc_failure_reasons[0]}` : "there are no reported sync-QC failure reasons"}.`;
    case "dg-02-drift":
      return `Finding: the drift model uses ${r.drift_segments} segment${r.drift_segments === 1 ? "" : "s"} with slope ${r.drift_slope.toFixed(6)} and intercept ${r.drift_intercept_ms.toFixed(0)} ms. Read values close to slope 1.000000 as clean clock agreement; multiple segments or a large intercept means time-locked effects need caution.`;
    case "dg-03-motion":
      return `Finding: motion contamination is ${(r.movement_artifact_ratio * 100).toFixed(1)}% of the synchronized record. Read the strip as a veto layer: physiology that changes during flagged motion is weaker evidence than physiology changing during quiet periods.`;
    case "dg-04-tachogram": {
      const rs = rrStats(rr);
      if (!rs) return "Finding: no RR tachogram can be read because the session has too few RR intervals.";
      return `Finding: ${rs.n} RR intervals range from ${rs.min.toFixed(0)} to ${rs.max.toFixed(0)} ms, with ${rs.jumpCount} abrupt beat-to-beat jump${rs.jumpCount === 1 ? "" : "s"} above ${rs.jumpThreshold.toFixed(0)} ms. Read a smooth band as usable rhythm and isolated cliffs as possible ectopic or detection artifacts.`;
    }
    case "dg-05-band-duration-gauge": {
      const dur = durationSeconds(ts);
      return `Finding: the usable recording duration is ${dur.toFixed(0)} s. Read the gauge against the band thresholds: HF needs about 60 s, LF about 120 s, and VLF about 300 s; this session ${dur >= 300 ? "clears all three" : dur >= 120 ? "supports HF and LF but not VLF" : dur >= 60 ? "supports HF only" : "is short even for HF"}.`;
    }
    case "q-s-01-phase-comparison": {
      const d = ext?.inference;
      if (!d) return "Finding: the file does not contain enough phase or trend data for a defensible first-half versus second-half claim. Read the chart descriptively only, looking for broad direction rather than a statistical contrast.";
      const hr = Math.abs(d.hr_change_effect_size_d);
      const eda = Math.abs(d.eda_change_effect_size_d);
      const strongest = hr >= eda ? `heart-rate change (d=${d.hr_change_effect_size_d.toFixed(2)})` : `EDA change (d=${d.eda_change_effect_size_d.toFixed(2)})`;
      return `Finding: the strongest first-half versus second-half shift is ${strongest}. Read the chart by comparing the two phase summaries first, then use the direction and size of each channel to decide whether the change is physiologically meaningful.`;
    }
    case "q-s-02-lfhf-trajectory": {
      const traj = seriesStats((ext?.spectral_trajectory?.lf_hf_ratio ?? []).filter((v): v is number => v != null && Number.isFinite(v)));
      if (traj) return `Finding: LF/HF ${traj.direction} from ${traj.first.toFixed(2)} to ${traj.last.toFixed(2)}, with a session peak of ${traj.max.toFixed(2)}. Read the line left to right: sustained drift matters more than isolated window noise.`;
      return fs.lf_hf_ratio == null
        ? "Finding: no stable LF/HF answer is available because the recording is too short or lacks enough RR data. Read any visible trace as provisional and do not infer sympathovagal balance from it."
        : `Finding: the session-level LF/HF ratio is ${fs.lf_hf_ratio.toFixed(2)}. Read the trajectory from left to right: a flat line suggests stable balance, while sustained upward or downward movement suggests a changing autonomic state.`;
    }
    case "q-s-03-poincare":
      return fs.sd1_ms == null || fs.sd2_ms == null
        ? "Finding: there are not enough RR intervals for a reliable Poincare geometry answer. Treat the scatter as a quality clue, not as a vagal-control estimate."
        : `Finding: the Poincare cloud has SD1=${fs.sd1_ms.toFixed(1)} ms, SD2=${fs.sd2_ms.toFixed(1)} ms, and SD1/SD2=${fs.sd1_sd2_ratio?.toFixed(3) ?? "not available"}. Read width as short-term variability and length as slower variability; a narrow cloud means less beat-to-beat flexibility.`;
    case "q-s-04-habituation": {
      const d = ext?.inference;
      if (!d) return "Finding: habituation cannot be estimated because windowed first-half versus second-half statistics are unavailable. Read the chart for visible trends only.";
      const direction = d.hr_change_effect_size_d < 0 || d.eda_change_effect_size_d < 0 ? "some evidence of reduction over the session" : "no clear reduction over the session";
      return `Finding: there is ${direction}. HR effect size is ${d.hr_change_effect_size_d.toFixed(2)} and EDA effect size is ${d.eda_change_effect_size_d.toFixed(2)}; read downward second-half change as possible habituation and upward or flat change as persistence.`;
    }
    case "q-s-05-hr-eda-coupling": {
      const coupling = correlation(
        ts.map((p) => p.hr_bpm),
        ts.map((p) => p.eda_us),
      );
      if (coupling == null) return "Finding: HR-EDA coupling cannot be estimated because the session lacks paired HR and EDA samples. Read this page as a missing-data result.";
      const strength = Math.abs(coupling) >= 0.6 ? "strong" : Math.abs(coupling) >= 0.3 ? "moderate" : "weak";
      return `Finding: HR and EDA coupling is ${strength} in this session (r=${coupling.toFixed(2)}). Read upward co-movement as integrated autonomic activation; a near-flat or opposite-signed relation means the two channels are not carrying the same signal.`;
    }
    case "q-s-06-bland-altman":
      return "Finding: agreement cannot be answered without a matched Kubios comparison file. Read this page as a placeholder for method comparison: the important marks would be mean bias and limits of agreement.";
    case "q-d-01-rr-histogram":
      return rrHistogramCaption(rr, flags, fs.rr_source);
    case "q-d-02-motion-timeline":
      return `Finding: motion artifact ratio is ${(r.movement_artifact_ratio * 100).toFixed(1)}%. Read the timeline by locating periods where movement overlaps physiological change; values above about 20% are substantial contamination for rest protocols.`;
    case "q-d-03-drift-residuals":
      return r.drift_segments > 1
        ? `Finding: the clocks required piecewise correction across ${r.drift_segments} segments, so drift is present. Read residuals for slopes, jumps, or clustered errors that would weaken time-aligned interpretation.`
        : "Finding: the drift model is single-segment, which is the cleaner case. Read residuals for any remaining slope or structure; a random band around zero is the desired pattern.";
    case "q-d-04-ectopic-rate":
      return fs.nn50 == null
        ? "Finding: ectopic-rate details are not available from this session payload. Read the tachogram visually for sudden isolated jumps before trusting HRV estimates."
        : `Finding: the corrected RR series supports HRV estimation; NN50 is ${fs.nn50}, and pNN50 is ${fs.pnn50?.toFixed(1) ?? "not available"}%. Read isolated spikes as possible ectopic or corrected beats, and sustained bands as the physiological rhythm.`;
    case "q-d-05-edr-quality":
      return edrQualityCaption(session);
    case "q-s-07-edr-respiration":
      return respirationCaption(
        ext?.windowed?.mean_rpm ?? [],
        ext?.windowed?.rsa_amplitude ?? [],
        ext?.edr_proxy?.rr_source ?? fs.rr_source,
      );
    case "q-s-08-sympathovagal-nu":
      return fs.lf_nu == null || fs.hf_nu == null
        ? "Finding: normalized LF/HF units are unavailable, probably because the recording lacks enough stable RR data. Read the page as a data-sufficiency warning rather than a physiology result."
        : `Finding: LF_nu is ${fs.lf_nu.toFixed(1)} and HF_nu is ${fs.hf_nu.toFixed(1)}, so the normalized balance is ${fs.lf_nu >= fs.hf_nu ? "LF-dominant" : "HF-dominant"} in this session. Read the paired bars as relative spectral allocation, not as a direct measure of sympathetic nerve firing.`;
    case "q-s-09-stress-v1-vs-v2":
      return stressV2 == null
        ? `Finding: only stress v1 is available here, with v1=${fs.stress_score.toFixed(3)}. Read the score as a first-pass composite, not as a validated diagnosis.`
        : `Finding: stress v1=${fs.stress_score.toFixed(3)} and stress v2=${stressV2.toFixed(3)}, a difference of ${(stressV2 - fs.stress_score).toFixed(3)}. ${stressIntervalFinding(session)} Read the gap as the effect of adding richer HRV/RSA channels; if the bars diverge, the added physiology has changed the story.`;
    default:
      return "Finding: this chart provides the direct evidence for the stated question. Read the plotted pattern first, then check quality flags before making a substantive interpretation.";
  }
}

function seriesStats(values: Array<number | null | undefined>) {
  const ys = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (ys.length < 2) return null;
  const first = ys[0];
  const last = ys[ys.length - 1];
  const delta = last - first;
  return {
    n: ys.length,
    first,
    last,
    min: Math.min(...ys),
    max: Math.max(...ys),
    mean: ys.reduce((a, b) => a + b, 0) / ys.length,
    delta,
    direction: Math.abs(delta) < 1e-9 ? "is essentially flat" : delta > 0 ? "rises" : "falls",
  };
}

function rrStats(rr: number[]) {
  if (rr.length < 3) return null;
  const sorted = [...rr].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const jumpThreshold = Math.max(250, median * 0.25);
  let jumpCount = 0;
  for (let i = 1; i < rr.length; i++) {
    if (Math.abs(rr[i] - rr[i - 1]) > jumpThreshold) jumpCount += 1;
  }
  return {
    n: rr.length,
    min: Math.min(...rr),
    max: Math.max(...rr),
    median,
    jumpThreshold,
    jumpCount,
  };
}

function rrHistogramCaption(rr: number[], flags: string, source: string): string {
  if (rr.length < 10) return "Finding: the RR histogram cannot be read because there are too few RR intervals.";
  const rs = rrStats(rr);
  const outside = rr.filter((v) => v < 300 || v > 2000).length;
  const outsidePct = (outside / rr.length) * 100;
  const sourceText = source.replace(/_/g, " ");
  const confidence = flags.includes("research-grade") || flags.includes("raw Polar")
    ? `RR intervals are present from ${sourceText}`
    : `RR intervals are present from ${sourceText}, so HRV claims are weaker than with native RR or raw ECG`;
  return `Finding: ${confidence}. The histogram is centred near ${rs!.median.toFixed(0)} ms, spans ${rs!.min.toFixed(0)}-${rs!.max.toFixed(0)} ms, and has ${outsidePct.toFixed(1)}% outside the 300-2000 ms physiological window. Read the central mass as the rhythm and the tails as possible artifact or arrhythmia.`;
}

function respirationCaption(
  rpmRaw: Array<number | null>,
  rsaRaw: Array<number | null>,
  rrSource: string | null | undefined,
): string {
  const rpm = seriesStats(rpmRaw);
  const rsa = seriesStats(rsaRaw);
  if (!rpm && !rsa) return "Finding: a respiration proxy is not available or not stable enough in this session. Do not interpret HRV shifts as stress until breathing has been ruled out.";
  const provenance = respirationProvenanceNote(rrSource);
  if (rpm && rsa) return `Finding: breathing averages ${rpm.mean.toFixed(1)} RPM and ${rpm.direction} by ${Math.abs(rpm.delta).toFixed(1)} RPM, while RSA ${rsa.direction} by ${Math.abs(rsa.delta).toFixed(1)}. Read the two traces together: HRV changes that track breathing are respiratory, not necessarily stress. ${provenance}`;
  if (rpm) return `Finding: breathing averages ${rpm.mean.toFixed(1)} RPM and ${rpm.direction} by ${Math.abs(rpm.delta).toFixed(1)} RPM. Read this trace before attributing HRV movement to arousal. ${provenance}`;
  return `Finding: RSA is available and ${rsa!.direction} by ${Math.abs(rsa!.delta).toFixed(1)}, but breathing rate is not stable enough to display. Read vagal conclusions cautiously. ${provenance}`;
}

function edrQualityCaption(session: StoredSession): string {
  const quality = session.extended?.edr_proxy?.quality;
  const rrSourceNote = session.extended?.edr_proxy?.rr_source_note ?? session.result.feature_summary.rr_source_note;
  if (!quality) return "Finding: this session does not carry a respiration-proxy quality bundle, so the respiration page should be treated as descriptive only.";
  const overall = quality.overall_confidence ?? quality.signal_confidence ?? null;
  const verdict = quality.verdict ?? "unknown";
  const duration = quality.duration_s;
  const count = quality.usable_breath_count;
  const stability = quality.interval_cv != null ? Math.max(0, 1 - quality.interval_cv) : null;
  return `Finding: the respiration proxy is rated ${verdict} at ${fmt(overall != null ? overall * 100 : null, 0)}%, based on ${fmt(duration, 1)} s of usable signal, ${count} usable breath intervals, and rhythm stability ${fmt(stability != null ? stability * 100 : null, 0)}%. ${rrSourceNote ?? "RR provenance note unavailable."}`;
}

function durationSeconds(ts: Array<{ timestamp_ms?: number }>): number {
  const xs = ts.map((p) => p.timestamp_ms).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (xs.length < 2) return 0;
  return (xs[xs.length - 1] - xs[0]) / 1000;
}

function fmtNullable(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "unavailable" : value.toFixed(1);
}

function correlation(aRaw: Array<number | null | undefined>, bRaw: Array<number | null | undefined>): number | null {
  const pairs: Array<[number, number]> = [];
  for (let i = 0; i < Math.min(aRaw.length, bRaw.length); i++) {
    const a = aRaw[i];
    const b = bRaw[i];
    if (typeof a === "number" && Number.isFinite(a) && typeof b === "number" && Number.isFinite(b)) pairs.push([a, b]);
  }
  if (pairs.length < 3) return null;
  const meanA = pairs.reduce((s, [a]) => s + a, 0) / pairs.length;
  const meanB = pairs.reduce((s, [, b]) => s + b, 0) / pairs.length;
  let num = 0;
  let denA = 0;
  let denB = 0;
  for (const [a, b] of pairs) {
    const da = a - meanA;
    const db = b - meanB;
    num += da * db;
    denA += da * da;
    denB += db * db;
  }
  const den = Math.sqrt(denA * denB);
  return den > 0 ? num / den : null;
}

function dominantWindowContribution(
  windowed: WindowedFeatures | null | undefined,
  windowIndexes: number[],
) {
  if (!windowed || windowIndexes.length === 0) return null;
  const channels = [
    { key: "v2_hr_contribution", label: "HR" },
    { key: "v2_eda_contribution", label: "EDA tonic" },
    { key: "v2_phasic_contribution", label: "EDA phasic" },
    { key: "v2_vagal_contribution", label: "vagal deficit" },
    { key: "v2_sympathovagal_contribution", label: "LF_nu balance" },
    { key: "v2_rigidity_contribution", label: "SD1/SD2 rigidity" },
    { key: "v2_rsa_contribution", label: "RSA deficit" },
  ] as const;
  const scores: Array<{ key: string; label: string; mean: number }> = [];
  for (const channel of channels) {
    const values = windowIndexes
      .map((i) => (windowed as any)?.[channel.key]?.[i] as number | null | undefined)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (values.length === 0) continue;
    scores.push({
      key: channel.key,
      label: channel.label,
      mean: values.reduce((sum, v) => sum + v, 0) / values.length,
    });
  }
  scores.sort((a, b) => b.mean - a.mean);
  return scores[0] ?? null;
}

function intervalArousalDigest(a: AnalyticEntry, session: StoredSession): { short: string; long: string } {
  if (!showsIntervalArousal(a)) return { short: "", long: "" };
  const rows = allIntervalStats(session);
  const baseline = rows.find((row) => row.interval.key.toLowerCase() === "baseline");
  const nonBaseline = rows.filter(
    (row) =>
      row.interval.key.toLowerCase() !== "baseline" &&
      typeof row.arousal?.mean === "number" &&
      Number.isFinite(row.arousal.mean),
  );
  if (nonBaseline.length === 0) return { short: "", long: "" };
  const peak = [...nonBaseline].sort((a, b) => (b.arousal?.mean ?? -Infinity) - (a.arousal?.mean ?? -Infinity))[0];
  const low = [...nonBaseline].sort((a, b) => (a.arousal?.mean ?? Infinity) - (b.arousal?.mean ?? Infinity))[0];
  const baselineText = baseline?.stressV2?.mean != null
    ? `The baseline interval sits at raw stress v2 ${baseline.stressV2.mean.toFixed(3)}, which is treated as arousal 0.000.`
    : "The baseline interval is treated as the neutral arousal point whenever a baseline marker is available.";
  const short = `Relative to baseline, ${peak.interval.label} is highest at ${fmtSigned(peak.arousal?.mean, 3)}, driven mainly by ${peak.dominantDriver?.label ?? "no single channel"}, while ${low.interval.label} is lowest at ${fmtSigned(low.arousal?.mean, 3)}.`;
  const long = `${baselineText} Positive arousal means the seven-channel stress-v2 composite is above that participant's own resting level; negative arousal means it is below. Across room intervals, ${peak.interval.label} is the strongest activation interval at ${fmtSigned(peak.arousal?.mean, 3)} with ${peak.dominantDriver?.label ?? "no single dominant driver"} contributing most, whereas ${low.interval.label} is the calmest interval at ${fmtSigned(low.arousal?.mean, 3)}.`;
  return { short, long };
}

function stressIntervalFinding(session: StoredSession): string {
  const rows = allIntervalStats(session).filter(
    (row) =>
      row.interval.key.toLowerCase() !== "baseline" &&
      typeof row.arousal?.mean === "number" &&
      Number.isFinite(row.arousal.mean),
  );
  if (rows.length === 0) return "";
  const peak = [...rows].sort((a, b) => (b.arousal?.mean ?? -Infinity) - (a.arousal?.mean ?? -Infinity))[0];
  return `${peak.interval.label} is the highest-arousal interval at ${fmtSigned(peak.arousal?.mean, 3)}, driven chiefly by ${peak.dominantDriver?.label ?? "no single dominant channel"}.`;
}

function showsIntervalArousal(a: AnalyticEntry): boolean {
  return a.chartKind === "stress_timeline"
    || a.chartKind === "interval_profile"
    || a.chartKind === "timeseries_overlay"
    || a.id.startsWith("ns-0")
    || a.id === "q-s-09-stress-v1-v2";
}

function whatItShowsForAnalytic(a: AnalyticEntry, session: StoredSession): string {
  if (a.id === "q-s-07-edr-respiration") {
    return `${a.whatItShows} ${session.extended?.edr_proxy?.rr_source_note ?? session.result.feature_summary.rr_source_note ?? respirationProvenanceNote(session.extended?.edr_proxy?.rr_source ?? session.result.feature_summary.rr_source)}`;
  }
  if (!showsIntervalArousal(a)) return a.whatItShows;
  const rows = allIntervalStats(session).filter((row) => row.interval.key.toLowerCase() !== "baseline");
  if (rows.length === 0) return a.whatItShows;
  return `${a.whatItShows} For this session the room-interval table is the compact scientific summary: each row reports the room's mean raw stress-v2, its baseline-centred arousal index, and the dominant physiological contributor to that arousal.`;
}

function howToReadForAnalytic(a: AnalyticEntry, session: StoredSession): string {
  if (a.id === "q-s-07-edr-respiration") {
    return `${a.howToRead} ${respirationInterpretationCaveat(session.extended?.edr_proxy?.rr_source ?? session.result.feature_summary.rr_source)}`;
  }
  if (!showsIntervalArousal(a)) return a.howToRead;
  const rows = allIntervalStats(session).filter((row) => row.interval.key.toLowerCase() !== "baseline");
  if (rows.length === 0) return a.howToRead;
  return `${a.howToRead} Then read the room table in two passes: first compare the arousal column against zero, which is the participant's own baseline; then read the main-driver column to see whether the rise comes chiefly from heart rate, electrodermal activity, vagal deficit, LF_nu balance, rigidity, or RSA deficit.`;
}

function architecturalMeaningForAnalytic(a: AnalyticEntry, session: StoredSession): string {
  if (a.id === "q-s-07-edr-respiration") {
    return `${a.architecturalMeaning} ${respirationInterpretationCaveat(session.extended?.edr_proxy?.rr_source ?? session.result.feature_summary.rr_source)}`;
  }
  if (!showsIntervalArousal(a)) return a.architecturalMeaning;
  const rows = allIntervalStats(session).filter((row) => row.interval.key.toLowerCase() !== "baseline");
  if (rows.length === 0) return a.architecturalMeaning;
  return `${a.architecturalMeaning} That distinction matters in architectural interpretation because two rooms may produce similar total arousal while doing so through different autonomic routes: one may raise cardiac load, another may suppress vagal flexibility, and a third may increase electrodermal orienting.`;
}

function firstSentence(text: string): string {
  const trimmed = text.trim();
  const match = trimmed.match(/^(.+?[.!?])(\s|$)/);
  return match ? match[1] : trimmed;
}

function lowerFirst(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return trimmed;
  return trimmed.charAt(0).toLowerCase() + trimmed.slice(1);
}

function respirationProvenanceNote(rrSource: string | null | undefined): string {
  switch (rrSource) {
    case "native_polar":
      return "Here the proxy is reconstructed from native Polar RR intervals, which is the strongest provenance this repo can offer without a dedicated respiration belt.";
    case "derived_from_ecg":
      return "Here the proxy is reconstructed from RR intervals derived in-app from raw ECG, which is still a real beat-level source but weaker than native RR export.";
    case "derived_from_bpm":
      return "Here the proxy is reconstructed from BPM-derived RR surrogates, so it should be read as a coarse timing cue rather than as a high-confidence breath morphology trace.";
    default:
      return "The provenance of the underlying RR series should be checked before treating this proxy as strong respiratory evidence.";
  }
}

function respirationInterpretationCaveat(rrSource: string | null | undefined): string {
  switch (rrSource) {
    case "native_polar":
      return "Because the underlying RR series is native, this page can be used as a serious disambiguation check on whether HRV changes are respiratory or stress-like.";
    case "derived_from_ecg":
      return "Because the underlying RR series was reconstructed from raw ECG, the page is still useful, but claims about fine respiratory timing should remain modest.";
    case "derived_from_bpm":
      return "Because the underlying RR series was reconstructed from BPM rather than native beat intervals, do not treat the proxy waveform as precise evidence about inhalation-exhalation shape; use it only to temper overconfident stress claims.";
    default:
      return "Without clear RR provenance, the chart should be used as a cautionary adjunct, not as a decisive respiratory adjudicator.";
  }
}
