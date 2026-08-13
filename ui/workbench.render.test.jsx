import React from 'react';
import test from 'node:test';
import assert from 'node:assert/strict';
import {Box, renderToString} from 'ink';
import {isWideLayout} from './layout.mjs';
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

function Preview({columns}) {
  const wide = isWideLayout(columns);

  return (
    <Box width="100%" height="100%" flexDirection="row">
      {wide && <Sidebar items={ITEMS} />}
      <Box flexGrow={1} minWidth={0} flexDirection="column">
        <WorkspaceHeader label="Task" busy={false} compact={!wide} model="deepseek-chat" />
        <Transcript items={ITEMS} stream="" status="" />
        <Composer
          input=""
          setInput={() => {}}
          submit={() => {}}
          label="Task"
          busy={false}
        />
      </Box>
    </Box>
  );
}

test('wide render contains the approved workbench regions', () => {
  const frame = renderToString(<Preview columns={140} />, {columns: 140, rows: 40});

  assert.match(frame, /VibeChatbot/);
  assert.match(frame, /Recent threads/);
  assert.match(frame, /Context: VibeChatbot/);
  assert.match(frame, /You/);
  assert.match(frame, /Agent/);
  assert.match(frame, /Tool/);
  assert.match(frame, /Result/);
  assert.match(frame, /Agent ready · deepseek-chat/);
  assert.match(frame, /Ask the agent to inspect, build, or explain/);
  assert.ok(frame.split('\n').length <= 40);
});

test('compact render hides the sidebar but keeps project context', () => {
  const frame = renderToString(<Preview columns={80} />, {columns: 80, rows: 24});

  assert.doesNotMatch(frame, /Recent threads/);
  assert.match(frame, /VibeChatbot · Task/);
  assert.match(frame, /Agent ready/);
  assert.match(frame, /Ask the agent to inspect, build, or explain/);
  assert.ok(frame.split('\n').length <= 24);
});
