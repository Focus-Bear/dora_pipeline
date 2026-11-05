// Display helpers for the repo summary page. They mirror qa_metrics.py, which
// computes the same indicators for the Cliq message, so both read alike.

export const NOT_AVAILABLE = "–";

// A dev-to-QA ratio at or above this means issues reach QA at least as fast
// as new ones are filed.
const ROADMAP_AHEAD_RATIO = 1;

export function trendLabel(current: number | null, previous: number | null): string {
  if (current === null || previous === null) return NOT_AVAILABLE;
  const delta = current - previous;
  if (delta > 0) return `↑${delta}`;
  if (delta < 0) return `↓${-delta}`;
  return "→";
}

export function isAhead(movedToQA: number, created: number): boolean | null {
  if (movedToQA === 0 && created === 0) return null;
  if (created === 0) return true;
  return movedToQA / created >= ROADMAP_AHEAD_RATIO;
}

export function progressIndicator(movedToQA: number, created: number): string {
  const ahead = isAhead(movedToQA, created);
  if (ahead === null) return NOT_AVAILABLE;
  return ahead ? "✅" : "⚠️";
}

export function formatRatio(movedToQA: number, created: number): string {
  if (created === 0) return movedToQA > 0 ? "∞" : NOT_AVAILABLE;
  return `${(movedToQA / created).toFixed(2)}×`;
}

export function sumKnown(values: Array<number | null>): number | null {
  const known = values.filter((value): value is number => value !== null);
  return known.length === 0 ? null : known.reduce((total, value) => total + value, 0);
}
