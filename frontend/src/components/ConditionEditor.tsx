import React, { useMemo, useState } from "react";
import { StoredSession, recomputeRespiratoryConditions } from "../api";

/**
 * ConditionEditor — lets the researcher group event markers into named
 * conditions and tag each as the stress arm, the calm/control arm, or a
 * comparison-only condition, then recompute respiratory pattern detection,
 * figures, and the comparison table for that grouping. The chosen grouping is
 * persisted with the session (it round-trips on reload).
 *
 * Roles: "stress" and "calm" define the dichotomy that drives pattern
 * detection; "comparison" conditions appear in the comparison/stats tables only.
 */

type Role = "stress" | "calm" | "comparison";
type Condition = { name: string; markers: string[]; role: Role };

type Props = {
  session: StoredSession;
  onUpdated: (s: StoredSession) => void;
};

const ROLE_LABEL: Record<Role, string> = {
  stress: "Treatment / stress",
  calm: "Control / calm",
  comparison: "Comparison only",
};

export const ConditionEditor: React.FC<Props> = ({ session, onUpdated }) => {
  // Only meaningful when a belt with recompute data exists.
  const hasBelt = !!session.vernier && !session.vernier.error;

  const availableMarkers = useMemo(() => {
    const codes = session.markers_summary?.codes ?? [];
    return Array.from(new Set(codes)).filter(Boolean);
  }, [session]);

  const [conditions, setConditions] = useState<Condition[]>(() => {
    const saved = session.respiratory_conditions;
    if (saved && saved.length) {
      return saved.map((c) => ({
        name: c.name,
        markers: c.markers,
        role: (["stress", "calm", "comparison"].includes(c.role) ? c.role : "comparison") as Role,
      }));
    }
    return [{ name: "Control", markers: [], role: "calm" }, { name: "Treatment", markers: [], role: "stress" }];
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!hasBelt) return null;

  const update = (i: number, patch: Partial<Condition>) =>
    setConditions((cs) => cs.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  const addCondition = () =>
    setConditions((cs) => [...cs, { name: `Condition ${cs.length + 1}`, markers: [], role: "comparison" }]);
  const removeCondition = (i: number) =>
    setConditions((cs) => cs.filter((_, idx) => idx !== i));
  const toggleMarker = (i: number, marker: string) =>
    setConditions((cs) =>
      cs.map((c, idx) =>
        idx === i
          ? { ...c, markers: c.markers.includes(marker) ? c.markers.filter((m) => m !== marker) : [...c.markers, marker] }
          : c,
      ),
    );

  const valid = conditions.filter((c) => c.name.trim() && c.markers.length > 0);
  const canApply = valid.length >= 2 && !busy;

  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await recomputeRespiratoryConditions(
        session.session_id,
        valid.map((c) => ({ name: c.name.trim(), markers: c.markers, role: c.role })),
      );
      onUpdated(updated);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const chip = (active: boolean): React.CSSProperties => ({
    display: "inline-block",
    padding: "3px 9px",
    margin: "2px 4px 2px 0",
    borderRadius: 12,
    fontSize: 12,
    cursor: "pointer",
    border: `1px solid ${active ? "#00C896" : "#3A3A3A"}`,
    background: active ? "rgba(0,200,150,0.15)" : "#1A1A1A",
    color: active ? "#C9F0E4" : "#A8A8A8",
    userSelect: "none",
  });

  return (
    <section className="card" style={{ marginTop: 22 }} aria-label="Condition grouping">
      <h2>Condition grouping</h2>
      <p style={{ fontSize: 13, color: "#B8B8B8", lineHeight: 1.5, marginBottom: 14 }}>
        Group your event markers into named conditions and choose which is the
        treatment (stress) arm and which is the control. Applying recomputes the
        respiratory pattern detection, the figures, and the comparison/statistics
        for your contrast, and saves the grouping with this session.
      </p>

      {availableMarkers.length === 0 ? (
        <div className="notice" style={{ marginBottom: 12 }}>
          No event markers are recorded for this session, so there is nothing to
          group yet. Add markers (via the marker editor above or a markers file)
          and they will appear here.
        </div>
      ) : null}

      {conditions.map((c, i) => (
        <div key={i} style={{ background: "#181818", border: "1px solid #2F2F2F", borderRadius: 8, padding: "12px 14px", marginBottom: 10 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
            <input
              value={c.name}
              onChange={(e) => update(i, { name: e.target.value })}
              placeholder="Condition name"
              style={{ background: "#101010", border: "1px solid #3A3A3A", color: "#E8E8E8", borderRadius: 6, padding: "6px 10px", fontSize: 13, width: 180 }}
            />
            <select
              value={c.role}
              onChange={(e) => update(i, { role: e.target.value as Role })}
              style={{ background: "#101010", border: "1px solid #3A3A3A", color: "#E8E8E8", borderRadius: 6, padding: "6px 10px", fontSize: 13 }}
            >
              {(["stress", "calm", "comparison"] as Role[]).map((r) => (
                <option key={r} value={r}>{ROLE_LABEL[r]}</option>
              ))}
            </select>
            <button
              onClick={() => removeCondition(i)}
              style={{ marginLeft: "auto", background: "transparent", border: "1px solid #3A3A3A", color: "#A8A8A8", borderRadius: 6, padding: "5px 10px", fontSize: 12, cursor: "pointer" }}
            >
              Remove
            </button>
          </div>
          <div>
            {availableMarkers.map((m) => (
              <span key={m} style={chip(c.markers.includes(m))} onClick={() => toggleMarker(i, m)} role="button" aria-pressed={c.markers.includes(m)}>
                {m}
              </span>
            ))}
          </div>
        </div>
      ))}

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 6, flexWrap: "wrap" }}>
        <button onClick={addCondition} className="download-btn" style={{ fontSize: 13 }}>+ Add condition</button>
        <button onClick={apply} disabled={!canApply} className="download-btn"
          style={{ fontSize: 13, background: canApply ? "#00C896" : "#2A2A2A", color: canApply ? "#08130F" : "#6B6B6B", fontWeight: 600 }}>
          {busy ? "Recomputing…" : "Apply grouping & recompute"}
        </button>
        {valid.length < 2 ? (
          <span style={{ fontSize: 12, color: "#7A7A7A" }}>Define at least two conditions (name + ≥1 marker each).</span>
        ) : null}
      </div>

      {error ? <div className="error-banner" style={{ marginTop: 12 }}>{error}</div> : null}
    </section>
  );
};
