import React from 'react';
import test from 'node:test';
import assert from 'node:assert/strict';
import {Box, renderToString} from 'ink';
import {getWorkspaceColumns, isWideLayout} from './layout.mjs';
import {
  Composer,
  Sidebar,
  Transcript,
  WorkspaceHeader,
} from './workbench.jsx';

const ITEMS = [
  {key: 1, kind: 'user', text: 'Add streaming support to the chat endpoint.'},
  {key: 2, kind: 'assistant', text: 'I will inspect the endpoint and update it.'},
  {key: 3, kind: 'log', text: 'Inspecting src/vibechatbot/chat.py'},
  {key: 4, kind: 'result', text: 'Streaming path verified.'},
];

function Preview({columns, rows}) {
  const wide = isWideLayout(columns);
  const workspaceColumns = getWorkspaceColumns(columns);

  return (
    <Box width={columns} height={rows}>
      {wide && <Sidebar items={ITEMS} rows={rows} />}
      <Box width={workspaceColumns} height={rows} flexDirection="column">
        <WorkspaceHeader mode="idle" busy={false} compact={!wide} />
        <Transcript
          items={ITEMS}
          stream=""
          status=""
          rows={rows}
          columns={workspaceColumns}
        />
        <Composer
          input=""
          setInput={() => {}}
          submit={() => {}}
          mode="idle"
          busy={false}
          columns={workspaceColumns}
        />
      </Box>
    </Box>
  );
}

test('wide render contains the approved workbench regions', () => {
  const frame = renderToString(<Preview columns={140} rows={40} />, {columns: 140});

  assert.match(frame, /VibeChatbot/);
  assert.match(frame, /Recent threads/);
  assert.match(frame, /Context: VibeChatbot/);
  assert.match(frame, /You/);
  assert.match(frame, /Agent/);
  assert.match(frame, /Tool/);
  assert.match(frame, /Result/);
  assert.match(frame, /Ask the agent to inspect, build, or explain/);
  assert.ok(frame.split('\n').length <= 40);
});

test('compact render hides the sidebar but keeps project context', () => {
  const frame = renderToString(<Preview columns={80} rows={24} />, {columns: 80});

  assert.doesNotMatch(frame, /Recent threads/);
  assert.match(frame, /VibeChatbot · Auto/);
  assert.match(frame, /Agent ready/);
  assert.match(frame, /Ask the agent to inspect, build, or explain/);
  assert.ok(frame.split('\n').length <= 24);
});
