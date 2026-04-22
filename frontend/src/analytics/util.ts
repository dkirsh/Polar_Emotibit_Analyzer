// Small utilities shared across the analytics layer.
//
// 1. `safe(v)` — NaN / ±Infinity sanitiser for chart coordinates.
//    ChartRenderer had zero NaN guards prior to 2026-04-21; this helper
//    closes that gap. Returns `null` for any non-finite number so the
//    renderer can treat it as a gap in the chart rather than passing
//    NaN to SVG coordinates.
//
// 2. `annotateGlossaryTerms(text)` — wraps known glossary terms in
//    <span title="one-line gloss"> on first occurrence per call.
//    Surfaces the 35-entry glossary as hover tooltips in the
//    whatItShows / howToRead / architecturalMeaning prose blocks.

import React from "react";
import { allGlossaryTerms, lookupGlossary } from "./glossary";

/** NaN / ±Infinity guard. Returns null for any non-finite input. */
export function safe(v: number | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v !== "number") return null;
  return Number.isFinite(v) ? v : null;
}

/** A longer-first sort so "SD1/SD2 ratio" is matched before "SD1". */
function glossaryTermsLongestFirst(): string[] {
  return allGlossaryTerms().sort((a, b) => b.length - a.length);
}

/**
 * Walk `text` and return an array of React nodes where each known
 * glossary term is wrapped in a <span> carrying its one-line gloss.
 *
 * Only the FIRST occurrence of each term in a given `text` is wrapped
 * — repeated annotations make prose visually noisy. Terms are matched
 * case-insensitively on word boundaries, longest-first so compound
 * terms beat their prefixes ("SD1/SD2 ratio" before "SD1", "LF_nu
 * (LF normalised units)" before "LF").
 */
export function annotateGlossaryTerms(text: string): React.ReactNode[] {
  const terms = glossaryTermsLongestFirst();
  const used = new Set<string>();

  // Build a single regex that matches any term on word boundaries.
  // Escape regex metacharacters in each term first. The "|" join
  // preserves the longest-first ordering because regex alternation
  // is left-to-right.
  const escaped = terms.map((t) =>
    t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
  );
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");

  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(text)) !== null) {
    const [matched] = m;
    const normalised = matched.toLowerCase();
    if (used.has(normalised)) {
      continue; // only annotate first occurrence
    }
    used.add(normalised);

    // The matched surface text might differ in casing from the glossary
    // key (which preserves the term's original casing). Find the
    // canonical entry by matching case-insensitively.
    const entry = terms
      .map((t) => lookupGlossary(t))
      .find((e) => e && e.term.toLowerCase() === normalised);
    if (!entry) continue;

    if (m.index > lastIndex) {
      nodes.push(text.slice(lastIndex, m.index));
    }
    nodes.push(
      React.createElement(
        "span",
        {
          key: `${normalised}-${m.index}`,
          title: entry.oneLiner,
          style: {
            borderBottom: "1px dotted currentColor",
            cursor: "help",
          },
        },
        matched,
      ),
    );
    lastIndex = m.index + matched.length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}
