// Chart palette — reads CSS custom properties defined in styles.css
// so the colour values live in a single source of truth (the :root
// block) and can be re-themed without editing TSX.
//
// SSR / test-environment safety: document.documentElement is not
// always present (node-based tests, SSR). The `read()` helper falls
// back to a baked-in default when getComputedStyle returns an empty
// string. The defaults match the CSS definitions so the two stay in
// sync.
//
// Read once at module load time; the palette object is a frozen
// snapshot for the session. This matches how the earlier inline
// PALETTE was used and avoids per-render getComputedStyle calls.

type PaletteKey =
  | "hr"
  | "eda"
  | "accent"
  | "bg"
  | "grid"
  | "text"
  | "sub"
  | "good"
  | "warn"
  | "bad"
  | "resp";

const DEFAULTS: Record<PaletteKey, string> = {
  hr: "#00C896",
  eda: "#E8872A",
  accent: "#4A6FA8",
  bg: "#141414",
  grid: "#2F2F2F",
  text: "#E8E8E8",
  sub: "#B8B8B8",
  good: "#1A7050",
  warn: "#B8821A",
  bad: "#B83A4A",
  resp: "#A78BFA",
};

const CSS_VAR_NAMES: Record<PaletteKey, string> = {
  hr: "--chart-hr",
  eda: "--chart-eda",
  accent: "--chart-accent",
  bg: "--chart-bg",
  grid: "--chart-grid",
  text: "--chart-text",
  sub: "--chart-sub",
  good: "--chart-good",
  warn: "--chart-warn",
  bad: "--chart-bad",
  resp: "--chart-resp",
};

function readPalette(): Record<PaletteKey, string> {
  const result: Record<PaletteKey, string> = { ...DEFAULTS };
  if (typeof document === "undefined" || !document.documentElement) {
    return result;
  }
  try {
    const rootStyle = getComputedStyle(document.documentElement);
    for (const key of Object.keys(DEFAULTS) as PaletteKey[]) {
      const varValue = rootStyle.getPropertyValue(CSS_VAR_NAMES[key]).trim();
      if (varValue) result[key] = varValue;
    }
  } catch {
    // Ignore; defaults stand.
  }
  return result;
}

export const PALETTE: Readonly<Record<PaletteKey, string>> = Object.freeze(
  readPalette(),
);
