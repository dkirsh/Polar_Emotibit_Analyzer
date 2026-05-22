import { StoredSession } from "../api";

export type EventMarker = { event_code: string; utc_ms: number; note?: string };

export type EventInterval = {
  key: string;
  letter: string;
  label: string;
  onsetCode: string;
  offsetCode: string;
  onsetMs: number;
  offsetMs: number;
};

export function sessionEvents(session: StoredSession): EventMarker[] {
  const range = sessionDataRangeMs(session);
  const events = (session.markers_summary?.event_markers ?? [])
    .filter((e) => typeof e.utc_ms === "number" && Number.isFinite(e.utc_ms))
    .filter((e) => !range || (e.utc_ms >= range.min && e.utc_ms <= range.max));
  return events.slice(0, 52);
}

export function chartEventIntervals(session: StoredSession): EventInterval[] {
  return sessionEventIntervals(session).filter(
    (i) => !i.key.includes("_analysis") && !i.key.includes("_epoch")
  );
}

export function sessionEventIntervals(session: StoredSession): EventInterval[] {
  const roomTypes = new Map(
    (session.room_stats ?? [])
      .filter((row) => /^room\d+$/i.test(row.room_key) && row.room_type)
      .map((row) => [row.room_key.toLowerCase(), row.room_type]),
  );
  const byKey = new Map<string, Partial<EventInterval>>();
  for (const event of sessionEvents(session)) {
    const match = event.event_code.match(/^(.+)_(onset|offset)$/);
    if (!match) continue;
    const key = match[1];
    const kind = match[2];
    const current = byKey.get(key) ?? { key };
    if (kind === "onset") {
      current.onsetCode = event.event_code;
      current.onsetMs = event.utc_ms;
    } else {
      current.offsetCode = event.event_code;
      current.offsetMs = event.utc_ms;
    }
    byKey.set(key, current);
  }

  return [...byKey.values()]
    .filter((i): i is Omit<EventInterval, "letter" | "label"> => (
      typeof i.key === "string" &&
      typeof i.onsetCode === "string" &&
      typeof i.offsetCode === "string" &&
      typeof i.onsetMs === "number" &&
      typeof i.offsetMs === "number"
    ))
    .sort((a, b) => a.onsetMs - b.onsetMs)
    .map((i, index) => ({
      ...i,
      letter: intervalMarker(i.key, index, roomTypes),
      label: intervalLabel(i.key, roomTypes),
    }));
}

export function eventLetter(session: StoredSession, eventCode: string): string {
  const interval = sessionEventIntervals(session).find(
    (i) => i.onsetCode === eventCode || i.offsetCode === eventCode,
  );
  return interval?.letter ?? fallbackEventLabel(eventCode);
}

export function fallbackEventLabel(code: string): string {
  return code
    .replace(/^stress_task_/, "task_")
    .replace(/^recording_/, "rec_")
    .replace(/_/g, " ");
}

function intervalLabel(key: string, roomTypes: Map<string, string>): string {
  const room = key.match(/^room(\d+)$/i);
  const roomType = roomTypes.get(key.toLowerCase());
  if (room && roomType) return `Room type ${roomType}`;
  if (room) return "Room type";
  if (key.toLowerCase() === "baseline") return "Baseline";
  return key
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function intervalMarker(key: string, index: number, roomTypes: Map<string, string>): string {
  const room = key.match(/^room(\d+)$/i);
  const roomType = roomTypes.get(key.toLowerCase());
  if (key.toLowerCase() === "baseline") return "Baseline";
  if (room && roomType) return roomType;
  if (room) return "Room";
  return String.fromCharCode(65 + Math.max(0, index % 26));
}

function sessionDataRangeMs(session: StoredSession): { min: number; max: number } | null {
  const times = (session.extended?.cleaned_timeseries ?? [])
    .map((point) => point.timestamp_ms)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (times.length === 0) return null;
  return { min: Math.min(...times), max: Math.max(...times) };
}
