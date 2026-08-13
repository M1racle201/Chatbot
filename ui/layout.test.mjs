import test from 'node:test';
import assert from 'node:assert/strict';

let layout = {};
try {
  layout = await import('./layout.mjs');
} catch {
  // The RED run intentionally starts before layout.mjs exists.
}

test('shows the sidebar only when the terminal is at least 104 columns', () => {
  assert.equal(layout.isWideLayout?.(103), false);
  assert.equal(layout.isWideLayout?.(104), true);
});

test('derives at most six newest user prompts for recent threads', () => {
  const items = Array.from({length: 8}, (_, index) => ({
    kind: index === 2 ? 'assistant' : 'user',
    text: `  prompt ${index}\ncontinued  `,
  }));

  assert.deepEqual(layout.deriveRecentThreads?.(items), [
    'prompt 7 continued',
    'prompt 6 continued',
    'prompt 5 continued',
    'prompt 4 continued',
    'prompt 3 continued',
    'prompt 1 continued',
  ]);
});

