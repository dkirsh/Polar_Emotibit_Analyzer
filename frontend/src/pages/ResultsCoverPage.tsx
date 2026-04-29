import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getSession, sessionExportUrl, StoredSession } from "../api";
import { GROUP_META, analyticsByGroup } from "../analytics/catalog";

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

      <div className="notice" style={{ marginTop: 18 }} role="note">
        <b>Non-diagnostic notice.</b> {r.non_diagnostic_notice}
      </div>

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
      </div>

      <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <Link to="/" className="download-btn">Add / replace files</Link>
        <div style={{ fontSize: 12, color: "#6B6B6B" }}>Cover page · {session.session_id}</div>
      </div>
    </main>
  );
};
