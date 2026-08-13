export const WIDE_LAYOUT_COLUMNS = 104;
export const SIDEBAR_WIDTH = 28;
export const MAX_RECENT_THREADS = 6;

export function isWideLayout(columns) {
  return columns >= WIDE_LAYOUT_COLUMNS;
}

export function deriveRecentThreads(items, limit = MAX_RECENT_THREADS) {
  return items
    .filter((item) => item.kind === 'user' && String(item.text || '').trim())
    .slice(-limit)
    .reverse()
    .map((item) => String(item.text).replace(/\s+/g, ' ').trim());
}

