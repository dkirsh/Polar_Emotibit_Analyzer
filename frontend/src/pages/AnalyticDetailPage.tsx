import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getSession, StoredSession } from "../api";
import {
  GROUP_META,
  adjacentAnalytics,
  analyticsByGroup,
  getAnalytic,
} from "../analytics/catalog";
import { ChartRenderer } from "../analytics/ChartRenderer";
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
  const scienceCaption = captionForAnalytic(a.id, session);
  const downloadSvg = () => {
    const svg = document.querySelector("#chart-frame svg");
    if (!svg) return;
    const source = new XMLSerializer().serializeToString(svg);
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
          <h2>Caption</h2>
          <p>{scienceCaption}</p>
          {a.question && <p className="chart-context-note">{a.caption}</p>}
        </section>
      )}

      {/* Chart */}
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
        <button className="download-btn" type="button" onClick={downloadSvg}>
          Download chart SVG
        </button>
      </div>
      <div id="chart-frame" className="chart-frame">
        <ChartRenderer kind={a.chartKind} session={session} width={920} height={360} />
      </div>

      {/* Interpretation triplet. Glossary terms in each prose block
          surface as dotted-underline hover tooltips on first occurrence;
          the helper at annotateGlossaryTerms matches the 35-term
          glossary so readers can look up jargon without leaving the
          page. */}
      <section aria-label="Interpretation" style={{ display: "grid", gridTemplateColumns: "1fr", gap: 18, marginBottom: 22 }}>
        <InterpretationBlock title="What this chart shows" hue={meta.hue}>
          {annotateGlossaryTerms(a.whatItShows)}
        </InterpretationBlock>
        <InterpretationBlock title="How to read it" hue={meta.hue}>
          {annotateGlossaryTerms(a.howToRead)}
        </InterpretationBlock>
        <InterpretationBlock title="What it means for cognitive neuroscience of architecture" hue={meta.hue}>
          {annotateGlossaryTerms(a.architecturalMeaning)}
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

function captionForAnalytic(id: string, session: StoredSession): string {
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
      return `Finding: the experimental stress composite is ${d.total.toFixed(3)}, led by ${d.dominant_driver}; the largest plotted contribution is ${strongest.name} at ${strongest.contribution.toFixed(3)}. Read the stacked bar by asking which colour occupies most of the total, because that identifies the physiological channel driving the score.`;
    }
    case "ns-06-stress-timeline": {
      const s = seriesStats(ext?.windowed?.stress ?? []);
      if (!s) return "Finding: the recording does not contain enough windows for a stress trajectory.";
      return `Finding: windowed stress peaks at ${s.max.toFixed(3)}, averages ${s.mean.toFixed(3)}, and ${s.direction} by ${Math.abs(s.delta).toFixed(3)} across the session. Read the white line for total stress and the coloured stacked areas for which physiological channel is responsible at each moment.`;
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
    case "q-s-07-edr-respiration":
      return respirationCaption(ext?.windowed?.mean_rpm ?? [], ext?.windowed?.rsa_amplitude ?? []);
    case "q-s-08-sympathovagal-nu":
      return fs.lf_nu == null || fs.hf_nu == null
        ? "Finding: normalized LF/HF units are unavailable, probably because the recording lacks enough stable RR data. Read the page as a data-sufficiency warning rather than a physiology result."
        : `Finding: LF_nu is ${fs.lf_nu.toFixed(1)} and HF_nu is ${fs.hf_nu.toFixed(1)}, so the normalized balance is ${fs.lf_nu >= fs.hf_nu ? "LF-dominant" : "HF-dominant"} in this session. Read the paired bars as relative spectral allocation, not as a direct measure of sympathetic nerve firing.`;
    case "q-s-09-stress-v1-vs-v2":
      return stressV2 == null
        ? `Finding: only stress v1 is available here, with v1=${fs.stress_score.toFixed(3)}. Read the score as a first-pass composite, not as a validated diagnosis.`
        : `Finding: stress v1=${fs.stress_score.toFixed(3)} and stress v2=${stressV2.toFixed(3)}, a difference of ${(stressV2 - fs.stress_score).toFixed(3)}. Read the gap as the effect of adding richer HRV/RSA channels; if the bars diverge, the added physiology has changed the story.`;
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

function respirationCaption(rpmRaw: Array<number | null>, rsaRaw: Array<number | null>): string {
  const rpm = seriesStats(rpmRaw);
  const rsa = seriesStats(rsaRaw);
  if (!rpm && !rsa) return "Finding: a respiration proxy is not available or not stable enough in this session. Do not interpret HRV shifts as stress until breathing has been ruled out.";
  if (rpm && rsa) return `Finding: breathing averages ${rpm.mean.toFixed(1)} RPM and ${rpm.direction} by ${Math.abs(rpm.delta).toFixed(1)} RPM, while RSA ${rsa.direction} by ${Math.abs(rsa.delta).toFixed(1)}. Read the two traces together: HRV changes that track breathing are respiratory, not necessarily stress.`;
  if (rpm) return `Finding: breathing averages ${rpm.mean.toFixed(1)} RPM and ${rpm.direction} by ${Math.abs(rpm.delta).toFixed(1)} RPM. Read this trace before attributing HRV movement to arousal.`;
  return `Finding: RSA is available and ${rsa!.direction} by ${Math.abs(rsa!.delta).toFixed(1)}, but breathing rate is not stable enough to display. Read vagal conclusions cautiously.`;
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
