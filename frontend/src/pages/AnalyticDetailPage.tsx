import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getSession, StoredSession } from "../api";
import {
  GROUP_META,
  adjacentAnalytics,
  getAnalytic,
} from "../analytics/catalog";
import { ChartRenderer } from "../analytics/ChartRenderer";

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

  useEffect(() => {
    if (!sessionId) return;
    getSession(sessionId).then(setSession).catch(() => {});
  }, [sessionId]);

  if (!session || !analyticId || !sessionId) return <main className="page">Loading…</main>;
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

  return (
    <main className="page" style={{ maxWidth: 960 }}>
      <div style={{ marginBottom: 14, display: "flex", gap: 16, alignItems: "center", fontSize: 13 }}>
        <Link to={`/results/${encodeURIComponent(session.session_id)}`} style={{ color: "#00C896" }}>Cover</Link>
        <span style={{ color: "#6B6B6B" }}>/</span>
        <Link to={groupHref} style={{ color: meta.hue }}>{meta.title}</Link>
        <span style={{ color: "#6B6B6B" }}>/</span>
        <span style={{ color: "#6B6B6B" }}>{String(a.order).padStart(2, "0")}</span>
      </div>

      {/* Title block — science-writer voice */}
      <header style={{ borderLeft: `3px solid ${meta.hue}`, paddingLeft: 18, marginBottom: 28 }}>
        {a.question && (
          <div style={{ color: meta.hue, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
            {a.question}
          </div>
        )}
        <h1 style={{ fontFamily: "Georgia, serif", fontSize: "1.85rem", color: "#E8E8E8", lineHeight: 1.3 }}>
          {a.title}
        </h1>
        <p style={{ color: "#B8B8B8", fontSize: 14, marginTop: 10, maxWidth: 720, lineHeight: 1.55 }}>
          {a.caption}
        </p>
      </header>

      {/* Chart */}
      <div style={{ background: "#141414", border: "1px solid #2F2F2F", borderRadius: 8, padding: 12, marginBottom: 22 }}>
        <ChartRenderer kind={a.chartKind} session={session} width={920} height={360} />
      </div>

      {/* Interpretation triplet */}
      <section style={{ display: "grid", gridTemplateColumns: "1fr", gap: 18, marginBottom: 22 }}>
        <InterpretationBlock title="What this chart shows" hue={meta.hue}>
          {a.whatItShows}
        </InterpretationBlock>
        <InterpretationBlock title="How to read it" hue={meta.hue}>
          {a.howToRead}
        </InterpretationBlock>
        <InterpretationBlock title="What it means for cognitive neuroscience of architecture" hue={meta.hue}>
          {a.architecturalMeaning}
        </InterpretationBlock>
        {a.caveats && (
          <InterpretationBlock title="Caveat" hue="#E8872A">
            {a.caveats}
          </InterpretationBlock>
        )}
      </section>

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
      <nav style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "stretch", marginTop: 30 }}>
        {prev ? (
          <Link to={`/results/${encodeURIComponent(session.session_id)}/analytic/${prev.id}`} style={chainCard(meta.hue, "prev")}>
            <div style={chainLabel(meta.hue)}>← Previous in {meta.title}</div>
            <div style={chainTitle}>{prev.title}</div>
          </Link>
        ) : <div />}
        {next ? (
          <Link to={`/results/${encodeURIComponent(session.session_id)}/analytic/${next.id}`} style={chainCard(meta.hue, "next")}>
            <div style={{ ...chainLabel(meta.hue), textAlign: "right" }}>Next in {meta.title} →</div>
            <div style={{ ...chainTitle, textAlign: "right" }}>{next.title}</div>
          </Link>
        ) : <div />}
      </nav>
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
