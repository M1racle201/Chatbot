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

test('derives one session title from the first user message only', () => {
  const items = [
    {kind: 'assistant', text: '忽略'},
    {kind: 'user', text: '  请帮我  读取一下  a.txt\n并总结内容。  '},
    {kind: 'assistant', text: '忽略'},
    {kind: 'user', text: '第二个问题，不应出现在标题中'},
  ];

  assert.deepEqual(layout.deriveRecentThreads?.(items), [
    '读取 a.txt 并总结内容',
  ]);
});

test('prefers the first rewriter output as the formal title', () => {
  const items = [
    {kind: 'user', text: '帮我看看这个项目到底是怎么回事'},
    {kind: 'step', stage: 'rewriter', text: '复写后任务: 分析项目结构'},
    {kind: 'step', stage: 'rewriter', text: '复写后任务: 第二次复写不应覆盖标题'},
  ];

  assert.deepEqual(layout.deriveRecentThreads?.(items), ['分析项目结构']);
});

test('formalizes and simplifies colloquial titles', () => {
  const items = [
    {kind: 'user', text: '帮我看看这个项目吧'},
  ];

  assert.deepEqual(layout.deriveRecentThreads?.(items), ['查看这个项目']);
});

test('keeps title within the sidebar width', () => {
  const items = [
    {
      kind: 'user',
      text: '这是一段特别长的用户输入内容，用来验证右侧标题会被自动截断而不是把侧栏撑坏',
    },
  ];

  const [title] = layout.deriveRecentThreads?.(items) || [];
  assert.ok(title.endsWith('…'));
  assert.ok([...title].length <= 12);
});
