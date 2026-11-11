// Display helpers for the repo summary page. They mirror qa_metrics.py and
// cliq_notify.py, which compute the same figures for the Cliq message, so both
// read alike.

export const NOT_AVAILABLE = "–";

export function trendLabel(current: number | null, previous: number | null): string {
  if (current === null || previous === null) return NOT_AVAILABLE;
  const delta = current - previous;
  if (delta > 0) return `↑${delta}`;
  if (delta < 0) return `↓${-delta}`;
  return "→";
}

export function percent(part: number | null, whole: number | null): number | null {
  if (part === null || !whole) return null;
  return Math.round((100 * part) / whole);
}

// "12% failed · prev 1 / 30" for the QA failed / tested tile.
export function failureDetail(
  failed: number | null,
  tested: number | null,
  failedPrev: number | null,
  testedPrev: number | null,
): string {
  const share = percent(failed, tested);
  const shareText = share === null ? NOT_AVAILABLE : `${share}% failed`;
  return `${shareText} · prev ${failedPrev ?? NOT_AVAILABLE} / ${testedPrev ?? NOT_AVAILABLE}`;
}

export function sumKnown(values: Array<number | null>): number | null {
  const known = values.filter((value): value is number => value !== null);
  return known.length === 0 ? null : known.reduce((total, value) => total + value, 0);
}
