import React, { useState } from "react";
import { StoredSession, updateMarkers } from "../api";
import { EventMarker } from "../analytics/eventIntervals";

type Props = {
  session: StoredSession;
  onUpdated: (updatedSession: StoredSession) => void;
};

export const MarkerEditor: React.FC<Props> = ({ session, onUpdated }) => {
  const [markers, setMarkers] = useState<EventMarker[]>(
    session.markers_summary?.event_markers ?? []
  );
  const [newCode, setNewCode] = useState("");
  const [newSeconds, setNewSeconds] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const originMs = session.extended?.cleaned_timeseries?.find(
    (p) => typeof p.timestamp_ms === "number"
  )?.timestamp_ms;

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!originMs) {
      setError("Cannot add markers: session has no valid timestamps.");
      return;
    }
    const sec = parseFloat(newSeconds);
    if (isNaN(sec)) {
      setError("Time must be a valid number in seconds.");
      return;
    }
    if (!newCode.trim()) {
      setError("Marker code cannot be empty.");
      return;
    }
    setError(null);
    const utc_ms = Math.round(originMs + sec * 1000);
    setMarkers([...markers, { event_code: newCode.trim(), utc_ms }]);
    setNewCode("");
    setNewSeconds("");
  };

  const handleRemove = (index: number) => {
    const next = [...markers];
    next.splice(index, 1);
    setMarkers(next);
  };

  const handleSave = async () => {
    try {
      setIsSaving(true);
      setError(null);
      const updated = await updateMarkers(session.session_id, markers);
      onUpdated(updated);
      setIsOpen(false);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) {
    return (
      <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
        <button
          className="download-btn"
          onClick={() => setIsOpen(true)}
          aria-label="Open Marker Editor"
        >
          Manage analysis markers
        </button>
        <div 
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 18,
            height: 18,
            borderRadius: "50%",
            background: "#2A2A2A",
            color: "#888",
            fontSize: 11,
            fontWeight: "bold",
            cursor: "help",
            border: "1px solid #3A3A3A"
          }}
          title="Add custom markers (like _analysis_onset) to extract exact physiological data for a specific time window without cluttering the charts."
        >
          i
        </div>
      </div>
    );
  }

  return (
    <div style={{ background: "#1E1E1E", border: "1px solid #2F2F2F", borderRadius: 8, padding: "20px", marginTop: 22 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: "#E8E8E8", fontSize: "1.2rem", fontFamily: "Georgia, serif" }}>Marker Editor</h3>
        <button className="download-btn" onClick={() => setIsOpen(false)} style={{ padding: "4px 10px", fontSize: 12 }}>Close</button>
      </div>

      <p style={{ fontSize: 13, color: "#B8B8B8", marginBottom: 16, lineHeight: 1.5 }}>
        Add custom markers (like <code>room1_analysis_onset</code>) to extract specific epochs. 
        Markers with <code>_analysis_</code> in the name are automatically hidden from charts to prevent clutter, 
        but their statistics will be fully computed in the interval CSVs.
      </p>

      {error && <div className="error-banner" style={{ marginBottom: 16 }}>{error}</div>}

      <div style={{ maxHeight: 200, overflowY: "auto", marginBottom: 16, border: "1px solid #2A2A2A", borderRadius: 4, background: "#141414" }}>
        <table style={{ width: "100%", fontSize: 13, textAlign: "left", borderCollapse: "collapse" }}>
          <thead style={{ background: "#222", color: "#888" }}>
            <tr>
              <th style={{ padding: "8px 12px", borderBottom: "1px solid #2A2A2A" }}>Code</th>
              <th style={{ padding: "8px 12px", borderBottom: "1px solid #2A2A2A" }}>Seconds</th>
              <th style={{ padding: "8px 12px", borderBottom: "1px solid #2A2A2A", width: 60 }}></th>
            </tr>
          </thead>
          <tbody>
            {markers.length === 0 ? (
              <tr><td colSpan={3} style={{ padding: "12px", color: "#666", textAlign: "center" }}>No markers defined.</td></tr>
            ) : markers.map((m, i) => {
              const sec = originMs ? ((m.utc_ms - originMs) / 1000).toFixed(1) : "?";
              return (
                <tr key={i} style={{ borderBottom: "1px solid #1E1E1E" }}>
                  <td style={{ padding: "8px 12px", color: "#D8D8D8", fontFamily: "monospace" }}>{m.event_code}</td>
                  <td style={{ padding: "8px 12px", color: "#D8D8D8" }}>{sec}s</td>
                  <td style={{ padding: "8px 12px", textAlign: "right" }}>
                    <button 
                      onClick={() => handleRemove(i)} 
                      style={{ background: "none", border: "none", color: "#E8872A", cursor: "pointer", fontSize: 12 }}
                      aria-label="Remove marker"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <form onSubmit={handleAdd} style={{ display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 16 }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: "block", fontSize: 12, color: "#888", marginBottom: 4 }}>Marker code (e.g. room1_analysis_onset)</label>
          <input 
            type="text" 
            value={newCode} 
            onChange={(e) => setNewCode(e.target.value)} 
            style={{ width: "100%", padding: "8px", background: "#111", border: "1px solid #333", color: "#FFF", borderRadius: 4 }}
            placeholder="room1_analysis_onset"
          />
        </div>
        <div style={{ width: 120 }}>
          <label style={{ display: "block", fontSize: 12, color: "#888", marginBottom: 4 }}>Seconds</label>
          <input 
            type="number" 
            step="0.1"
            value={newSeconds} 
            onChange={(e) => setNewSeconds(e.target.value)} 
            style={{ width: "100%", padding: "8px", background: "#111", border: "1px solid #333", color: "#FFF", borderRadius: 4 }}
            placeholder="120.5"
          />
        </div>
        <button type="submit" className="download-btn" style={{ padding: "9px 14px", height: 35 }}>Add</button>
      </form>

      <div style={{ display: "flex", justifyContent: "flex-end", borderTop: "1px solid #2F2F2F", paddingTop: 16 }}>
        <button 
          className="download-btn" 
          onClick={handleSave} 
          disabled={isSaving}
          style={{ background: "#00C896", color: "#000", fontWeight: 600, border: "none" }}
        >
          {isSaving ? "Saving..." : "Save markers & update session"}
        </button>
      </div>
    </div>
  );
};
