import React from 'react';
import test from 'node:test';
import assert from 'node:assert/strict';
import {Box, renderToString} from 'ink';
import {isWideLayout} from './layout.mjs';
import {
  Composer,
  SettingsPanel,
  Sidebar,
  ToolHistory,
  Transcript,
  WorkspaceHeader,
  parseSgrMouseSequence,
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

test('parses SGR mouse wheel sequences', () => {
  assert.deepEqual(parseSgrMouseSequence('\x1b[<64;40;12M'), {
    button: 64,
    x: 40,
    y: 12,
    action: 'M',
  });
  assert.deepEqual(parseSgrMouseSequence('\x1b[<65;40;12m'), {
    button: 65,
    x: 40,
    y: 12,
    action: 'm',
  });
  assert.equal(parseSgrMouseSequence('\x1b[A'), null);
});

test('sidebar shows one title derived from the first user message', () => {
  const items = [
    {key: 1, kind: 'user', text: '请帮我查看项目结构'},
    {key: 2, kind: 'assistant', text: '正在分析...'},
    {key: 3, kind: 'user', text: '第二个任务'},
  ];
  const frame = renderToString(<Sidebar items={items} />, {
    columns: 120,
    rows: 24,
  });

  assert.match(frame, /查看项目结构/);
  assert.doesNotMatch(frame, /第二个任务/);
});

test('step items render chain-of-thought entries', () => {
  const steps = [
    {key: 1, kind: 'step', stage: 'rewriter', text: '复写后任务: 检查文件'},
    {key: 2, kind: 'step', stage: 'tool', text: 'load(x.pdf)'},
    {key: 3, kind: 'step', stage: 'tool_result', text: '{"content": "..."}'},
    {key: 4, kind: 'step', stage: 'verify_reject', text: '核查打回(复写打回): 缺少依据'},
    {key: 5, kind: 'step', stage: 'retry', text: '第 1 轮重试'},
    {key: 6, kind: 'step', stage: 'verify_pass', text: '核查通过'},
    {key: 7, kind: 'step', stage: 'fast', text: '快速通道：直接执行工具任务'},
  ];
  const frame = renderToString(
    <Transcript items={steps} stream="" status="" />,
    {columns: 120, rows: 30}
  );

  assert.match(frame, /思考 · 任务复写/);
  assert.match(frame, /复写后任务/);
  assert.match(frame, /Tool call · load/);
  assert.match(frame, /x\.pdf/);
  assert.match(frame, /Tool result/);
  assert.match(frame, /核查打回/);
  assert.match(frame, /第 1 轮重试/);
  assert.match(frame, /核查通过/);
  assert.match(frame, /快速通道/);
});

test('long tool results do not overlap following steps', () => {
  const longBody = `这是一段很长的工具返回内容，用来验证换行后不会覆盖后续步骤。${'A'.repeat(300)}`;
  const items = [
    {key: 1, kind: 'step', stage: 'tool', text: 'load(first.txt)', tool: 'load'},
    {key: 2, kind: 'step', stage: 'tool_result', text: longBody, tool: 'load'},
    {key: 3, kind: 'step', stage: 'tool', text: 'load(second.txt)', tool: 'load'},
    {key: 4, kind: 'assistant', text: '最终回复已生成'},
  ];
  const frame = renderToString(
    <Transcript items={items} stream="" status="" columns={80} />,
    {columns: 80, rows: 12}
  );

  // 最新内容应留在可视区域底部，而不是只显示最旧的工具结果。
  assert.match(frame, /Tool call · load/);
  assert.match(frame, /最终回复已生成/);
  const lines = frame.split('\n');
  for (const line of lines) {
    assert.ok(
      !(line.includes('Tool call') && line.includes('AAAA')),
      `工具步骤与长文本发生重叠: ${line}`
    );
    assert.ok(
      !(line.includes('Tool result') && line.includes('AAAA')),
      `工具结果与长文本发生重叠: ${line}`
    );
  }
});

test('transcript viewport pins to the latest messages', () => {
  const items = Array.from({length: 30}, (_, index) => ({
    key: index,
    kind: 'assistant',
    text: `历史消息 ${index}`,
  }));
  const frame = renderToString(
    <Box flexDirection="column" height={12}>
      <Transcript items={items} stream="" status="" columns={80} />
    </Box>,
    {columns: 80, rows: 12}
  );

  assert.match(frame, /历史消息 29/);
  assert.doesNotMatch(frame, /历史消息 0/);
});

test('tool calls collapse into one summary after final output', () => {
  const items = [
    {key: 1, kind: 'user', text: '读取文件并总结'},
    {key: 2, kind: 'step', stage: 'tool', text: 'load(first.txt)', tool: 'load'},
    {key: 3, kind: 'step', stage: 'tool_result', text: '文件内容', tool: 'load'},
    {key: 4, kind: 'assistant', text: '总结完成'},
  ];
  const frame = renderToString(
    <Box flexDirection="column" height={12}>
      <Transcript items={items} stream="" status="" columns={80} />
    </Box>,
    {columns: 80, rows: 12}
  );

  assert.match(frame, /工具调用 2 条/);
  assert.match(frame, /点击展开/);
  assert.doesNotMatch(frame, /load\(first\.txt\)/);
});

test('new round keeps previous round tools collapsed', () => {
  const items = [
    {key: 1, kind: 'user', text: '任务1'},
    {key: 2, kind: 'step', stage: 'tool', text: 'load(a.txt)', tool: 'load'},
    {key: 3, kind: 'step', stage: 'tool_result', text: 'A内容', tool: 'load'},
    {key: 4, kind: 'assistant', text: '任务1完成'},
    {key: 5, kind: 'user', text: '任务2'},
    {key: 6, kind: 'step', stage: 'tool', text: 'load(b.txt)', tool: 'load'},
    {key: 7, kind: 'step', stage: 'tool_result', text: 'B内容', tool: 'load'},
  ];
  const frame = renderToString(
    <Box flexDirection="column" height={24}>
      <Transcript items={items} stream="" status="" columns={80} />
    </Box>,
    {columns: 80, rows: 24}
  );

  assert.match(frame, /工具调用 2 条/);
  // 第二轮正在执行，当前任务工具应展开；上一轮工具应保持折叠。
  assert.match(frame, /b\.txt/);
  assert.doesNotMatch(frame, /a\.txt/);
});

test('expanded tool history shows the original tool calls', () => {
  const items = [
    {key: 1, kind: 'step', stage: 'tool', text: 'load(first.txt)', tool: 'load'},
    {key: 2, kind: 'step', stage: 'tool_result', text: '文件内容', tool: 'load'},
  ];
  const frame = renderToString(
    <Box flexDirection="column" height={12}>
      <ToolHistory items={items} collapsed={false} contentWidth={68} />
    </Box>,
    {columns: 80, rows: 12}
  );

  assert.match(frame, /工具调用 2 条/);
  assert.match(frame, /Tool call · load/);
  assert.match(frame, /first\.txt/);
  assert.match(frame, /文件内容/);
});

test('composer collapses oversized pasted text into a line/row summary', () => {
  const hugeInput = '这是一段用来测试大量粘贴内容的文字。'.repeat(80);
  const frame = renderToString(
    <Composer
      input={hugeInput}
      setInput={() => {}}
      submit={() => {}}
      label="Task"
      busy={false}
      columns={80}
      maxHeight={5}
    />,
    {columns: 80, rows: 12}
  );

  assert.match(frame, /\[\d+ lines \* \d+ rows\]/);
  assert.match(frame, /内容过多，已折叠显示/);
  assert.doesNotMatch(frame, /大量粘贴内容的文字。这是一段/);
  assert.ok(frame.split('\n').length <= 5);
});

test('composer grows vertically when input wraps to multiple lines', () => {
  const longInput =
    '这是一段很长的输入内容，用来验证输入框在终端宽度不足时会自动换行，而不是超出边框。';
  const frame = renderToString(
    <Composer
      input={longInput}
      setInput={() => {}}
      submit={() => {}}
      label="Task"
      busy={false}
      columns={80}
      maxHeight={10}
    />,
    {columns: 80, rows: 12}
  );

  const lines = frame.split('\n');
  assert.ok(lines.length >= 4);
  assert.ok(lines.length <= 10);
  assert.match(frame, /很长/);
  assert.match(frame, /边框/);
});

test('settings panel renders URL, API key, and model fields', () => {
  const frame = renderToString(
    <SettingsPanel
      initial={{base_url: 'https://example.com/v1', api_key: '', model: 'model-x'}}
      onSave={() => {}}
      onCancel={() => {}}
      error=""
    />,
    {columns: 80, rows: 20},
  );

  assert.match(frame, /API Settings/);
  assert.match(frame, /API URL/);
  assert.match(frame, /API Key/);
  assert.match(frame, /Model/);
  assert.match(frame, /保存/);
  assert.match(frame, /取消/);
});
