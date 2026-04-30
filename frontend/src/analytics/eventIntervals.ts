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

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export function sessionEvents(session: StoredSession): EventMarker[] {
  return (session.markers_summary?.event_markers ?? [])
    .filter((e) => typeof e.utc_ms === "number" && Number.isFinite(e.utc_ms))
    .slice(0, 52);
}

export function sessionEventIntervals(session: StoredSession): EventInterval[] {
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
      letter: LETTERS[index] ?? `${index + 1}`,
      label: intervalLabel(i.key),
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

function intervalLabel(key: string): string {
  const room = key.match(/^room(\d+)$/i);
  if (room) return `Room ${room[1]}`;
  if (key.toLowerCase() === "baseline") return "Baseline";
  return key
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
