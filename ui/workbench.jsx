import React, {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {Box, Text, measureElement, useInput, useStdin, useStdout} from 'ink';
import TextInput from 'ink-text-input';
import stringWidth from 'string-width';
import wrapAnsi from 'wrap-ansi';
import {SIDEBAR_WIDTH, deriveRecentThreads, isWideLayout} from './layout.mjs';

const COLOR = {
  amber: '#62a2f5',
  cyan: '#58D1C2',
  surface: '#191F27',
  border: '#30363D',
  text: '#F2F2ED',
  muted: '#9CA3AD',
  success: '#89f2b1',
  error: '#F47067',
};

const STEP_META = {
  rewriter: {icon: '⟳', label: '思考 · 任务复写', color: COLOR.amber},
  tool: {icon: '⚒', label: '工具调用', color: COLOR.cyan},
  tool_result: {icon: '↳', label: '工具结果', color: COLOR.muted},
  verify_pass: {icon: '✔', label: '核查通过', color: COLOR.success},
  verify_reject: {icon: '✗', label: '核查打回', color: COLOR.error},
  retry: {icon: '↻', label: '重试', color: COLOR.amber},
  fast: {icon: '⚡', label: '快速通道', color: COLOR.cyan},
};

function parseToolCall(text) {
  const value = String(text || '').trim();
  const match = value.match(/^([A-Za-z_][A-Za-z0-9_.-]*)\s*\(([\s\S]*)\)$/);
  if (match) {
    return {name: match[1], args: match[2].trim()};
  }
  const open = value.indexOf('(');
  if (open > 0) {
    return {
      name: value.slice(0, open).trim(),
      args: value.slice(open + 1).replace(/\)$/, '').trim(),
    };
  }
  return {name: '', args: value};
}

function formatToolArguments(args) {
  try {
    return JSON.stringify(JSON.parse(args), null, 2);
  } catch {
    return args;
  }
}

function wrappedLineCount(text, maxWidth) {
  const value = String(text || ' ');
  return Math.max(
    1,
    wrapAnsi(value, Math.max(1, maxWidth), {
      trim: false,
      hard: true,
    }).split('\n').length
  );
}


export function Sidebar({items}) {
  const recent = deriveRecentThreads(items);
  const threads = recent.length ? recent : ['No recent threads'];

  return (
    <Box
      width={SIDEBAR_WIDTH}
      flexShrink={0}
      flexDirection="column"
      paddingX={1}
      borderStyle="single"
      borderTop={false}
      borderBottom={false}
      borderLeft={false}
      borderColor={COLOR.border}
    >
      <Box height={3} alignItems="center">
        <Text bold color={COLOR.amber}>JobMatchAgent⌄</Text>
      </Box>

      <Box flexDirection="column" marginTop={1} gap={1}>
        <Text bold color={COLOR.amber} backgroundColor={COLOR.surface}>
          {'  ◇  Threads            '}
        </Text>
        <Text color={COLOR.muted}>{'  ▣  Files'}</Text>
        <Text color={COLOR.muted}>{'  □  Tasks'}</Text>
      </Box>

      <Box flexDirection="column" marginTop={2} gap={1}>
        <Text color={COLOR.muted}>Recent threads</Text>
        {threads.map((thread, index) => (
          <Text
            key={`${thread}-${index}`}
            color={index === 0 && recent.length ? COLOR.amber : COLOR.text}
            dimColor={!recent.length}
            wrap="truncate-end"
          >
            {thread}
          </Text>
        ))}
      </Box>

      <Box flexGrow={1} />
      <Box marginBottom={1}>
        <Text color={COLOR.muted}>⚙  Settings</Text>
      </Box>
    </Box>
  );
}

export function WorkspaceHeader({label = 'Task', busy, compact, model = ''}) {
  const context = compact
    ? `JobMatchAgent · ${label}`
    : `Context: JobMatchAgent · ${label}`;

  return (
    <Box
      height={3}
      flexShrink={0}
      paddingX={2}
      alignItems="center"
      justifyContent="space-between"
      borderStyle="single"
      borderTop={false}
      borderLeft={false}
      borderRight={false}
      borderColor={COLOR.border}
    >
      <Text>
        <Text color={busy ? COLOR.amber : COLOR.cyan}>●</Text>
        {`  ${busy ? 'Agent working' : 'Agent ready'}`}
        {model ? <Text color={COLOR.muted}>{` · ${model}`}</Text> : null}
      </Text>
      <Text color={COLOR.muted}>{context}</Text>
    </Box>
  );
}

export function ToolActivity({text, busy = false, contentWidth = 68}) {
  const prefixWidth = stringWidth(busy ? '○' : '✓') + stringWidth('  Tool  ');
  const textWidth = Math.max(12, contentWidth - 2 - prefixWidth);
  const lineCount = wrappedLineCount(text, textWidth);

  return (
    <Box
      paddingX={1}
      marginBottom={1}
      width="100%"
      height={lineCount}
      flexShrink={0}
      backgroundColor={COLOR.surface}
    >
      <Text color={busy ? COLOR.amber : COLOR.success}>
        {busy ? '○' : '✓'}
      </Text>
      <Text bold>{'  Tool  '}</Text>
      <Text color={COLOR.muted} wrap="wrap">{text}</Text>
    </Box>
  );
}

function ToolCallStep({item, contentWidth = 68}) {
  const {name, args} = parseToolCall(item.text);
  const body = formatToolArguments(args);
  const bodyWidth = Math.max(12, contentWidth - 4);
  const height = 1 + 1 + wrappedLineCount(body || ' ', bodyWidth);

  return (
    <Box
      flexDirection="column"
      marginBottom={1}
      width="100%"
      height={height}
      flexShrink={0}
    >
      <Box width="100%" paddingX={1} backgroundColor={COLOR.surface}>
        <Text bold color={COLOR.cyan}>⚒ Tool call</Text>
        {name ? <Text color={COLOR.cyan}>{` · ${name}`}</Text> : null}
      </Box>
      <Box paddingX={2} paddingTop={1}>
        <Text color={COLOR.text} wrap="wrap">
          {body}
        </Text>
      </Box>
    </Box>
  );
}

function ToolResultStep({item, contentWidth = 68}) {
  const body = formatToolArguments(item.text);
  const bodyWidth = Math.max(12, contentWidth - 4);
  const bodyLineCount = wrappedLineCount(body || ' ', bodyWidth);
  const visibleBodyLines = Math.min(2, bodyLineCount);
  const height = 1 + 1 + visibleBodyLines;

  return (
    <Box
      flexDirection="column"
      marginBottom={1}
      width="100%"
      height={height}
      flexShrink={0}
    >
      <Box width="100%" paddingX={1} backgroundColor={COLOR.surface}>
        <Text color={COLOR.muted}>↳ Tool result</Text>
        {item.tool ? <Text color={COLOR.muted}>{` · ${item.tool}`}</Text> : null}
      </Box>
      <Box
        paddingX={2}
        paddingTop={1}
        height={1 + visibleBodyLines}
        overflow="hidden"
      >
        <Text color={COLOR.muted} wrap="wrap">{body}</Text>
      </Box>
    </Box>
  );
}

function ThoughtStep({item, contentWidth = 68}) {
  const meta = STEP_META[item.stage] || {
    icon: '·',
    label: '思考',
    color: COLOR.muted,
  };
  const body = item.text === meta.label ? '' : item.text;
  const bodyWidth = Math.max(12, contentWidth - 3);
  const bodyLines = body ? wrappedLineCount(body, bodyWidth) : 0;
  const height = 1 + (body ? 1 + bodyLines : 0);

  return (
    <Box
      flexDirection="column"
      marginBottom={1}
      paddingLeft={1}
      width="100%"
      height={height}
      flexShrink={0}
    >
      <Box>
        <Text color={meta.color}>{meta.icon}</Text>
        <Text bold color={meta.color}>{`  ${meta.label}`}</Text>
      </Box>
      {body ? (
        <Box paddingLeft={2} paddingTop={1}>
          <Text
            color={item.stage === 'verify_reject' ? COLOR.error : COLOR.text}
            wrap="wrap"
          >
            {body}
          </Text>
        </Box>
      ) : null}
    </Box>
  );
}

export function ResultPanel({text, contentWidth = 68}) {
  const bodyWidth = Math.max(12, contentWidth - 2);
  const height = 1 + 1 + wrappedLineCount(text || ' ', bodyWidth);

  return (
    <Box
      flexDirection="column"
      marginBottom={1}
      width="100%"
      height={height}
      flexShrink={0}
    >
      <Box width="100%" paddingX={1} backgroundColor={COLOR.surface}>
        <Text bold>Result</Text>
      </Box>
      <Box paddingX={1} paddingTop={1}>
        <Text color={COLOR.text} wrap="wrap">{text}</Text>
      </Box>
    </Box>
  );
}

function Message({item, contentWidth}) {
  switch (item.kind) {
    case 'user':
      return (
        <Box
          flexDirection="column"
          marginBottom={1}
          width="100%"
          height={1 + wrappedLineCount(item.text, contentWidth)}
          flexShrink={0}
        >
          <Text bold color={COLOR.amber}>You</Text>
          <Text color={COLOR.text} wrap="wrap">
            {item.text}
          </Text>
        </Box>
      );
    case 'assistant':
      return (
        <Box
          flexDirection="column"
          marginBottom={1}
          width="100%"
          height={1 + wrappedLineCount(item.text, contentWidth)}
          flexShrink={0}
        >
          <Text bold color={COLOR.cyan}>Agent</Text>
          <Text color={COLOR.text} wrap="wrap">
            {item.text}
          </Text>
        </Box>
      );
    case 'log':
      return <ToolActivity text={item.text} contentWidth={contentWidth} />;
    case 'step':
      if (item.stage === 'tool') {
        return <ToolCallStep item={item} contentWidth={contentWidth} />;
      }
      if (item.stage === 'tool_result') {
        return <ToolResultStep item={item} contentWidth={contentWidth} />;
      }
      return <ThoughtStep item={item} contentWidth={contentWidth} />;
    case 'notice':
      return (
        <Box
          height={wrappedLineCount(`· ${item.text}`, contentWidth)}
          flexShrink={0}
        >
          <Text color={COLOR.muted} wrap="wrap">
            {'· '}{item.text}
          </Text>
        </Box>
      );
    case 'result':
      return <ResultPanel text={item.text} contentWidth={contentWidth} />;
    case 'error':
      return (
        <Box
          height={wrappedLineCount(`! Error  ${item.text}`, contentWidth)}
          flexShrink={0}
        >
          <Text bold color={COLOR.error} wrap="wrap">
            {'! Error  '}{item.text}
          </Text>
        </Box>
      );
    default:
      return <Text> </Text>;
  }
}

export function parseSgrMouseSequence(input) {
  const match = String(input || '').match(
    /^\x1b\[<(\d+);(\d+);(\d+)([Mm])$/
  );
  if (!match) return null;
  return {
    button: Number(match[1]),
    x: Number(match[2]),
    y: Number(match[3]),
    action: match[4],
  };
}

function useMouseWheel(onWheel, onClick) {
  const {internal_eventEmitter} = useStdin();
  const {stdout} = useStdout();
  const onWheelRef = useRef(onWheel);
  const onClickRef = useRef(onClick);
  onWheelRef.current = onWheel;
  onClickRef.current = onClick;

  useEffect(() => {
    if (!stdout?.isTTY || !internal_eventEmitter) return undefined;
    const emitter = internal_eventEmitter;
    const originalEmit = emitter.emit.bind(emitter);

    emitter.emit = (event, input, key) => {
      if (event === 'input') {
        const mouse = parseSgrMouseSequence(input);
        if (mouse) {
          if (mouse.action === 'M' && mouse.button === 64) {
            onWheelRef.current(-3);
          } else if (mouse.action === 'M' && mouse.button === 65) {
            onWheelRef.current(3);
          } else if (mouse.action === 'M' && mouse.button === 0) {
            onClickRef.current?.();
          }
          // 拦截所有鼠标上报，避免 TextInput 把鼠标序列当成普通字符插入。
          return true;
        }
      }
      return originalEmit(event, input, key);
    };

    stdout.write('\x1b[?1000h\x1b[?1006h');
    return () => {
      emitter.emit = originalEmit;
      stdout.write('\x1b[?1000l\x1b[?1006l');
    };
  }, [internal_eventEmitter, stdout]);
}

function isToolStep(item) {
  return (
    item?.kind === 'step' &&
    (item.stage === 'tool' || item.stage === 'tool_result')
  );
}

export function ToolHistory({
  userKey,
  items,
  collapsed,
  onToggle,
  onRegister,
  contentWidth,
}) {
  const headerRef = useRef(null);

  useLayoutEffect(() => {
    if (!onRegister || !headerRef.current?.yogaNode) return;
    let top = 0;
    let node = headerRef.current;
    while (node?.yogaNode) {
      top += node.yogaNode.getComputedTop() || 0;
      node = node.parentNode;
    }
    const height = headerRef.current.yogaNode.getComputedHeight() || 0;
    onRegister(userKey, top, height);
  }, [onRegister, userKey, collapsed, items.length]);

  return (
    <Box flexDirection="column" marginBottom={1} width="100%" flexShrink={0}>
      <Box
        ref={headerRef}
        width="100%"
        paddingX={1}
        backgroundColor={COLOR.surface}
        flexShrink={0}
      >
        <Text bold color={COLOR.cyan}>⚒ 工具调用 {items.length} 条</Text>
        <Text color={COLOR.muted}>
          {collapsed ? ' · 点击展开' : ' · 点击收起'}
        </Text>
      </Box>
      {!collapsed
        ? items.map((item) => (
            <Message key={item.key} item={item} contentWidth={contentWidth} />
          ))
        : null}
    </Box>
  );
}

export function Transcript({items, stream, status, columns = 80, wide}) {
  const hasSidebar = wide === undefined ? isWideLayout(columns) : wide;
  const contentWidth = Math.max(
    12,
    columns - (hasSidebar ? SIDEBAR_WIDTH : 0) - 4
  );
  const viewportRef = useRef(null);
  const contentRef = useRef(null);
  const [viewportHeight, setViewportHeight] = useState(0);
  const [contentHeight, setContentHeight] = useState(0);
  const [scrollOffset, setScrollOffset] = useState(0);
  const [pinnedToBottom, setPinnedToBottom] = useState(true);
  const [expandedToolUsers, setExpandedToolUsers] = useState(() => new Set());
  const toolBarRangesRef = useRef([]);
  toolBarRangesRef.current = [];

  const maxScrollOffset = Math.max(0, contentHeight - viewportHeight);

  useLayoutEffect(() => {
    const nextViewportHeight = measureElement(viewportRef.current).height || 0;
    const nextContentHeight = measureElement(contentRef.current).height || 0;
    setViewportHeight(nextViewportHeight);
    setContentHeight(nextContentHeight);
  }, [items, stream, status, columns, wide]);

  useLayoutEffect(() => {
    if (pinnedToBottom) {
      setScrollOffset(maxScrollOffset);
    }
  }, [maxScrollOffset, pinnedToBottom]);

  useEffect(() => {
    if (scrollOffset >= maxScrollOffset) {
      setPinnedToBottom(true);
    }
  }, [scrollOffset, maxScrollOffset]);

  // 提交新任务后自动回到最底部，避免停留在历史滚动位置看不到新回复。
  useEffect(() => {
    if (items[items.length - 1]?.kind === 'user') {
      setPinnedToBottom(true);
    }
  }, [items]);

  // 每个任务独立控制展开/收起：
  // - 新任务开始后全部收起
  // - 当前任务出现工具调用时展开当前任务
  // - 当前任务输出最终结果后收起当前任务
  useLayoutEffect(() => {
    const last = items[items.length - 1];
    if (!last) return;
    const findLastUserKey = (list) => {
      for (let index = list.length - 1; index >= 0; index--) {
        if (list[index].kind === 'user') return list[index].key;
      }
      return null;
    };
    if (isToolStep(last)) {
      const userKey = findLastUserKey(items);
      if (userKey != null) {
        setExpandedToolUsers((current) => {
          const next = new Set(current);
          next.add(userKey);
          return next;
        });
      }
    } else if (last.kind === 'user') {
      setExpandedToolUsers(new Set());
    } else if (last.kind === 'assistant' || last.kind === 'result') {
      const userKey = findLastUserKey(items.slice(0, -1));
      if (userKey != null) {
        setExpandedToolUsers((current) => {
          const next = new Set(current);
          next.delete(userKey);
          return next;
        });
      }
    }
  }, [items]);

  const scrollBy = (delta) => {
    if (delta < 0) setPinnedToBottom(false);
    setScrollOffset((current) =>
      Math.max(0, Math.min(maxScrollOffset, current + delta))
    );
  };

  const toggleToolHistory = (userKey) => {
    setExpandedToolUsers((current) => {
      const next = new Set(current);
      if (next.has(userKey)) {
        next.delete(userKey);
      } else {
        next.add(userKey);
      }
      return next;
    });
  };

  const registerToolBar = (userKey, top, height) => {
    toolBarRangesRef.current.push({userKey, top, height});
  };

  useMouseWheel(scrollBy, (clickY) => {
    const contentY = clickY + scrollOffset;
    const hit = toolBarRangesRef.current.find(
      (range) => contentY >= range.top && contentY < range.top + range.height
    );
    if (hit) {
      toggleToolHistory(hit.userKey);
    }
  });

  useInput((_input, key) => {
    const pageSize = Math.max(1, viewportHeight - 2);
    if (key.upArrow) {
      scrollBy(-1);
    } else if (key.downArrow) {
      scrollBy(1);
    } else if (key.pageUp) {
      scrollBy(-pageSize);
    } else if (key.pageDown) {
      scrollBy(pageSize);
    }
  });

  return (
    <Box
      ref={viewportRef}
      flexDirection="column"
      flexGrow={1}
      flexShrink={1}
      overflow="hidden"
      paddingX={2}
      paddingTop={1}
    >
      <Box
        ref={contentRef}
        flexDirection="column"
        flexShrink={0}
        marginTop={-scrollOffset}
      >
        {(() => {
          const visibleItems = items.slice(-60);
          const visibleStart = items.length - visibleItems.length;
          const groups = [];
          let currentGroup = null;
          visibleItems.forEach((item, index) => {
            if (item.kind === 'user') {
              currentGroup = {userKey: item.key, index, tools: []};
              groups.push(currentGroup);
            } else if (currentGroup && isToolStep(item)) {
              currentGroup.tools.push(item);
            }
          });
          const groupedToolKeys = new Set(
            groups.flatMap((group) => group.tools.map((tool) => tool.key))
          );
          const rendered = [];
          visibleItems.forEach((item, index) => {
            const group = groups.find((entry) => entry.index === index);
            if (group) {
              rendered.push(
                <Message
                  key={item.key}
                  item={item}
                  contentWidth={contentWidth}
                />
              );
              if (group.tools.length > 0) {
                rendered.push(
                  <ToolHistory
                    key={`tool-history-${visibleStart + index}`}
                    userKey={group.userKey}
                    items={group.tools}
                    collapsed={!expandedToolUsers.has(group.userKey)}
                    onToggle={() => toggleToolHistory(group.userKey)}
                    onRegister={registerToolBar}
                    contentWidth={contentWidth}
                  />
                );
              }
            } else if (isToolStep(item) && groupedToolKeys.has(item.key)) {
              // 已收进对应 ToolHistory，不再重复渲染。
            } else {
              rendered.push(
                <Message
                  key={item.key}
                  item={item}
                  contentWidth={contentWidth}
                />
              );
            }
          });
          return rendered;
        })()}
        {stream && (
          <Message
            item={{kind: 'assistant', text: `${stream}▌`}}
            contentWidth={contentWidth}
          />
        )}
        {status && (
          <ToolActivity text={status} busy contentWidth={contentWidth} />
        )}
      </Box>
    </Box>
  );
}

export function Composer({
  input,
  setInput,
  submit,
  label = 'Task',
  busy,
  columns = 80,
  maxHeight = 21,
}) {
  const placeholder = busy
    ? 'Agent is working...'
    : 'Ask the agent to inspect, build, or explain...';

  // 输入框可用宽度：去掉侧栏、边框、内边距、右侧 label 和提交箭头。
  const compact = !isWideLayout(columns);
  const outerWidth = Math.max(24, columns - (compact ? 0 : SIDEBAR_WIDTH));
  const inputWidth = Math.max(12, outerWidth - 8 - stringWidth(label));
  const renderedText = input ? `${input} ` : placeholder;
  const lineCount = wrappedLineCount(renderedText, inputWidth);
  const maxVisibleInputLines = Math.max(1, maxHeight - 2);
  const collapsed = lineCount > maxVisibleInputLines;
  const composerHeight = Math.max(3, Math.min(2 + lineCount, maxHeight));

  return (
    <Box
      width="100%"
      height={composerHeight}
      flexShrink={0}
      paddingX={1}
      borderStyle="single"
      borderColor={COLOR.amber}
      overflow="hidden"
    >
      <Box
        display={collapsed ? 'none' : 'flex'}
        flexGrow={1}
        marginRight={1}
        overflow="hidden"
      >
        <TextInput
          value={input}
          onChange={setInput}
          onSubmit={submit}
          placeholder={placeholder}
        />
      </Box>
      {collapsed ? (
        <Box flexGrow={1} marginRight={1} overflow="hidden">
          <Text color={COLOR.muted} wrap="truncate-end">
            [{lineCount} lines * {maxVisibleInputLines} rows] 内容过多，已折叠显示
          </Text>
        </Box>
      ) : null}
      <Text color={COLOR.muted}>{label}{'  '}</Text>
      <Text bold color={COLOR.amber}>↗</Text>
    </Box>
  );
}

export function SettingsPanel({
  initial = {},
  onSave,
  onCancel,
  error = '',
  busy = false,
  columns = 80,
}) {
  const [baseUrl, setBaseUrl] = useState(initial.base_url || '');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState(initial.model || '');
  const [active, setActive] = useState(0);
  const panelWidth = Math.max(30, Math.min(76, columns - 4));

  useInput((_input, key) => {
    if (busy) return;
    if (key.escape) {
      onCancel();
      return;
    }
    if ((key.shift && key.tab) || key.upArrow) {
      setActive((index) => (index + 2) % 3);
      return;
    }
    if (key.tab || key.downArrow) {
      setActive((index) => (index + 1) % 3);
      return;
    }
    if (key.return && active === 2) {
      onSave({base_url: baseUrl, api_key: apiKey, model});
    } else if (key.return) {
      setActive((index) => index + 1);
    }
  }, {isActive: true});

  const field = (label, value, setValue, placeholder, mask) => (
    <Box flexDirection="column" marginBottom={1}>
      <Text color={COLOR.muted}>{label}</Text>
      <Box
        width={panelWidth}
        paddingX={1}
        borderStyle="single"
        borderColor={COLOR.border}
      >
        <TextInput
          value={value}
          onChange={setValue}
          focus={active === (label === 'API URL' ? 0 : label === 'API Key' ? 1 : 2) && !busy}
          placeholder={placeholder}
          mask={mask}
        />
      </Box>
    </Box>
  );

  return (
    <Box
      width="100%"
      flexDirection="column"
      paddingX={2}
      paddingY={1}
      borderStyle="single"
      borderColor={COLOR.amber}
    >
      <Text bold color={COLOR.amber}>API Settings</Text>
      <Text color={COLOR.muted}>配置保存后立即生效；API Key 不会显示或写入日志。</Text>
      <Box flexDirection="column" marginTop={1}>
        {field('API URL', baseUrl, setBaseUrl, 'https://api.example.com/v1')}
        {field('API Key', apiKey, setApiKey, '留空表示保持当前配置', '*')}
        {field('Model', model, setModel, 'deepseek-chat')}
      </Box>
      {error ? <Text color={COLOR.error}>错误：{error}</Text> : null}
      <Text color={COLOR.muted}>
        {busy ? '正在应用配置...' : 'Tab/↑↓ 切换 · Enter 下一项/保存 · Esc 取消'}
      </Text>
    </Box>
  );
}
