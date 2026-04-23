import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  analyze,
  listRecentSessions,
  RecentSession,
  ValidateEmotibitResponse,
  ValidateMarkersResponse,
  ValidatePolarResponse,
  validateEmotibitCsv,
  validateMarkersCsv,
  validatePolarCsv,
} from "../api";

type FileSlotState<T> =
  | { file: null }
  | { file: File; status: "validating" }
  | { file: File; status: "valid"; info: T }
  | { file: File; status: "invalid"; error: string };

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * View 1 — New Analysis Session.
 * Captures session identity plus the two (optionally three) CSV files
 * and submits them to /api/v1/analyze. On success navigates to
 * /results/:sessionId.
 *
 * Per docs/GUI_SCOPE_FILE_ONLY_2026-04-20.md, this replaces the
 * five-step wizard from the sibling emotibit_polar_data_system repo.
 * There is no Lab Setup, no Sensor Setup, no Data Collection step —
 * the tool is a file-only post-hoc analyzer.
 */
export const StartPage: React.FC = () => {
  const nav = useNavigate();

  // Metadata
  const [sessionId, setSessionId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [studyId, setStudyId] = useState("");
  const [sessionDate, setSessionDate] = useState(todayISO());
  const [operator, setOperator] = useState("");
  const [notes, setNotes] = useState("");

  // Uploads
  const [emotibit, setEmotibit] = useState<FileSlotState<ValidateEmotibitResponse>>({ file: null });
  const [polar, setPolar] = useState<FileSlotState<ValidatePolarResponse>>({ file: null });
  const [markers, setMarkers] = useState<FileSlotState<ValidateMarkersResponse>>({ file: null });

  // Submit state
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Recent-sessions footer
  const [recent, setRecent] = useState<RecentSession[]>([]);
  useEffect(() => { listRecentSessions(10).then(setRecent).catch(() => {}); }, []);

  const onDropFile = useCallback(
    async (
      which: "em" | "pol" | "mk",
      file: File,
    ) => {
      if (which === "em") {
        setEmotibit({ file, status: "validating" });
        try { setEmotibit({ file, status: "valid", info: await validateEmotibitCsv(file) }); }
        catch (e) { setEmotibit({ file, status: "invalid", error: (e as Error).message }); }
      } else if (which === "pol") {
        setPolar({ file, status: "validating" });
        try { setPolar({ file, status: "valid", info: await validatePolarCsv(file) }); }
        catch (e) { setPolar({ file, status: "invalid", error: (e as Error).message }); }
      } else {
        setMarkers({ file, status: "validating" });
        try { setMarkers({ file, status: "valid", info: await validateMarkersCsv(file) }); }
        catch (e) { setMarkers({ file, status: "invalid", error: (e as Error).message }); }
      }
    },
    [],
  );

  const submitEnabled =
    sessionId.trim().length > 0 &&
    subjectId.trim().length > 0 &&
    studyId.trim().length > 0 &&
    sessionDate.length > 0 &&
    emotibit.file !== null && "status" in emotibit && emotibit.status === "valid" &&
    polar.file !== null && "status" in polar && polar.status === "valid" &&
    (markers.file === null || ("status" in markers && markers.status !== "invalid")) &&
    !submitting;

  const onSubmit = async () => {
    if (!submitEnabled) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await analyze({
        emotibit_file: emotibit.file!,
        polar_file: polar.file!,
        markers_file: markers.file ?? null,
        session_id: sessionId.trim(),
        subject_id: subjectId.trim(),
        study_id: studyId.trim(),
        session_date: sessionDate,
        operator: operator.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      nav(`/results/${encodeURIComponent(sessionId.trim())}`);
    } catch (e) {
      setSubmitError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="page" role="main" aria-label="New analysis session">
      <div className="va-grid">

        {/* LEFT — Session metadata */}
        <section className="card" aria-label="Session metadata">
          <h2>Session Identity</h2>
          <div className="field">
            <label htmlFor="f-sess">Session ID<span className="req">*</span></label>
            <input id="f-sess" value={sessionId} onChange={(e) => setSessionId(e.target.value)}
                   placeholder="e.g. S204_2026_04_08" />
          </div>
          <div className="field">
            <label htmlFor="f-subj">Subject ID<span className="req">*</span></label>
            <input id="f-subj" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}
                   placeholder="e.g. P01" />
          </div>
          <div className="field">
            <label htmlFor="f-study">Study / Project ID<span className="req">*</span></label>
            <input id="f-study" value={studyId} onChange={(e) => setStudyId(e.target.value)}
                   placeholder="e.g. STRESS_001" />
          </div>
          <div className="field">
            <label htmlFor="f-date">Session date<span className="req">*</span></label>
            <input id="f-date" type="date" value={sessionDate}
                   onChange={(e) => setSessionDate(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="f-op">Operator / analyst</label>
            <input id="f-op" value={operator} onChange={(e) => setOperator(e.target.value)}
                   placeholder="(optional)" />
          </div>
          <div className="field">
            <label htmlFor="f-notes">Notes</label>
            <textarea id="f-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)}
                      maxLength={500} placeholder="(optional, ≤ 500 chars)" />
          </div>
        </section>

        {/* RIGHT — Uploads */}
        <section className="card" aria-label="File uploads">
          <h2>Upload Files</h2>
          {submitError && <div className="error-banner">Analysis failed: {submitError}</div>}

          <DropSlot
            label="EmotiBit CSV (EDA + accelerometer)"
            required
            state={emotibit}
            onFile={(f) => onDropFile("em", f)}
            describeInfo={(info) =>
              `${info.n_rows} rows, ${info.timestamp_range_ms.span_s}s · ${info.has_accelerometer ? "accelerometer present" : "no accelerometer"}${info.has_respiration ? " · resp_bpm present" : ""}`}
          />
          <DropSlot
            label="Polar H10 CSV (raw ECG preferred)"
            required
            state={polar}
            onFile={(f) => onDropFile("pol", f)}
            describeInfo={(info) =>
              `${info.n_rows} rows, ${info.timestamp_range_ms.span_s}s · ${
                info.rr_source === "derived_from_ecg"
                  ? "raw ECG present (HR/RR computed in app)"
                  : info.rr_source === "native_polar"
                    ? "native RR present (research-grade)"
                    : "hr_bpm only (BPM-derived RR, reduced accuracy)"
              }`}
          />
          <DropSlot
            label="Event markers CSV (optional)"
            required={false}
            state={markers}
            onFile={(f) => onDropFile("mk", f)}
            describeInfo={(info) =>
              `${info.n_rows} markers · codes: ${info.codes_present.join(", ")}${info.unknown_codes.length > 0 ? ` (unknown: ${info.unknown_codes.join(", ")})` : ""}`}
          />

          <button className="submit-btn" disabled={!submitEnabled} onClick={onSubmit}
                  aria-busy={submitting}>
            {submitting ? "Running pipeline…" : "Run Synchronization & Feature Extraction"}
          </button>
        </section>
      </div>

      {/* Recent sessions footer */}
      {recent.length > 0 && (
        <section className="recent-sessions" aria-label="Recent sessions">
          <h2 style={{ color: "#00C896", fontFamily: "Georgia, serif", fontSize: "1rem", marginBottom: 10 }}>
            Recent sessions
          </h2>
          <table>
            <thead>
              <tr>
                <th>Session</th><th>Subject</th><th>Date</th><th>Analyzed at</th><th>Sync QC</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((s) => (
                <tr key={s.session_id}>
                  <td><a href={`/results/${encodeURIComponent(s.session_id)}`}>{s.session_id}</a></td>
                  <td>{s.subject_id}</td>
                  <td>{s.session_date}</td>
                  <td>{s.analyzed_at.slice(0, 19).replace("T", " ")}</td>
                  <td>
                    <span className={`qc-pill ${s.sync_qc_gate === "go" ? "green" : s.sync_qc_gate === "conditional_go" ? "yellow" : "red"}`}>
                      {s.sync_qc_gate === "go" ? "Green" : s.sync_qc_gate === "conditional_go" ? "Yellow" : "Red"} · {Math.round(s.sync_qc_score)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {submitting && (
        <div className="loading-overlay" role="status" aria-live="polite">
          <div className="spinner">Running V2.1 pipeline — drift correction, synchronization, feature extraction…</div>
        </div>
      )}
    </main>
  );
};

// Helper component: drag-drop + validation feedback.
function DropSlot<T>({
  label, required, state, onFile, describeInfo,
}: {
  label: string;
  required: boolean;
  state: FileSlotState<T>;
  onFile: (f: File) => void;
  describeInfo: (info: T) => string;
}) {
  const [drag, setDrag] = useState(false);
  const className =
    "dropzone " +
    (drag ? "drag " : "") +
    ("status" in state
      ? state.status === "valid"
        ? "valid"
        : state.status === "invalid"
          ? "invalid"
          : ""
      : "");

  return (
    <div
      className={className}
      role="button"
      tabIndex={0}
      aria-label={`Upload ${label}`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files[0];
        if (f) onFile(f);
      }}
      onClick={() => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".csv,text/csv";
        input.onchange = () => { if (input.files?.[0]) onFile(input.files[0]); };
        input.click();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          (e.currentTarget as HTMLDivElement).click();
        }
      }}
      style={{ marginBottom: 14 }}
    >
      <h4>{label}{required && <span className="req"> *</span>}</h4>
      {state.file === null ? (
        <p style={{ color: "#888" }}>Drag CSV here, or click to browse</p>
      ) : (
        <>
          <div className="filename">{state.file.name}</div>
          {"status" in state && state.status === "validating" && (
            <div className="validation-detail">Validating…</div>
          )}
          {"status" in state && state.status === "valid" && (
            <div className="validation-detail">✓ {describeInfo(state.info)}</div>
          )}
          {"status" in state && state.status === "invalid" && (
            <div className="validation-detail error">✗ {state.error}</div>
          )}
        </>
      )}
    </div>
  );
}
