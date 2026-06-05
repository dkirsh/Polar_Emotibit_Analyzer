import React, { useCallback, useEffect, useRef, useState } from "react";
import JSZip from "jszip";
import { useNavigate } from "react-router-dom";
import {
  analyze,
  analyzeSingle,
  listRecentSessions,
  RecentSession,
  ValidateEmotibitResponse,
  ValidateMarkersResponse,
  ValidateOrderAffectResponse,
  ValidatePolarResponse,
  ValidateVernierResponse,
  validateEmotibitCsv,
  validateMarkersCsv,
  validateOrderAffectCsv,
  validatePolarCsv,
  validateVernierXlsx,
} from "../api";

type FileSlotState<T> =
  | { file: null }
  | { file: File; status: "validating"; preview?: string[][] }
  | { file: File; status: "valid"; info: T; preview?: string[][] }
  | { file: File; status: "invalid"; error: string; preview?: string[][] };

type SavedSettings = {
  sessionId: string;
  subjectId: string;
  studyId: string;
  sessionDate: string;
  operator: string;
  notes: string;
};

type UploadSlot = "em" | "pol" | "mk" | "oa" | "vn";

type ToastState = { msg: string; type: "success" | "warn" } | null;

type ReroutePrompt = {
  file: File;
  fromSlot: UploadSlot;
  toSlot: UploadSlot;
  message: string;
} | null;

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
  orderAffect: { file: null } as FileSlotState<ValidateOrderAffectResponse>,
  vernier: { file: null } as FileSlotState<ValidateVernierResponse>,
};

/** Parse the first 6 lines of a CSV file for preview (1 header + 5 data rows). */
function parseCsvPreview(file: File): Promise<string[][] | undefined> {
  const name = file.name.toLowerCase();
  // Skip non-CSV files (XLSX/ZIP) — no client-side parser for those
  if (name.endsWith(".xlsx") || name.endsWith(".xls") || name.endsWith(".zip")) {
    return Promise.resolve(undefined);
  }
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onerror = () => resolve(undefined);
    reader.onload = () => {
      const text = String(reader.result ?? "");
      const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
      if (lines.length === 0) { resolve(undefined); return; }
      const rows = lines.slice(0, 6).map((line) => line.split(","));
      resolve(rows);
    };
    // Read first 16KB — enough for 6 lines of any reasonable CSV
    reader.readAsText(file.slice(0, 16384));
  });
}

/**
 * Bundle multiple files into a single ZIP using JSZip.
 * Returns a File object named "bundled_<N>_files.zip".
 */
async function bundleFilesAsZip(files: File[]): Promise<File> {
  const zip = new JSZip();
  for (const f of files) {
    const buf = await f.arrayBuffer();
    zip.file(f.name, buf);
  }
  const blob = await zip.generateAsync({ type: "blob", compression: "DEFLATE" });
  return new File([blob], `bundled_${files.length}_files.zip`, { type: "application/zip" });
}

/** Detect file type using header-sniffing logic. Returns the best-guess slot or null. */
async function detectFileType(file: File): Promise<UploadSlot | null> {
  const name = file.name.toLowerCase();

  if (name.endsWith(".xlsx") || name.endsWith(".xls")) {
    return "vn"; // Vernier is the only XLSX slot
  }

  if (name.endsWith(".zip")) {
    return null; // Ambiguous — ZIP could be any slot
  }

  const header = await readCsvHeader(file);
  const columns = header.split(",").map((c) => c.trim().toLowerCase());
  const has = (col: string) => columns.includes(col);
  const hasAny = (cols: string[]) => cols.some(has);
  const filenameHas = (pattern: RegExp) => pattern.test(file.name);

  const looksLikeNativeEmotibit = has("localtimestamp") || filenameHas(/_E[AXYZ]\.csv$/i);
  const looksLikeNativePolar = has("utc_epoch_ns");
  const looksLikeMarkers = has("event_code") || has("utc_ms") || filenameHas(/(^|[_\-\s])(event|events|marker|markers|sync)([_\-\s.]|$)/i);
  const looksLikePolar = looksLikeNativePolar || hasAny(["hr_bpm", "rr_ms", "ecg_uv", "ecg_mv", "ecg", "raw_ecg", "raw_ecg_uv", "voltage_uv", "timestamp_ns"]) || filenameHas(/polar|h10|hrv|ecg|rr/i);
  const looksLikeEmotibit = looksLikeNativeEmotibit || has("eda_us") || hasAny(["acc_x", "acc_y", "acc_z", "resp_bpm"]) || filenameHas(/emotibit|eda|gsr/i);
  const looksLikeOrderAffect = hasAny(["room_type", "room_order", "valence", "arousal"]) || filenameHas(/order|affect|condition/i);

  // Return the most confident match, or null if ambiguous
  const matches: UploadSlot[] = [];
  if (looksLikeMarkers) matches.push("mk");
  if (looksLikeEmotibit && !looksLikePolar) matches.push("em");
  if (looksLikePolar && !looksLikeEmotibit) matches.push("pol");
  if (looksLikeEmotibit && looksLikePolar) { matches.push("em"); matches.push("pol"); }
  if (looksLikeOrderAffect) matches.push("oa");

  if (matches.length === 1) return matches[0];
  // Prefer markers if exclusively markers
  if (matches.length === 0) return null;
  // Multiple matches → ambiguous
  return null;
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
  const [orderAffect, setOrderAffect] = useState<FileSlotState<ValidateOrderAffectResponse>>(draft.orderAffect);
  const [vernier, setVernier] = useState<FileSlotState<ValidateVernierResponse>>(draft.vernier);

  // Submit state
  const [submitting, setSubmitting] = useState(false);
  const [submitStage, setSubmitStage] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Toast state
  const [toast, setToast] = useState<ToastState>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reroute modal state
  const [reroutePrompt, setReroutePrompt] = useState<ReroutePrompt>(null);

  // Page-level drag state
  const [pageDrag, setPageDrag] = useState(false);
  const dragCounter = useRef(0);

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
  useEffect(() => { draft.orderAffect = orderAffect; }, [orderAffect]);
  useEffect(() => { draft.vernier = vernier; }, [vernier]);

  const showToast = useCallback((msg: string, type: "success" | "warn") => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ msg, type });
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }, []);

  const hasValidEmotibit = emotibit.file !== null && "status" in emotibit && emotibit.status === "valid";
  const hasValidPolar = polar.file !== null && "status" in polar && polar.status === "valid";

  /**
   * Accept one or more files for a slot. If multiple files are provided,
   * they are bundled into a single ZIP client-side before validation.
   */
  const onDropFiles = useCallback(
    async (which: UploadSlot, files: File[]) => {
      if (files.length === 0) return;
      let file: File;
      if (files.length === 1) {
        file = files[0];
      } else {
        // Bundle multiple files into a ZIP
        showToast(`Bundling ${files.length} files into ZIP…`, "success");
        file = await bundleFilesAsZip(files);
      }
      onDropFile(which, file);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [/* forward to onDropFile */],
  );

  const onDropFile = useCallback(
    async (
      which: UploadSlot,
      file: File,
    ) => {
      const existing = which === "em" ? emotibit.file : which === "pol" ? polar.file : which === "mk" ? markers.file : which === "oa" ? orderAffect.file : vernier.file;
      if (existing && !window.confirm(`${slotLabel(which)} already contains ${existing.name}. Replace it with ${file.name}?`)) {
        return;
      }

      // Parse CSV preview immediately (before server validation)
      const preview = await parseCsvPreview(file);

      const localCheck = await checkFileForSlot(file, which);
      if (!localCheck.ok) {
        // Instead of just blocking, detect if the file belongs elsewhere and offer to reroute
        const detectedSlot = await detectFileType(file);
        if (detectedSlot && detectedSlot !== which) {
          setReroutePrompt({
            file,
            fromSlot: which,
            toSlot: detectedSlot,
            message: `This looks like a ${slotFriendlyName(detectedSlot)} file. Route to ${slotLabel(detectedSlot)} instead?`,
          });
          return;
        }
        // No reroute possible — show as invalid with preview
        const invalid = { file, status: "invalid" as const, error: localCheck.message, preview };
        if (which === "em") setEmotibit(invalid);
        else if (which === "pol") setPolar(invalid);
        else if (which === "mk") setMarkers(invalid);
        else if (which === "oa") setOrderAffect(invalid);
        else setVernier(invalid);
        return;
      }
      if (localCheck.confirm && !window.confirm(localCheck.confirm)) {
        return;
      }

      if (which === "em") {
        setEmotibit({ file, status: "validating", preview });
        try { setEmotibit({ file, status: "valid", info: await validateEmotibitCsv(file), preview }); }
        catch (e) { setEmotibit({ file, status: "invalid", error: (e as Error).message, preview }); }
      } else if (which === "pol") {
        setPolar({ file, status: "validating", preview });
        try { setPolar({ file, status: "valid", info: await validatePolarCsv(file), preview }); }
        catch (e) { setPolar({ file, status: "invalid", error: (e as Error).message, preview }); }
      } else if (which === "mk") {
        setMarkers({ file, status: "validating", preview });
        try { setMarkers({ file, status: "valid", info: await validateMarkersCsv(file), preview }); }
        catch (e) { setMarkers({ file, status: "invalid", error: (e as Error).message, preview }); }
      } else if (which === "oa") {
        setOrderAffect({ file, status: "validating", preview });
        try { setOrderAffect({ file, status: "valid", info: await validateOrderAffectCsv(file), preview }); }
        catch (e) { setOrderAffect({ file, status: "invalid", error: (e as Error).message, preview }); }
      } else {
        setVernier({ file, status: "validating", preview });
        try { setVernier({ file, status: "valid", info: await validateVernierXlsx(file), preview }); }
        catch (e) { setVernier({ file, status: "invalid", error: (e as Error).message, preview }); }
      }
    },
    [emotibit.file, markers.file, polar.file, orderAffect.file, vernier.file],
  );

  /** Handle a file dropped on the page (not on a specific slot) — auto-detect and route. */
  const onPageDrop = useCallback(
    async (file: File) => {
      const detectedSlot = await detectFileType(file);
      if (detectedSlot) {
        showToast(`✓ Detected as ${slotFriendlyName(detectedSlot)} — routed to ${slotLabel(detectedSlot)}`, "success");
        onDropFile(detectedSlot, file);
      } else {
        showToast(`Could not auto-detect file type for ${file.name}. Drop it on a specific slot.`, "warn");
      }
    },
    [onDropFile, showToast],
  );

  /** Handle reroute modal confirmation. */
  const onRerouteConfirm = useCallback(() => {
    if (!reroutePrompt) return;
    const { file, toSlot } = reroutePrompt;
    setReroutePrompt(null);
    showToast(`✓ Rerouted to ${slotLabel(toSlot)}`, "success");
    onDropFile(toSlot, file);
  }, [reroutePrompt, onDropFile, showToast]);

  const onRerouteCancel = useCallback(() => {
    setReroutePrompt(null);
  }, []);

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
          order_affect_file: orderAffect.file ?? null,
          vernier_file: vernier.file ?? null,
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
    <main
      className={`page${pageDrag ? " page-drop-active" : ""}`}
      role="main"
      aria-label="New analysis session"
      onDragOver={(e) => { e.preventDefault(); }}
      onDragEnter={(e) => {
        e.preventDefault();
        dragCounter.current++;
        setPageDrag(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        dragCounter.current--;
        if (dragCounter.current <= 0) { dragCounter.current = 0; setPageDrag(false); }
      }}
      onDrop={(e) => {
        e.preventDefault();
        dragCounter.current = 0;
        setPageDrag(false);
        // Handle single or multiple files dropped on the page
        const fileList = e.dataTransfer.files;
        if (fileList.length === 1) {
          onPageDrop(fileList[0]);
        } else if (fileList.length > 1) {
          // Multiple files dropped on page — try to auto-detect and route
          onPageDrop(fileList[0]); // Route first file; user can multi-drop on slots
        }
      }}
    >
      {/* Toast notification */}
      {toast && (
        <div className={`upload-toast ${toast.type}`} role="status" aria-live="polite">
          {toast.msg}
        </div>
      )}

      {/* Reroute modal */}
      {reroutePrompt && (
        <div className="reroute-modal-overlay" onClick={onRerouteCancel}>
          <div className="reroute-modal" onClick={(e) => e.stopPropagation()}>
            <p>{reroutePrompt.message}</p>
            <div className="reroute-modal-btns">
              <button className="btn-yes" onClick={onRerouteConfirm}>Yes</button>
              <button className="btn-no" onClick={onRerouteCancel}>No</button>
            </div>
          </div>
        </div>
      )}

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
                   placeholder="e.g. P01 or P022-040 (range for batch ZIP)" />
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
            onFiles={(files) => onDropFiles("em", files)}
            onClear={() => setEmotibit({ file: null })}
            describeInfo={(info) =>
              `${info.n_rows} rows, ${info.timestamp_range_ms.span_s}s · ${info.has_accelerometer ? "accelerometer present" : "no accelerometer"}${info.has_respiration ? " · resp_bpm present" : ""}`}
          />
          <DropSlot
            label="Polar H10 CSV (raw ECG preferred)"
            required={false}
            state={polar}
            onFile={(f) => onDropFile("pol", f)}
            onFiles={(files) => onDropFiles("pol", files)}
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
            onFiles={(files) => onDropFiles("mk", files)}
            onClear={() => setMarkers({ file: null })}
            describeInfo={(info) =>
              `${info.n_events ?? info.n_rows} markers · codes: ${(info.event_codes ?? []).join(", ") || "none"}`
            }
          />
          <DropSlot
            label="Order & Affect CSV/ZIP (room order + valence/arousal)"
            required={false}
            state={orderAffect}
            onFile={(f) => onDropFile("oa", f)}
            onFiles={(files) => onDropFiles("oa", files)}
            onClear={() => setOrderAffect({ file: null })}
            describeInfo={(info) =>
              `${info.n_rooms ?? 0} rooms · subject ${info.subject_id_detected ?? "?"} · types: ${(info.room_types ?? []).join(", ") || "none"}`
            }
          />
          <DropSlot
            label="Vernier Respiration Belt XLSX (respiratory force)"
            required={false}
            state={vernier}
            onFile={(f) => onDropFile("vn", f)}
            onFiles={(files) => onDropFiles("vn", files)}
            onClear={() => setVernier({ file: null })}
            describeInfo={(info) =>
              `${info.n_rows} samples · ${info.duration_min?.toFixed(1) ?? "?"}min · ${info.sample_rate_hz}Hz resampled${info.vendor_rr_median ? ` · vendor RR ${info.vendor_rr_median} bpm` : ""}`
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
  if (which === "mk") return "Event markers slot";
  if (which === "oa") return "Order & Affect slot";
  return "Vernier respiration slot";
}

function slotFriendlyName(which: UploadSlot): string {
  if (which === "em") return "EmotiBit CSV";
  if (which === "pol") return "Polar H10 CSV";
  if (which === "mk") return "Event markers CSV";
  if (which === "oa") return "Order & Affect CSV";
  return "Vernier XLSX";
}

async function checkFileForSlot(
  file: File,
  which: UploadSlot,
): Promise<{ ok: true; confirm?: string } | { ok: false; message: string }> {
  const name = file.name.toLowerCase();

  // ZIP files are always accepted — the backend classifies contents
  if (name.endsWith(".zip")) {
    return { ok: true };
  }

  const header = await readCsvHeader(file);
  const columns = header.split(",").map((c) => c.trim().toLowerCase());
  const has = (col: string) => columns.includes(col);
  const hasAny = (cols: string[]) => cols.some(has);
  const filenameHas = (pattern: RegExp) => pattern.test(file.name);

  // Native format detection
  const looksLikeNativeEmotibit = has("localtimestamp") || filenameHas(/_E[AXYZ]\.csv$/i);
  const looksLikeNativePolar = has("utc_epoch_ns");
  const looksLikeMarkers = has("event_code") || has("utc_ms") || filenameHas(/(^|[_\-\s])(event|events|marker|markers|sync)([_\-\s.]|$)/i);
  const looksLikePolar = looksLikeNativePolar || hasAny(["hr_bpm", "rr_ms", "ecg_uv", "ecg_mv", "ecg", "raw_ecg", "raw_ecg_uv", "voltage_uv", "timestamp_ns"]) || filenameHas(/polar|h10|hrv|ecg|rr/i);
  const looksLikeEmotibit = looksLikeNativeEmotibit || has("eda_us") || hasAny(["acc_x", "acc_y", "acc_z", "resp_bpm"]) || filenameHas(/emotibit|eda|gsr/i);
  const looksLikeOrderAffect = hasAny(["room_type", "room_order", "valence", "arousal"]) || filenameHas(/order|affect|condition/i);

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

  if (which === "oa") {
    if (looksLikePolar || looksLikeEmotibit || looksLikeMarkers) {
      return { ok: false, message: "This does not look like an Order & Affect file. Expected columns: subject_id, room_number, room_type, valence, arousal." };
    }
    if (!looksLikeOrderAffect) {
      return { ok: true, confirm: `${file.name} does not show the expected Order & Affect columns (subject_id, room_type, valence, arousal). Try it anyway?` };
    }
  }

  if (which === "vn") {
    if (!name.endsWith(".xlsx") && !name.endsWith(".xls")) {
      return { ok: true, confirm: `${file.name} is not named as an Excel file (.xlsx). Vernier belt data should be in .xlsx format. Try it anyway?` };
    }
    return { ok: true };
  }

  if (!name.endsWith(".csv") && !name.endsWith(".zip")) {
    return { ok: true, confirm: `${file.name} is not named as a .csv or .zip file. Try it anyway?` };
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

/** Collapsible data preview showing header + first 5 rows. */
function DataPreview({ preview }: { preview?: string[][] }) {
  if (!preview || preview.length < 2) return null;
  const [header, ...rows] = preview;
  return (
    <details className="data-preview" onClick={(e) => e.stopPropagation()}>
      <summary>Preview ({Math.min(rows.length, 5)} rows)</summary>
      <div className="data-preview-table">
        <table>
          <thead>
            <tr>
              {header.map((col, i) => (
                <th key={i}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 5).map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td key={ci}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

// Helper component: drag-drop + validation feedback.
function DropSlot<T>({
  label, required, state, onFile, onFiles, onClear, describeInfo,
}: {
  label: string;
  required: boolean;
  state: FileSlotState<T>;
  onFile: (f: File) => void;
  onFiles?: (files: File[]) => void;
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
    input.multiple = true;
    input.accept = ".csv,.zip,.xlsx,text/csv,application/zip,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    input.onchange = () => {
      if (!input.files || input.files.length === 0) return;
      if (input.files.length === 1) {
        onFile(input.files[0]);
      } else {
        const arr = Array.from(input.files);
        onFiles ? onFiles(arr) : onFile(arr[0]);
      }
    };
    input.click();
  };

  const preview = ("status" in state && state.status !== "validating") ? (state as { preview?: string[][] }).preview : ("preview" in state ? (state as { preview?: string[][] }).preview : undefined);

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
        e.stopPropagation();
        setDrag(false);
        const fileList = e.dataTransfer.files;
        if (fileList.length === 1) {
          onFile(fileList[0]);
        } else if (fileList.length > 1) {
          const arr = Array.from(fileList);
          onFiles ? onFiles(arr) : onFile(arr[0]);
        }
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
        <p style={{ color: "#888" }}>Drag CSV(s) or ZIP here, or click to browse (multi-select supported)</p>
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
          <DataPreview preview={preview} />
        </>
      )}
    </div>
  );
}
