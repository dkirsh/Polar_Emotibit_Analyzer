import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  analyze,
  analyzeSingle,
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

type SavedSettings = {
  sessionId: string;
  subjectId: string;
  studyId: string;
  sessionDate: string;
  operator: string;
  notes: string;
};

type UploadSlot = "em" | "pol" | "mk";

const SETTINGS_KEY = "polar-emotibit:last-settings";

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function loadSavedSettings(): SavedSettings {
  const fallback = {
    sessionId: "",
    subjectId: "",
    studyId: "",
    sessionDate: todayISO(),
    operator: "",
    notes: "",
  };
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    if (!raw) return fallback;
    return { ...fallback, ...JSON.parse(raw) };
  } catch {
    return fallback;
  }
}

const draft = {
  settings: loadSavedSettings(),
  emotibit: { file: null } as FileSlotState<ValidateEmotibitResponse>,
  polar: { file: null } as FileSlotState<ValidatePolarResponse>,
  markers: { file: null } as FileSlotState<ValidateMarkersResponse>,
};

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
  const [sessionId, setSessionId] = useState(draft.settings.sessionId);
  const [subjectId, setSubjectId] = useState(draft.settings.subjectId);
  const [studyId, setStudyId] = useState(draft.settings.studyId);
  const [sessionDate, setSessionDate] = useState(draft.settings.sessionDate);
  const [operator, setOperator] = useState(draft.settings.operator);
  const [notes, setNotes] = useState(draft.settings.notes);

  // Uploads
  const [emotibit, setEmotibit] = useState<FileSlotState<ValidateEmotibitResponse>>(draft.emotibit);
  const [polar, setPolar] = useState<FileSlotState<ValidatePolarResponse>>(draft.polar);
  const [markers, setMarkers] = useState<FileSlotState<ValidateMarkersResponse>>(draft.markers);

  // Submit state
  const [submitting, setSubmitting] = useState(false);
  const [submitStage, setSubmitStage] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Recent-sessions footer
  const [recent, setRecent] = useState<RecentSession[]>([]);
  useEffect(() => { listRecentSessions(10).then(setRecent).catch(() => {}); }, []);

  useEffect(() => {
    const settings = { sessionId, subjectId, studyId, sessionDate, operator, notes };
    draft.settings = settings;
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  }, [sessionId, subjectId, studyId, sessionDate, operator, notes]);

  useEffect(() => { draft.emotibit = emotibit; }, [emotibit]);
  useEffect(() => { draft.polar = polar; }, [polar]);
  useEffect(() => { draft.markers = markers; }, [markers]);

  const hasValidEmotibit = emotibit.file !== null && "status" in emotibit && emotibit.status === "valid";
  const hasValidPolar = polar.file !== null && "status" in polar && polar.status === "valid";

  const onDropFile = useCallback(
    async (
      which: UploadSlot,
      file: File,
    ) => {
      const existing = which === "em" ? emotibit.file : which === "pol" ? polar.file : markers.file;
      if (existing && !window.confirm(`${slotLabel(which)} already contains ${existing.name}. Replace it with ${file.name}?`)) {
        return;
      }

      const localCheck = await checkFileForSlot(file, which);
      if (!localCheck.ok) {
        const invalid = { file, status: "invalid" as const, error: localCheck.message };
        if (which === "em") setEmotibit(invalid);
        else if (which === "pol") setPolar(invalid);
        else setMarkers(invalid);
        return;
      }
      if (localCheck.confirm && !window.confirm(localCheck.confirm)) {
        return;
      }

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
    [emotibit.file, markers.file, polar.file],
  );

  const submitEnabled =
    sessionId.trim().length > 0 &&
    subjectId.trim().length > 0 &&
    studyId.trim().length > 0 &&
    sessionDate.length > 0 &&
    (hasValidEmotibit || hasValidPolar) &&
    (markers.file === null || ("status" in markers && markers.status !== "invalid")) &&
    !submitting;

  const onSubmit = async () => {
    if (!submitEnabled) return;
    setSubmitting(true);
    setSubmitStage("Reading uploaded files and checking CSV schemas…");
    setSubmitError(null);
    try {
      if (hasValidEmotibit && hasValidPolar) {
        setSubmitStage("Synchronizing Polar and EmotiBit timestamps…");
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
      } else if (hasValidPolar) {
        setSubmitStage("Reading Polar file and computing HR/HRV charts…");
        await analyzeSingle({
          file: polar.file!,
          source_type: "polar",
          session_id: sessionId.trim(),
          subject_id: subjectId.trim(),
          study_id: studyId.trim(),
          session_date: sessionDate,
          operator: operator.trim() || undefined,
          notes: notes.trim() || undefined,
        });
      } else {
        setSubmitStage("Reading EmotiBit file and computing EDA charts…");
        await analyzeSingle({
          file: emotibit.file!,
          source_type: "emotibit",
          session_id: sessionId.trim(),
          subject_id: subjectId.trim(),
          study_id: studyId.trim(),
          session_date: sessionDate,
          operator: operator.trim() || undefined,
          notes: notes.trim() || undefined,
        });
      }
      setSubmitStage("Saving analysis and opening chart dashboard…");
      nav(`/results/${encodeURIComponent(sessionId.trim())}`);
    } catch (e) {
      setSubmitError((e as Error).message);
      setSubmitStage("Analysis stopped before charts were created.");
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
            required={false}
            state={emotibit}
            onFile={(f) => onDropFile("em", f)}
            onClear={() => setEmotibit({ file: null })}
            describeInfo={(info) =>
              `${info.n_rows} rows, ${info.timestamp_range_ms.span_s}s · ${info.has_accelerometer ? "accelerometer present" : "no accelerometer"}${info.has_respiration ? " · resp_bpm present" : ""}`}
          />
          <DropSlot
            label="Polar H10 CSV (raw ECG preferred)"
            required={false}
            state={polar}
            onFile={(f) => onDropFile("pol", f)}
            onClear={() => setPolar({ file: null })}
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
            onClear={() => setMarkers({ file: null })}
            describeInfo={(info) =>
              `${info.n_events ?? info.n_rows} markers · codes: ${(info.event_codes ?? []).join(", ") || "none"}`
            }
          />

          <button className="submit-btn" disabled={!submitEnabled} onClick={onSubmit}
                  aria-busy={submitting}>
            {submitting
              ? "Running pipeline…"
              : hasValidEmotibit && hasValidPolar
                ? "Run Paired Analysis"
                : hasValidPolar
                  ? "Run Polar-Only Analysis"
                  : hasValidEmotibit
                    ? "Run EmotiBit-Only Analysis"
                    : "Upload One or Two Files"}
          </button>
          {(submitStage || submitError) && (
            <div className={`run-status ${submitError ? "failed" : submitting ? "active" : "idle"}`} role="status" aria-live="polite">
              <b>{submitError ? "Analysis status" : "Pipeline status"}</b>
              <span>{submitError ? submitStage : submitStage}</span>
            </div>
          )}
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
          <div className="spinner">{submitStage ?? "Running V2.1 pipeline…"}</div>
        </div>
      )}
    </main>
  );
};

function slotLabel(which: UploadSlot): string {
  if (which === "em") return "EmotiBit slot";
  if (which === "pol") return "Polar slot";
  return "Event markers slot";
}

async function checkFileForSlot(
  file: File,
  which: UploadSlot,
): Promise<{ ok: true; confirm?: string } | { ok: false; message: string }> {
  const name = file.name.toLowerCase();
  const header = await readCsvHeader(file);
  const columns = header.split(",").map((c) => c.trim().toLowerCase());
  const has = (col: string) => columns.includes(col);
  const hasAny = (cols: string[]) => cols.some(has);
  const filenameHas = (pattern: RegExp) => pattern.test(file.name);
  const looksLikeMarkers = has("event_code") || has("utc_ms") || filenameHas(/(^|[_\-\s])(event|events|marker|markers|sync)([_\-\s.]|$)/i);
  const looksLikePolar = hasAny(["hr_bpm", "rr_ms", "ecg_uv", "ecg_mv", "ecg", "raw_ecg", "raw_ecg_uv", "voltage_uv", "timestamp_ns"]) || filenameHas(/polar|h10|hrv|ecg|rr/i);
  const looksLikeEmotibit = has("eda_us") || hasAny(["acc_x", "acc_y", "acc_z", "resp_bpm"]) || filenameHas(/emotibit|eda|gsr/i);

  if (which === "pol") {
    if (looksLikeMarkers) {
      return { ok: false, message: "This looks like an event markers file. Put it in the Event markers slot, not the Polar slot." };
    }
    if (looksLikeEmotibit && !looksLikePolar) {
      return { ok: false, message: "This looks like an EmotiBit file. Put it in the EmotiBit slot, not the Polar slot." };
    }
    if (!looksLikePolar) {
      return { ok: true, confirm: `${file.name} does not look like a Polar/H10 filename and its header does not show HR, RR, or ECG columns. Try it in the Polar slot anyway?` };
    }
  }

  if (which === "em") {
    if (looksLikeMarkers) {
      return { ok: false, message: "This looks like an event markers file. Put it in the Event markers slot, not the EmotiBit slot." };
    }
    if (looksLikePolar && !looksLikeEmotibit) {
      return { ok: false, message: "This looks like a Polar/H10 file. Put it in the Polar slot, not the EmotiBit slot." };
    }
    if (!looksLikeEmotibit) {
      return { ok: true, confirm: `${file.name} does not look like an EmotiBit filename and its header does not show EDA columns. Try it in the EmotiBit slot anyway?` };
    }
  }

  if (which === "mk") {
    if (looksLikePolar && !looksLikeMarkers) {
      return { ok: false, message: "This looks like a Polar/H10 file. Put it in the Polar slot, not the Event markers slot." };
    }
    if (looksLikeEmotibit && !looksLikeMarkers) {
      return { ok: false, message: "This looks like an EmotiBit file. Put it in the EmotiBit slot, not the Event markers slot." };
    }
    if (!has("event_code") || !has("utc_ms")) {
      return { ok: true, confirm: `${file.name} does not show the expected event marker columns (session_id, event_code, utc_ms). Try it in the Event markers slot anyway?` };
    }
  }

  if (!name.endsWith(".csv")) {
    return { ok: true, confirm: `${file.name} is not named as a .csv file. Try it anyway?` };
  }
  return { ok: true };
}

function readCsvHeader(file: File): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onerror = () => resolve("");
    reader.onload = () => {
      const text = String(reader.result ?? "");
      resolve(text.split(/\r?\n/, 1)[0] ?? "");
    };
    reader.readAsText(file.slice(0, 4096));
  });
}

// Helper component: drag-drop + validation feedback.
function DropSlot<T>({
  label, required, state, onFile, onClear, describeInfo,
}: {
  label: string;
  required: boolean;
  state: FileSlotState<T>;
  onFile: (f: File) => void;
  onClear: () => void;
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

  const openPicker = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,text/csv";
    input.onchange = () => { if (input.files?.[0]) onFile(input.files[0]); };
    input.click();
  };

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
      onClick={openPicker}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          (e.currentTarget as HTMLDivElement).click();
        }
      }}
      style={{ marginBottom: 14 }}
    >
      <div className="dropzone-head">
        <h4>{label}{required && <span className="req"> *</span>}</h4>
        {state.file !== null && (
          <button
            type="button"
            className="clear-file-btn"
            onClick={(e) => {
              e.stopPropagation();
              onClear();
            }}
            aria-label={`Remove ${label}`}
          >
            Remove
          </button>
        )}
      </div>
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
