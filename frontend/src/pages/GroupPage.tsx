import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getSession, StoredSession } from "../api";
import {
  AnalyticGroup,
  GROUP_META,
  analyticsByCategory,
  analyticsByGroup,
} from "../analytics/catalog";

/**
 * Group page — renders the cards for one of the three analytic groups.
 * Necessary and Diagnostic pages use same-size cards; Question-Driven
 * uses an expandable list grouped by category (Science / Diagnostics).
 */
export const GroupPage: React.FC = () => {
  const { sessionId, groupId } = useParams<{ sessionId: string; groupId: AnalyticGroup }>();
  const [session, setSession] = useState<StoredSession | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    getSession(sessionId).then(setSession).catch(() => {});
  }, [sessionId]);

  if (!session || !groupId) return <main className="page">Loading…</main>;
  const meta = GROUP_META[groupId];

  const cardStyle = (size: "sm" | "md"): React.CSSProperties => ({
    background: "#1E1E1E",
    border: `1px solid #2F2F2F`,
    borderLeft: `3px solid ${meta.hue}`,
    borderRadius: 6,
    padding: size === "sm" ? "14px 16px" : "18px 22px",
    textDecoration: "none",
    color: "#E8E8E8",
    display: "block",
    transition: "background 0.15s",
  });

  return (
    <main className="page">
      <div style={{ marginBottom: 18 }}>
        <Link to={`/results/${encodeURIComponent(session.session_id)}`} style={{ color: "#00C896", fontSize: 13 }}>
          ← Cover
        </Link>
      </div>

      <div style={{ marginBottom: 26 }}>
        <div style={{ fontSize: 26, color: meta.hue }}>{meta.icon}</div>
        <h1 style={{ fontFamily: "Georgia, serif", fontSize: "1.8rem", color: meta.hue, marginTop: 6 }}>
          {meta.title}
        </h1>
        <p style={{ color: "#B8B8B8", maxWidth: 720, marginTop: 8 }}>{meta.caption}</p>
      </div>

      {groupId === "question" ? (
        <QuestionsList session={session} hue={meta.hue} />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: groupId === "diagnostic" ? "repeat(auto-fit, minmax(260px, 1fr))" : "repeat(auto-fit, minmax(300px, 1fr))", gap: groupId === "diagnostic" ? 12 : 16 }}>
          {analyticsByGroup(groupId).map((a) => (
            <Link
              key={a.id}
              to={`/results/${encodeURIComponent(session.session_id)}/analytic/${a.id}`}
              style={cardStyle(groupId === "diagnostic" ? "sm" : "md")}
            >
              <div style={{ fontSize: 11, color: meta.hue, fontWeight: 700, letterSpacing: "0.04em" }}>
                {String(a.order).padStart(2, "0")} · {a.chartKind.replace("_", " ")}
              </div>
              <h3 style={{ fontFamily: "Georgia, serif", fontSize: groupId === "diagnostic" ? "1rem" : "1.1rem", color: "#E8E8E8", margin: "6px 0 8px 0" }}>
                {a.title}
              </h3>
              <p style={{ fontSize: 12.5, color: "#B8B8B8", lineHeight: 1.5 }}>{a.caption}</p>
              <div style={{ marginTop: 10, color: "#00C896", fontSize: 12, fontWeight: 600 }}>Open →</div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
};

function QuestionsList({ session, hue }: { session: StoredSession; hue: string }) {
  const sci = analyticsByCategory("science");
  const diag = analyticsByCategory("diagnostics");
  return (
    <div>
      <CategoryBlock title="Science questions" hue={hue} items={sci} sessionId={session.session_id} />
      <div style={{ height: 24 }} />
      <CategoryBlock title="Diagnostics questions" hue="#E8872A" items={diag} sessionId={session.session_id} />
    </div>
  );
}

function CategoryBlock({
  title, hue, items, sessionId,
}: {
  title: string;
  hue: string;
  items: ReturnType<typeof analyticsByCategory>;
  sessionId: string;
}) {
  return (
    <div>
      <h2 style={{ fontFamily: "Georgia, serif", fontSize: "1rem", color: hue, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {title}
      </h2>
      <div style={{ background: "#141414", border: "1px solid #2F2F2F", borderRadius: 8, overflow: "hidden" }}>
        {items.map((a, i) => (
          <Link
            key={a.id}
            to={`/results/${encodeURIComponent(sessionId)}/analytic/${a.id}`}
            style={{
              display: "block",
              padding: "14px 18px",
              color: "#E8E8E8",
              textDecoration: "none",
              borderTop: i === 0 ? "none" : "1px solid #2F2F2F",
              transition: "background 0.1s",
            }}
          >
            <div style={{ color: hue, fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
              {a.question}
            </div>
            <div style={{ fontSize: 13, color: "#B8B8B8" }}>{a.title} — {a.caption}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
