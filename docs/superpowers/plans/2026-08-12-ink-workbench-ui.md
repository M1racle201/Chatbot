# Ink Workbench UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the existing Ink presentation layer as a responsive two-column coding-agent workbench that closely matches the approved reference image while preserving every command and bridge event.

**Architecture:** Keep bridge lifecycle, command parsing, and application state in `ui/index.jsx`. Move responsive calculations and recent-thread derivation into pure functions in `ui/layout.mjs`, and move all visual components into `ui/workbench.jsx`. Wide terminals render a 28-column sidebar plus workspace; terminals below 104 columns render the workspace alone.

**Tech Stack:** React 19, Ink 6, ink-text-input, Node built-in test runner, Python unittest source-contract tests, esbuild.

---

## File Structure

- Create `ui/layout.mjs`: pure responsive layout and recent-thread helper functions.
- Create `ui/layout.test.mjs`: executable behavior tests for the pure helpers.
- Create `ui/workbench.jsx`: sidebar, header, messages, tool/result panels, transcript, and composer.
- Modify `ui/index.jsx`: retain controller behavior and compose the new workbench shell.
- Modify `ui/package.json`: expose non-interactive `build` and Node `test` scripts while preserving `start`.
- Modify `tests/test_ui_layout.py`: verify component boundaries, semantic labels, responsive integration, and preserved command paths.

### Task 1: Responsive Layout Rules

**Files:**
- Create: `ui/layout.test.mjs`
- Create: `ui/layout.mjs`
- Modify: `ui/package.json`

- [ ] **Step 1: Write the failing layout behavior tests**

Create `ui/layout.test.mjs` with a guarded dynamic import so the first run is an assertion failure, not an import crash:

```js
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

test('reserves 28 columns for the wide sidebar', () => {
  assert.equal(layout.getWorkspaceColumns?.(140), 112);
  assert.equal(layout.getWorkspaceColumns?.(80), 80);
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

test('keeps a usable transcript in compact terminals', () => {
  assert.equal(layout.getTranscriptRows?.(40), 32);
  assert.equal(layout.getTranscriptRows?.(20), 13);
});
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
node --test ui/layout.test.mjs
```

Expected: four failed tests because the responsive functions are missing.

- [ ] **Step 3: Implement the minimal pure layout module**

Create `ui/layout.mjs`:

```js
export const WIDE_LAYOUT_COLUMNS = 104;
export const SIDEBAR_WIDTH = 28;
export const MAX_RECENT_THREADS = 6;

export function isWideLayout(columns) {
  return columns >= WIDE_LAYOUT_COLUMNS;
}

export function getWorkspaceColumns(columns) {
  return isWideLayout(columns) ? columns - SIDEBAR_WIDTH : columns;
}

export function deriveRecentThreads(items, limit = MAX_RECENT_THREADS) {
  return items
    .filter((item) => item.kind === 'user' && String(item.text || '').trim())
    .slice(-limit)
    .reverse()
    .map((item) => String(item.text).replace(/\s+/g, ' ').trim());
}

export function getTranscriptRows(rows) {
  return Math.max(rows - (rows < 24 ? 7 : 8), 6);
}
```

- [ ] **Step 4: Add deterministic package scripts**

Change `ui/package.json` scripts to:

```json
{
  "scripts": {
    "build": "esbuild index.jsx --bundle --platform=node --format=esm --alias:react-devtools-core=./devtools-stub.js --banner:js=\"import {createRequire} from 'module';const require=createRequire(import.meta.url);\" --outfile=.build/index.mjs",
    "test": "node --test layout.test.mjs",
    "start": "npm run build && node .build/index.mjs"
  }
}
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
npm.cmd --prefix ui test
```

Expected: four tests pass, zero fail.

- [ ] **Step 6: Commit the responsive foundation**

```powershell
git add ui/layout.mjs ui/layout.test.mjs ui/package.json
git commit -m "test: define Ink workbench layout rules"
```

### Task 2: Workbench Component Contract

**Files:**
- Modify: `tests/test_ui_layout.py`
- Create: `ui/workbench.jsx`

- [ ] **Step 1: Replace the old source-contract tests with the new component contract**

Use separate source reads and assertions:

```python
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
APP_SOURCE = (ROOT / "ui" / "index.jsx").read_text(encoding="utf-8")
WORKBENCH_SOURCE = (
    ROOT / "ui" / "workbench.jsx"
).read_text(encoding="utf-8") if (ROOT / "ui" / "workbench.jsx").exists() else ""


class TestInkUiLayout(unittest.TestCase):
    def test_workbench_has_reference_image_regions(self):
        for marker in (
            "function Sidebar(",
            "function WorkspaceHeader(",
            "function ToolActivity(",
            "function ResultPanel(",
            "function Transcript(",
            "function Composer(",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, WORKBENCH_SOURCE)

    def test_visual_copy_matches_the_approved_workbench(self):
        for copy in (
            "VibeChatbot",
            "Threads",
            "Files",
            "Tasks",
            "Recent threads",
            "Agent ready",
            "Context:",
            "Ask the agent to inspect, build, or explain...",
            "You",
            "Agent",
        ):
            with self.subTest(copy=copy):
                self.assertIn(copy, WORKBENCH_SOURCE)

    def test_app_integrates_wide_and_compact_layouts(self):
        self.assertIn("isWideLayout(columns)", APP_SOURCE)
        self.assertIn("getWorkspaceColumns(columns)", APP_SOURCE)
        self.assertIn("<Sidebar", APP_SOURCE)
        self.assertIn("<WorkspaceHeader", APP_SOURCE)

    def test_existing_command_paths_are_preserved(self):
        for command in (
            "/chat", "/agent", "/agentic", "/clear_history",
            "/clear_memory", "/exit",
        ):
            with self.subTest(command=command):
                self.assertIn(command, APP_SOURCE)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the source-contract tests and verify RED**

Run:

```powershell
& 'C:\Users\21776\AppData\Local\Programs\Python\Python314\python.exe' tests\test_ui_layout.py
```

Expected: failures for missing `workbench.jsx`, components, and shell integration; existing command assertions remain green.

- [ ] **Step 3: Implement the workbench visual components**

Create `ui/workbench.jsx` with these exports and responsibilities:

```jsx
import React from 'react';
import {Box, Text} from 'ink';
import TextInput from 'ink-text-input';
import {deriveRecentThreads, getTranscriptRows} from './layout.mjs';

const COLOR = {
  amber: '#F2B84B',
  cyan: '#58D1C2',
  surface: '#191F27',
  border: '#30363D',
  text: '#F2F2ED',
  muted: '#9CA3AD',
  success: '#68D391',
  error: '#F47067',
};

const MODE_LABEL = {
  idle: 'Auto',
  chat: 'Chat',
  agent: 'Agent',
  agentic: 'Agentic',
};

export function Sidebar({items, rows}) {
  const recent = deriveRecentThreads(items);
  return (
    <Box width={28} height={rows} flexDirection="column" paddingX={1}
      borderStyle="single" borderTop={false} borderBottom={false} borderLeft={false}
      borderColor={COLOR.border}>
      <Box height={3} alignItems="center"><Text bold color={COLOR.amber}>VibeChatbot⌄</Text></Box>
      <Box flexDirection="column" marginTop={1}>
        <Text bold color={COLOR.amber} backgroundColor={COLOR.surface}>{'  ◇  Threads              '}</Text>
        <Text color={COLOR.muted}>{'  ▣  Files'}</Text>
        <Text color={COLOR.muted}>{'  □  Tasks'}</Text>
      </Box>
      <Box flexDirection="column" marginTop={2}>
        <Text dimColor>Recent threads</Text>
        {(recent.length ? recent : ['No recent threads']).map((thread, index) => (
          <Text key={`${thread}-${index}`} color={index === 0 ? COLOR.amber : COLOR.text}
            wrap="truncate-end">{thread}</Text>
        ))}
      </Box>
      <Box flexGrow={1} />
      <Box marginBottom={1}><Text color={COLOR.muted}>⚙  Settings</Text></Box>
    </Box>
  );
}

export function WorkspaceHeader({mode, busy, compact}) {
  return (
    <Box height={3} paddingX={2} alignItems="center" justifyContent="space-between"
      borderStyle="single" borderTop={false} borderLeft={false} borderRight={false}
      borderColor={COLOR.border}>
      <Text><Text color={COLOR.cyan}>●</Text>{`  ${busy ? 'Agent working' : 'Agent ready'}`}</Text>
      <Text color={COLOR.muted}>{compact ? MODE_LABEL[mode] : `Context: VibeChatbot · ${MODE_LABEL[mode]}`}</Text>
    </Box>
  );
}

export function ToolActivity({text, busy = false}) {
  return (
    <Box borderStyle="single" borderColor={COLOR.border} paddingX={1} marginBottom={1}>
      <Text color={busy ? COLOR.amber : COLOR.success}>{busy ? '○' : '✓'}</Text>
      <Text bold>{'  Tool  '}</Text>
      <Text color={COLOR.muted} wrap="truncate-end">{text}</Text>
    </Box>
  );
}

export function ResultPanel({text}) {
  return (
    <Box flexDirection="column" borderStyle="single" borderColor={COLOR.border} marginBottom={1}>
      <Box paddingX={1} backgroundColor={COLOR.surface}><Text bold>Result</Text></Box>
      <Box paddingX={1}><Text color={COLOR.text} wrap="wrap">{text}</Text></Box>
    </Box>
  );
}
```

Continue the same file with the exact message, transcript, and composer implementations:

```jsx
function Message({item, columns}) {
  const bodyWidth = Math.max(columns - 6, 20);
  switch (item.kind) {
    case 'user':
      return (
        <Box flexDirection="column" marginBottom={1} width={columns}>
          <Text bold color={COLOR.amber}>You</Text>
          <Text color={COLOR.text} wrap="wrap" width={bodyWidth}>{item.text}</Text>
        </Box>
      );
    case 'assistant':
      return (
        <Box flexDirection="column" marginBottom={1} width={columns}>
          <Text bold color={COLOR.cyan}>Agent</Text>
          <Text color={COLOR.text} wrap="wrap" width={bodyWidth}>{item.text}</Text>
        </Box>
      );
    case 'log':
      return <ToolActivity text={item.text} />;
    case 'notice':
      return <Text color={COLOR.muted} wrap="wrap">{'· '}{item.text}</Text>;
    case 'result':
      return <ResultPanel text={item.text} />;
    case 'error':
      return <Text bold color={COLOR.error} wrap="wrap">{'! Error  '}{item.text}</Text>;
    default:
      return <Text> </Text>;
  }
}

export function Transcript({items, stream, status, rows, columns}) {
  return (
    <Box flexDirection="column" height={getTranscriptRows(rows)} width={columns}
      overflow="hidden" paddingX={2} paddingTop={1}>
      {items.slice(-60).map((item) => (
        <Message key={item.key} item={item} columns={Math.max(columns - 4, 20)} />
      ))}
      {stream && (
        <Message item={{kind: 'assistant', text: `${stream}▌`}}
          columns={Math.max(columns - 4, 20)} />
      )}
      {status && <ToolActivity text={status} busy />}
    </Box>
  );
}

export function Composer({input, setInput, submit, mode, busy, columns}) {
  const placeholder = busy
    ? 'Agent is working...'
    : 'Ask the agent to inspect, build, or explain...';
  return (
    <Box width={columns} height={4} paddingX={1} paddingY={1}
      borderStyle="single" borderColor={COLOR.amber}>
      <Box flexGrow={1} marginRight={1}>
        <TextInput value={input} onChange={setInput} onSubmit={submit}
          placeholder={placeholder} />
      </Box>
      <Text color={COLOR.muted}>{MODE_LABEL[mode]}  </Text>
      <Text bold color={COLOR.amber}>↗</Text>
    </Box>
  );
}
```

- [ ] **Step 4: Run the source-contract tests**

Run the same Python command. Expected: component and copy assertions pass; App integration assertions remain red until Task 3.

- [ ] **Step 5: Commit the component layer**

```powershell
git add tests/test_ui_layout.py ui/workbench.jsx
git commit -m "feat: add Ink workbench components"
```

### Task 3: Controller Integration Without Behavior Changes

**Files:**
- Modify: `ui/index.jsx`

- [ ] **Step 1: Import the new shell**

Replace Ink presentation imports and remove the old `Header`, `Message`, `Transcript`, and `Composer` definitions:

```jsx
import React, {useEffect, useRef, useState} from 'react';
import {Box, render} from 'ink';
import {isWideLayout, getWorkspaceColumns} from './layout.mjs';
import {
  Sidebar,
  WorkspaceHeader,
  Transcript,
  Composer,
} from './workbench.jsx';
```

Keep `createBridge`, `useTerminalSize`, all state, every event case, and the entire `submit` function unchanged.

- [ ] **Step 2: Compose the responsive root**

Replace only the returned presentation tree:

```jsx
const wide = isWideLayout(columns);
const workspaceColumns = getWorkspaceColumns(columns);

return (
  <Box width={columns} height={rows}>
    {wide && <Sidebar items={items} rows={rows} />}
    <Box width={workspaceColumns} height={rows} flexDirection="column">
      <WorkspaceHeader mode={mode} busy={busy} compact={!wide} />
      <Transcript
        items={items}
        stream={stream}
        status={status}
        rows={rows}
        columns={workspaceColumns}
      />
      <Composer
        input={input}
        setInput={setInput}
        submit={submit}
        mode={mode}
        busy={busy}
        columns={workspaceColumns}
      />
    </Box>
  </Box>
);
```

- [ ] **Step 3: Run UI behavior and source-contract tests**

Run:

```powershell
npm.cmd --prefix ui test
& 'C:\Users\21776\AppData\Local\Programs\Python\Python314\python.exe' tests\test_ui_layout.py
```

Expected: all Node layout tests and all Python UI contract tests pass.

- [ ] **Step 4: Build the bundled Ink application**

Run:

```powershell
npm.cmd --prefix ui run build
```

Expected: esbuild exits 0 and writes `ui/.build/index.mjs`.

- [ ] **Step 5: Commit controller integration**

```powershell
git add ui/index.jsx
git commit -m "feat: render responsive Ink workbench"
```

### Task 4: Full Regression and Visual Verification

**Files:**
- Verify only; modify earlier files only if a test exposes a defect.

- [ ] **Step 1: Run the full Python suite**

```powershell
& 'C:\Users\21776\AppData\Local\Programs\Python\Python314\python.exe' -m unittest discover -s tests
```

Expected: all tests pass with zero failures and zero errors.

- [ ] **Step 2: Run the complete UI verification**

```powershell
npm.cmd --prefix ui test
npm.cmd --prefix ui run build
```

Expected: Node tests pass and esbuild exits 0 without warnings.

- [ ] **Step 3: Perform bounded terminal smoke checks**

Launch `npm.cmd --prefix ui start` in a real TTY at approximately 140×40, verify the sidebar/workspace ratio and all semantic regions, then resize to approximately 80×24 and verify the sidebar disappears while Composer remains visible. Exit with `/exit`.

- [ ] **Step 4: Inspect the final diff**

```powershell
git diff HEAD~3 -- ui tests/test_ui_layout.py
git status --short
```

Expected: only the planned Ink UI, tests, and package script files changed; runtime build output remains ignored.

- [ ] **Step 5: Complete the branch**

Use `superpowers:verification-before-completion`, then `superpowers:requesting-code-review`, then `superpowers:finishing-a-development-branch`. Do not claim completion until fresh tests and build evidence are available.
