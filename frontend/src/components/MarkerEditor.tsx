import React, { useState, useRef } from "react";
import { StoredSession, updateMarkers } from "../api";
import { EventMarker } from "../analytics/eventIntervals";

type TimestampMode = "seconds" | "unix" | "utc";

const MODE_CONFIG: Record<TimestampMode, { label: string; placeholder: string; width: number; inputType: string; step?: string }> = {
  seconds: { label: "Seconds (offset from start)", placeholder: "120.5", width: 150, inputType: "number", step: "0.1" },
  unix:    { label: "Unix Timestamp (s)", placeholder: "1714600000.000", width: 200, inputType: "number", step: "0.001" },
  utc:     { label: "UTC Datetime", placeholder: "2026-05-01T14:30:00Z", width: 250, inputType: "text" },
};

type Props = {
  session: StoredSession;
  onUpdated: (updatedSession: StoredSession) => void;
};

/**
 * Parse a raw time input string into utc_ms based on the selected mode.
 * Returns null if parsing fails.
 */
function parseTimeInput(raw: string, mode: TimestampMode, originMs: number | undefined): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;

  switch (mode) {
    case "seconds": {
      if (originMs === undefined) return null;
      const sec = parseFloat(trimmed);
      if (isNaN(sec)) return null;
      return Math.round(originMs + sec * 1000);
    }
    case "unix": {
      // Accept seconds (with optional decimals), milliseconds, or nanoseconds
      const num = parseFloat(trimmed);
      if (isNaN(num)) return null;
      if (num > 1e15) {
        // Nanoseconds (> 1e15)
        return Math.round(num / 1e6);
      } else if (num > 1e12) {
        // Milliseconds (> 1e12)
        return Math.round(num);
      } else {
        // Seconds
        return Math.round(num * 1000);
      }
    }
    case "utc": {
      // Accept ISO 8601 datetime strings
      const d = new Date(trimmed);
      if (isNaN(d.getTime())) return null;
      return d.getTime();
    }
  }
}

/**
 * Parse a CSV file and extract markers. Supports three column layouts:
 *  1. event_code, utc_ms   (milliseconds)
 *  2. event_code, utc_ns   (nanoseconds, like Polar timestamps)
 *  3. event_code, unix_seconds  (seconds, like session_marks CSV)
 *  4. session_id, event_code, utc_ms  (the David platform format)
 *  5. label, unix_seconds  (alternate session_marks format)
 *  6. event_code, timestamp  (ISO 8601 / UTC datetime string)
 *
 * Auto-detects based on header names and value magnitudes.
 */
function parseMarkerCSV(text: string): EventMarker[] {
  const lines = text.split(/\r?\n/).filter(l => l.trim() && !l.startsWith("#"));
  if (lines.length < 2) return [];

  const headerLine = lines[0].toLowerCase();
  const headers = headerLine.split(",").map(h => h.trim());
  const dataLines = lines.slice(1);
  const markers: EventMarker[] = [];

  // Find the event code column
  let codeIdx = headers.findIndex(h =>
    h === "event_code" || h === "label" || h === "marker" || h === "code" || h === "name"
  );

  // Find the time column and determine its type
  type CsvTimeType = "ms" | "ns" | "seconds" | "iso";
  let timeIdx = -1;
  let timeType: CsvTimeType = "ms";

  const timeColCandidates: Array<{ name: string; type: CsvTimeType }> = [
    { name: "utc_ms", type: "ms" },
    { name: "timestamp_ms", type: "ms" },
    { name: "utc_ns", type: "ns" },
    { name: "timestamp_ns", type: "ns" },
    { name: "unix_seconds", type: "seconds" },
    { name: "seconds", type: "seconds" },
    { name: "time", type: "seconds" },
    { name: "timestamp", type: "iso" },
    { name: "utc", type: "iso" },
    { name: "datetime", type: "iso" },
  ];

  for (const candidate of timeColCandidates) {
    const idx = headers.indexOf(candidate.name);
    if (idx !== -1) {
      timeIdx = idx;
      timeType = candidate.type;
      break;
    }
  }

  // Handle the David platform 3-column format: session_id, event_code, utc_ms
  if (headers.length >= 3 && headers[0] === "session_id" && headers[1] === "event_code" && headers[2] === "utc_ms") {
    codeIdx = 1;
    timeIdx = 2;
    timeType = "ms";
  }

  // If we still haven't found columns, try positional: assume col 0 = code, col 1 = time
  if (codeIdx === -1) codeIdx = 0;
  if (timeIdx === -1) timeIdx = headers.length > 2 ? 2 : 1;

  // Auto-detect time type from first data value if header was ambiguous
  if (timeType === "iso" || timeType === "seconds") {
    const firstVal = dataLines[0]?.split(",")[timeIdx]?.trim() ?? "";
    const num = parseFloat(firstVal);
    if (!isNaN(num)) {
      if (num > 1e15) timeType = "ns";
      else if (num > 1e12) timeType = "ms";
      else timeType = "seconds";
    } else {
      timeType = "iso";
    }
  }

  for (const line of dataLines) {
    const cols = line.split(",").map(c => c.trim());
    const code = cols[codeIdx];
    const rawTime = cols[timeIdx];
    if (!code || !rawTime) continue;

    let utc_ms: number;
    switch (timeType) {
      case "ms":
        utc_ms = Math.round(parseFloat(rawTime));
        break;
      case "ns":
        utc_ms = Math.round(parseFloat(rawTime) / 1e6);
        break;
      case "seconds":
        utc_ms = Math.round(parseFloat(rawTime) * 1000);
        break;
      case "iso": {
        const d = new Date(rawTime);
        if (isNaN(d.getTime())) continue;
        utc_ms = d.getTime();
        break;
      }
    }

    if (isNaN(utc_ms!)) continue;
    markers.push({ event_code: code, utc_ms: utc_ms! });
  }

  return markers;
}

export const MarkerEditor: React.FC<Props> = ({ session, onUpdated }) => {
  const [markers, setMarkers] = useState<EventMarker[]>(
    session.markers_summary?.event_markers ?? []
  );
  const [newCode, setNewCode] = useState("");
  const [newTime, setNewTime] = useState("");
  const [timestampMode, setTimestampMode] = useState<TimestampMode>("seconds");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [csvStatus, setCsvStatus] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const originMs = session.extended?.cleaned_timeseries?.find(
    (p) => typeof p.timestamp_ms === "number"
  )?.timestamp_ms;

  const config = MODE_CONFIG[timestampMode];

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (timestampMode === "seconds" && !originMs) {
      setError("Cannot add markers in Seconds mode: session has no valid timestamps.");
      return;
    }
    const utc_ms = parseTimeInput(newTime, timestampMode, originMs);
    if (utc_ms === null) {
      const hints: Record<TimestampMode, string> = {
        seconds: "Time must be a valid number in seconds (e.g. 120.5).",
        unix: "Time must be a valid Unix timestamp in seconds, ms, or ns (e.g. 1714600000).",
        utc: "Time must be a valid ISO 8601 datetime (e.g. 2026-05-01T14:30:00Z).",
      };
      setError(hints[timestampMode]);
      return;
    }
    if (!newCode.trim()) {
      setError("Marker code cannot be empty.");
      return;
    }
    setError(null);
    setMarkers([...markers, { event_code: newCode.trim(), utc_ms }]);
    setNewCode("");
    setNewTime("");
  };

  const handleRemove = (index: number) => {
    const next = [...markers];
    next.splice(index, 1);
    setMarkers(next);
  };

  const handleCSVUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvStatus(null);
    setError(null);

    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target?.result as string;
      try {
        const parsed = parseMarkerCSV(text);
        if (parsed.length === 0) {
          setError("CSV contained no valid markers. Expected columns: event_code + a time column (utc_ms, unix_seconds, timestamp, etc.).");
          return;
        }
        setMarkers([...markers, ...parsed]);
        setCsvStatus(`Imported ${parsed.length} marker${parsed.length > 1 ? "s" : ""} from ${file.name}`);
      } catch {
        setError("Failed to parse CSV file.");
      }
    };
    reader.onerror = () => setError("Failed to read CSV file.");
    reader.readAsText(file);
    // Reset so the same file can be re-uploaded
    if (fileInputRef.current) fileInputRef.current.value = "";
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

  const formatDisplayTime = (m: EventMarker): string => {
    if (originMs) {
      return `${((m.utc_ms - originMs) / 1000).toFixed(1)}s`;
    }
    return new Date(m.utc_ms).toISOString();
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
      {csvStatus && (
        <div style={{ background: "#0E251C", borderLeft: "3px solid #00C896", padding: "10px 14px", borderRadius: 5, fontSize: 13, color: "#C9F0E4", marginBottom: 16 }}>
          {csvStatus}
        </div>
      )}

      {/* Timestamp mode selector + CSV upload — same row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 16, padding: "12px 14px", background: "#141414", border: "1px solid #2A2A2A", borderRadius: 6 }}>
        {/* Radio buttons — left aligned */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 11, color: "#888", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Timestamp format</span>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {(["seconds", "unix", "utc"] as TimestampMode[]).map((mode) => (
              <label
                key={mode}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: "pointer",
                  fontSize: 13,
                  color: timestampMode === mode ? "#E8E8E8" : "#888",
                  padding: "3px 0",
                }}
              >
                <input
                  type="radio"
                  name="timestampMode"
                  value={mode}
                  checked={timestampMode === mode}
                  onChange={() => { setTimestampMode(mode); setNewTime(""); setError(null); }}
                  style={{ accentColor: "#00C896" }}
                />
                {MODE_CONFIG[mode].label}
              </label>
            ))}
          </div>
        </div>

        {/* CSV upload — center of row */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, color: "#888", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Import from CSV</span>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.txt"
            onChange={handleCSVUpload}
            style={{ display: "none" }}
            id="marker-csv-upload"
          />
          <button
            className="download-btn"
            onClick={() => fileInputRef.current?.click()}
            style={{ padding: "7px 16px", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
          >
            <span style={{ fontSize: 14 }}>📄</span> Upload marker CSV
          </button>
          <span style={{ fontSize: 11, color: "#666", maxWidth: 220, textAlign: "center", lineHeight: 1.3 }}>
            Accepts: event_code + utc_ms, unix_seconds, timestamp_ns, or ISO datetime
          </span>
        </div>
      </div>

      {/* Existing markers table */}
      <div style={{ maxHeight: 200, overflowY: "auto", marginBottom: 16, border: "1px solid #2A2A2A", borderRadius: 4, background: "#141414" }}>
        <table style={{ width: "100%", fontSize: 13, textAlign: "left", borderCollapse: "collapse" }}>
          <thead style={{ background: "#222", color: "#888" }}>
            <tr>
              <th style={{ padding: "8px 12px", borderBottom: "1px solid #2A2A2A" }}>Code</th>
              <th style={{ padding: "8px 12px", borderBottom: "1px solid #2A2A2A" }}>Time</th>
              <th style={{ padding: "8px 12px", borderBottom: "1px solid #2A2A2A", width: 60 }}></th>
            </tr>
          </thead>
          <tbody>
            {markers.length === 0 ? (
              <tr><td colSpan={3} style={{ padding: "12px", color: "#666", textAlign: "center" }}>No markers defined.</td></tr>
            ) : markers.map((m, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #1E1E1E" }}>
                <td style={{ padding: "8px 12px", color: "#D8D8D8", fontFamily: "monospace" }}>{m.event_code}</td>
                <td style={{ padding: "8px 12px", color: "#D8D8D8" }}>{formatDisplayTime(m)}</td>
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
            ))}
          </tbody>
        </table>
      </div>

      {/* Add marker form — label dynamically reflects selected mode */}
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
        <div style={{ width: config.width }}>
          <label style={{ display: "block", fontSize: 12, color: "#888", marginBottom: 4 }}>{config.label}</label>
          <input 
            type={config.inputType}
            step={config.step}
            value={newTime} 
            onChange={(e) => setNewTime(e.target.value)} 
            style={{ width: "100%", padding: "8px", background: "#111", border: "1px solid #333", color: "#FFF", borderRadius: 4 }}
            placeholder={config.placeholder}
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
