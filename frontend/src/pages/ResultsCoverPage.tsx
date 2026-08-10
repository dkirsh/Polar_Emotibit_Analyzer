import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getSession, sessionExportUrl, StoredSession } from "../api";
import { GROUP_META, analyticsByGroup } from "../analytics/catalog";
import { MarkerEditor } from "../components/MarkerEditor";
import { ConditionEditor } from "../components/ConditionEditor";

/**
 * Results cover page — the landing for a completed analysis.
 * Shows the session-identity bar, a top-level sync-QC pill, and three
 * large group cards (Necessary Science, Diagnostic, Question-Driven).
 * Each card leads to its group page.
 */
export const ResultsCoverPage: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [session, setSession] = useState<StoredSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    getSession(sessionId).then(setSession).catch((e) => setError((e as Error).message));
  }, [sessionId]);

  if (error) return (
    <main className="page">
      <div className="error-banner">{error}</div>
      <div className="notice">Run a new analysis first, then use the exact Session ID shown in the form and recent-sessions table.</div>
      <Link to="/" style={{ color: "#00C896" }}>← back</Link>
    </main>
  );
  if (!session) return <main className="page"><div className="loading-panel">Reading saved analysis session…</div></main>;

  const r = session.result;
  const band = r.sync_qc_band;

  return (
    <main className="page" role="main" aria-label="Analysis results cover page">
      <div className="identity-bar" role="banner" aria-label="Session identity">
        <div className="session-line">
          Session {session.session_id} · Subject {session.subject_id} · {session.session_date}
          {session.operator ? ` · ${session.operator}` : ""}
        </div>
        <div className="meta-line">
          Analyzed at {session.analyzed_at.slice(0, 19).replace("T", " ")} · Study {session.study_id} ·
          {" "}RR source: {r.feature_summary.rr_source.replace("_", " ")} ·
          {" "}Sync-QC: <span style={{ color: band === "green" ? "#C9F0E4" : band === "yellow" ? "#FEE8C8" : "#F5A0B0" }}>{band.toUpperCase()} ({r.sync_qc_score.toFixed(0)}/100)</span>
        </div>
      </div>

      <div style={{ background: "#1E1E1E", border: "1px solid #2F2F2F", borderRadius: 10, padding: "18px 22px", marginBottom: 22, fontSize: 13, color: "#C9F0E4", lineHeight: 1.55 }}>
        This analysis is organised into three reading layers. Read <b style={{ color: "#00C896" }}>Necessary Science Analytics</b> first: these are the five charts a research-grade HRV and EDA analysis is expected to defend. Read <b style={{ color: "#E8872A" }}>Diagnostic Analytics</b> before trusting any of the science — they report data quality, synchronisation cleanliness, and artifact load. <b style={{ color: "#8BA8D4" }}>Question-Driven Analytics</b> exist for specific research questions; open the list when your analysis plan needs an answer the primary charts do not deliver directly.
      </div>

      <nav aria-label="Analytic groups" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 18 }}>
        {(["necessary", "diagnostic", "question"] as const).map((g) => {
          const meta = GROUP_META[g];
          const count = g === "question"
            ? analyticsByGroup("question").length
            : analyticsByGroup(g).length;
          return (
            <Link
              key={g}
              to={`/results/${encodeURIComponent(session.session_id)}/group/${g}`}
              aria-label={`${meta.title}: ${count} analytics`}
              style={{
                background: "#1E1E1E",
                border: `1px solid #2F2F2F`,
                borderTop: `4px solid ${meta.hue}`,
                borderRadius: 8,
                padding: "22px 24px",
                textDecoration: "none",
                color: "#E8E8E8",
                transition: "border-color 0.15s, transform 0.1s",
                display: "block",
              }}
            >
              <div style={{ fontSize: 22, color: meta.hue, marginBottom: 6 }} aria-hidden="true">{meta.icon}</div>
              <h3 style={{ fontFamily: "Georgia, serif", fontSize: "1.1rem", color: meta.hue, marginBottom: 8 }}>{meta.title}</h3>
              <p style={{ fontSize: 13, color: "#B8B8B8", lineHeight: 1.5 }}>{meta.caption}</p>
              <div style={{ marginTop: 14, color: "#00C896", fontWeight: 600, fontSize: 13 }}>
                {count} {count === 1 ? "analytic" : "analytics"} →
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Quality flags — always visible on the cover */}
      <section className="card" style={{ marginTop: 22 }} aria-label="Provenance flags">
        <h2>Provenance flags</h2>
        <ul className="flags-list" role="list">
          {r.quality_flags.map((f, i) => <li key={i}>{f}</li>)}
        </ul>
      </section>

      {/* Direct Vernier respiration-belt summary. Rendered only when a belt was
          recorded. This closes the last-mile gap where belt results were
          computed and stored but dropped before reaching the screen. */}
      <BeltRespirationCard
        vernier={session.vernier}
        patterns={session.respiratory_patterns}
      />

      <ConditionEditor session={session} onUpdated={setSession} />

      <div className="notice" style={{ marginTop: 18 }} role="note">
        <b>Non-diagnostic notice.</b> {r.non_diagnostic_notice}
      </div>

      <MarkerEditor session={session} onUpdated={setSession} />

      {/* Download row — JSON + four Kubios-parity report formats.
          The four format buttons link to the server-side export endpoint
          which runs through app/services/reporting/exporters.py. */}
      <div className="download-row" style={{ marginTop: 18, display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button
          className="download-btn"
          aria-label="Download full analysis JSON"
          onClick={() => {
            const blob = new Blob([JSON.stringify(session, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${session.session_id}_analysis.json`;
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          ↓ JSON
        </button>
        <a
          className="download-btn"
          href={sessionExportUrl(session.session_id, "csv")}
          download={`${session.session_id}.csv`}
          aria-label="Download analysis as CSV"
        >
          ↓ CSV
        </a>
        <a
          className="download-btn"
          href={sessionExportUrl(session.session_id, "intervals_csv")}
          download={`${session.session_id}_interval_means.csv`}
          aria-label="Download interval means as CSV"
        >
          ↓ Interval CSV
        </a>
        <a
          className="download-btn"
          href={sessionExportUrl(session.session_id, "xlsx")}
          download={`${session.session_id}.xlsx`}
          aria-label="Download analysis as Excel workbook"
        >
          ↓ XLSX
        </a>
        <a
          className="download-btn"
          href={sessionExportUrl(session.session_id, "mat")}
          download={`${session.session_id}.mat`}
          aria-label="Download analysis as MATLAB .mat file"
        >
          ↓ MAT
        </a>
        <a
          className="download-btn"
          href={sessionExportUrl(session.session_id, "pdf")}
          download={`${session.session_id}.pdf`}
          aria-label="Download analysis as PDF report"
        >
          ↓ PDF
        </a>
        <Link
          className="download-btn"
          to={`/results/${encodeURIComponent(session.session_id)}/room-summary`}
          aria-label="Open room marker summary chart"
        >
          Room summary
        </Link>
      </div>

      <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <Link to="/" className="download-btn">Add / replace files</Link>
        <div style={{ fontSize: 12, color: "#6B6B6B" }}>Cover page · {session.session_id}</div>
      </div>
    </main>
  );
};

/** Format a possibly-null number to a fixed precision, or an em-dash. */
function fmtNum(v: number | null | undefined, digits: number, unit = ""): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v.toFixed(digits)}${unit ? " " + unit : ""}`;
}

/**
 * Direct Vernier respiration-belt summary card.
 *
 * This is the consumer end of the Vernier last-mile fix: the belt is parsed and
 * analyzed server-side, carried through SessionDetail, and shown here. It renders
 * nothing when no belt was recorded (honest empty state rather than fake zeros),
 * surfaces a parse error if one occurred, and otherwise reports the summary
 * respiratory features plus any detected breathing-pattern anomalies.
 */
const BeltRespirationCard: React.FC<{
  vernier: StoredSession["vernier"];
  patterns: StoredSession["respiratory_patterns"];
}> = ({ vernier, patterns }) => {
  if (!vernier) return null;

  if (vernier.error) {
    return (
      <section className="card" style={{ marginTop: 22 }} aria-label="Respiration belt">
        <h2>Respiration (belt)</h2>
        <div className="error-banner" style={{ marginTop: 8 }}>{vernier.error}</div>
      </section>
    );
  }

  const f = vernier.respiratory_features ?? null;
  const details = patterns?.pattern_details ?? null;
  const detailRows = details
    ? Object.entries(details).sort((a, b) => Number(b[1].found) - Number(a[1].found) || b[1].count - a[1].count)
    : [];
  const figures = patterns?.figures ?? null;
  // Show the overview figure first, then the rest in stable order.
  const figureEntries = figures
    ? Object.entries(figures).sort((a, b) => (a[0] === "overview" ? -1 : b[0] === "overview" ? 1 : a[0].localeCompare(b[0])))
    : [];
  const conditions = patterns?.condition_comparison?.conditions ?? null;
  const conditionRows = conditions ? Object.entries(conditions) : [];
  const contrasts = patterns?.contrasts ?? [];

  const stat = (label: string, value: string, note?: string) => (
    <div style={{ background: "#1A1A1A", border: "1px solid #2F2F2F", borderRadius: 8, padding: "12px 14px", minWidth: 150 }}>
      <div style={{ fontSize: 11, color: "#8BA8D4", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, color: "#E8E8E8", fontFamily: "Georgia, serif" }}>{value}</div>
      {note ? <div style={{ fontSize: 11, color: "#7A7A7A", marginTop: 3 }}>{note}</div> : null}
    </div>
  );

  const th: React.CSSProperties = { textAlign: "left", padding: "6px 10px", color: "#8BA8D4", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", borderBottom: "1px solid #2F2F2F" };
  const td: React.CSSProperties = { padding: "6px 10px", fontSize: 13, color: "#D8D8D8", borderBottom: "1px solid #242424" };

  return (
    <section className="card" style={{ marginTop: 22 }} aria-label="Respiration belt">
      <h2>Respiration (belt)</h2>
      <p style={{ fontSize: 13, color: "#B8B8B8", lineHeight: 1.5, marginBottom: 14 }}>
        Direct respiration from the Vernier belt — a measured chest-expansion
        signal, distinct from the RR-derived respiration proxy under
        Question-Driven analytics. Where both exist, the belt is the stronger
        evidence for breathing rate and depth.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {stat("Respiratory rate", fmtNum(f?.resp_rate_bpm, 1, "bpm"))}
        {stat("Mean cycle", fmtNum(f?.mean_cycle_dur_s, 2, "s"))}
        {stat("Mean I:E ratio", fmtNum(f?.ie_ratio_mean, 2), "inhale ÷ exhale")}
        {stat("Breaths detected", fmtNum(f?.n_breaths ?? null, 0))}
        {stat("Recording", fmtNum(vernier.duration_s ?? null, 0, "s"), `${vernier.sample_rate_hz ?? "?"} Hz`)}
        {patterns?.total_breaths != null ? stat("Cycles analyzed", String(patterns.total_breaths)) : null}
      </div>

      {/* Pattern count table — quantity of each stress pattern, stressed vs calm. */}
      {detailRows.length > 0 ? (
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 12, color: "#E8872A", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Stress-pattern counts
          </div>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={th}>Pattern</th>
                <th style={{ ...th, textAlign: "right" }}>Stressed breaths</th>
                <th style={{ ...th, textAlign: "right" }}>Calm breaths</th>
                <th style={{ ...th, textAlign: "center" }}>Detected</th>
              </tr>
            </thead>
            <tbody>
              {detailRows.map(([key, d]) => (
                <tr key={key}>
                  <td style={td} title={d.description ?? ""}>{d.label}</td>
                  <td style={{ ...td, textAlign: "right", color: d.found ? "#F5A0B0" : "#D8D8D8" }}>{d.count}</td>
                  <td style={{ ...td, textAlign: "right" }}>{d.calm_count}</td>
                  <td style={{ ...td, textAlign: "center" }}>{d.found ? "●" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ marginTop: 14, fontSize: 12, color: "#7A7A7A" }}>
          No stress-related breathing patterns were flagged for this session.
        </div>
      )}

      {/* Cross-condition comparison — populated when markers/order-affect define conditions. */}
      {conditionRows.length > 0 ? (
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 12, color: "#8BA8D4", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Comparison by condition
          </div>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={th}>Condition</th>
                <th style={{ ...th, textAlign: "right" }}>Breaths</th>
                <th style={{ ...th, textAlign: "right" }}>Rate (bpm)</th>
                <th style={{ ...th, textAlign: "right" }}>I:E</th>
                <th style={{ ...th, textAlign: "right" }}>Amplitude</th>
              </tr>
            </thead>
            <tbody>
              {conditionRows.map(([label, c]) => (
                <tr key={label}>
                  <td style={td}>{label}</td>
                  <td style={{ ...td, textAlign: "right" }}>{c.n_breaths}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmtNum(c.resp_rate_mean, 1)} ± {fmtNum(c.resp_rate_sd, 1)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmtNum(c.ie_ratio_mean, 2)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmtNum(c.amplitude_mean, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* Stage-2 statistics: condition contrasts with effect size + 95% CI. */}
      {contrasts.length > 0 ? (
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 12, color: "#8BA8D4", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Condition contrasts (effect size &amp; 95% CI)
          </div>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={th}>Contrast</th>
                <th style={th}>Metric</th>
                <th style={{ ...th, textAlign: "right" }}>Δ</th>
                <th style={{ ...th, textAlign: "right" }}>Cohen's d</th>
                <th style={{ ...th, textAlign: "right" }}>95% CI</th>
                <th style={{ ...th, textAlign: "center" }}>n</th>
              </tr>
            </thead>
            <tbody>
              {contrasts.map((c, i) => (
                <tr key={i}>
                  <td style={td}>{c.condition_a} − {c.condition_b}</td>
                  <td style={td}>{c.metric_label}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmtNum(c.diff, 2)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmtNum(c.cohens_d, 2)}</td>
                  <td style={{ ...td, textAlign: "right", color: c.underpowered ? "#C8A24A" : "#D8D8D8" }}>
                    {c.underpowered ? "underpowered" : `[${fmtNum(c.ci95_low, 2)}, ${fmtNum(c.ci95_high, 2)}]`}
                  </td>
                  <td style={{ ...td, textAlign: "center" }} title={c.underpowered_reason ?? ""}>{c.n_a}/{c.n_b}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ fontSize: 11, color: "#7A7A7A", marginTop: 6 }}>
            Δ is mean(A) − mean(B). Contrasts with fewer than 8 breaths in an arm
            are flagged underpowered rather than given a confident interval.
          </div>
        </div>
      ) : null}

      {/* Backend-rendered pattern figures (matplotlib PNGs, base64). */}
      {figureEntries.length > 0 ? (
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 12, color: "#00C896", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Pattern illustrations
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 14 }}>
            {figureEntries.map(([name, b64]) => (
              <figure key={name} style={{ margin: 0, background: "#FAFAFA", borderRadius: 8, padding: 8, border: "1px solid #2F2F2F" }}>
                <img
                  src={`data:image/png;base64,${b64}`}
                  alt={`Respiratory pattern figure: ${name}`}
                  style={{ width: "100%", height: "auto", display: "block", borderRadius: 4 }}
                />
                <figcaption style={{ fontSize: 11, color: "#6B6B6B", marginTop: 6, textAlign: "center", textTransform: "capitalize" }}>
                  {name.replace(/_/g, " ")}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
};
