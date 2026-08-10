import React, {useEffect, useRef, useState} from 'react';
import {Box, Text, render} from 'ink';
import TextInput from 'ink-text-input';
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import readline from 'node:readline';
import path from 'node:path';

// bundle ????? .build/??????????? bridge.py
const entryDir = path.dirname(process.argv[1] || process.cwd());
const bridgePath =
  [
    path.join(process.cwd(), 'bridge.py'),
    path.join(entryDir, 'bridge.py'),
    path.join(entryDir, '..', 'bridge.py'),
  ].find(existsSync) ?? path.join(process.cwd(), 'bridge.py');
const pythonCmd = process.env.VIBECHAT_PYTHON || 'python';

const MODE_LABEL = {
  idle: '未选择模式',
  chat: '聊天',
  agent: '任务',
  agentic: '智能任务',
};

const MODE_COLOR = {
  idle: 'gray',
  chat: 'green',
  agent: 'yellow',
  agentic: 'magenta',
};

const MAX_VISIBLE_ITEMS = 60;
const MIN_TRANSCRIPT_ROWS = 8;
const RESERVED_SHELL_ROWS = 7;

function createBridge(onEvent, onClose, onError) {
  const child = spawn(pythonCmd, [bridgePath], {
    stdio: ['pipe', 'pipe', 'inherit'],
  });
  child.on('error', (err) => {
    onError(
      `无法启动 Python 后端（${pythonCmd}）：${err.message}。请安装 Python 或用 VIBECHAT_PYTHON 指定路径`
    );
  });
  const rl = readline.createInterface({input: child.stdout});
  rl.on('line', (line) => {
    try {
      onEvent(JSON.parse(line));
    } catch {
      // 忽略无法解析的行
    }
  });
  child.on('close', onClose);
  return {
    send: (command) => child.stdin.write(JSON.stringify(command) + '\n'),
    close: () => child.stdin.end(),
  };
}

function useTerminalSize() {
  const getSize = () => ({
    columns: process.stdout.columns || 80,
    rows: process.stdout.rows || 24,
  });
  const [size, setSize] = useState(getSize);

  useEffect(() => {
    const update = () => setSize(getSize());
    process.stdout.on?.('resize', update);
    update();
    return () => process.stdout.off?.('resize', update);
  }, []);

  return size;
}

function Header({mode, busy, columns}) {
  return (
    <Box
      width={columns}
      borderStyle="single"
      borderColor="gray"
      paddingX={1}
      justifyContent="space-between"
    >
      <Box>
        <Text bold color="cyan">VibeChatbot</Text>
        <Text dimColor>{'  ·  '}</Text>
        <Text bold color={MODE_COLOR[mode]}>{MODE_LABEL[mode]}</Text>
      </Box>
      <Text color={busy ? 'yellow' : 'green'}>{busy ? '处理中' : '就绪'}</Text>
    </Box>
  );
}

function Message({item, columns}) {
  const textWidth = Math.max(columns - 4, 20);

  switch (item.kind) {
    case 'user':
      return (
        <Box key={item.key} marginBottom={1} width={columns}>
          <Text color="cyan" bold>{'› '}</Text>
          <Text wrap="wrap" width={textWidth}>{item.text}</Text>
        </Box>
      );
    case 'assistant':
      return (
        <Box key={item.key} marginBottom={1} width={columns}>
          <Text color="green" bold>{'AI  '}</Text>
          <Text color="green" wrap="wrap" width={textWidth}>{item.text}</Text>
        </Box>
      );
    case 'log':
      return <Text key={item.key} dimColor wrap="truncate-end">{'  · '}{item.text}</Text>;
    case 'notice':
      return <Text key={item.key} color="blue" wrap="wrap">{'  · '}{item.text}</Text>;
    case 'result':
      return (
        <Box key={item.key} flexDirection="column" marginTop={1} marginBottom={1} paddingLeft={1} width={columns}>
          <Text bold color="white">结果</Text>
          <Text wrap="wrap" width={Math.max(columns - 2, 20)}>{item.text}</Text>
        </Box>
      );
    case 'error':
      return <Text key={item.key} color="red" wrap="wrap">{'错误  '}{item.text}</Text>;
    default:
      return <Text key={item.key}> </Text>;
  }
}

function Transcript({items, stream, status, rows, columns}) {
  const transcriptRows = Math.max(rows - RESERVED_SHELL_ROWS, MIN_TRANSCRIPT_ROWS);

  return (
    <Box flexDirection="column" height={transcriptRows} width={columns} overflow="hidden" marginTop={1}>
      {items.slice(-MAX_VISIBLE_ITEMS).map((item) => (
        <Message key={item.key} item={item} columns={columns} />
      ))}
      {stream && (
        <Message key="stream" item={{key: 'stream', kind: 'assistant', text: `${stream}▌`}} columns={columns} />
      )}
      {status && <Text dimColor wrap="truncate-end">{'  · '}{status}</Text>}
    </Box>
  );
}

function Composer({input, setInput, submit, mode, busy, columns}) {
  const hint = mode === 'idle'
    ? '/chat  /agent  /agentic'
    : busy
      ? '处理中'
      : '/help  /exit';

  return (
    <Box
      width={columns}
      marginTop={1}
      paddingX={1}
      borderStyle="single"
      borderColor={busy ? 'yellow' : 'gray'}
    >
      <Text color="cyan" bold>{'› '}</Text>
      <Box flexGrow={1}>
        <TextInput value={input} onChange={setInput} onSubmit={submit} />
      </Box>
      <Text dimColor>{'  '}{hint}</Text>
    </Box>
  );
}

const App = () => {
  const [mode, setMode] = useState('idle');
  const [input, setInput] = useState('');
  const [items, setItems] = useState([]); // {key, kind, text}
  const [stream, setStream] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const bridgeRef = useRef(null);
  const keyRef = useRef(0);

  const pushItem = (kind, text) => {
    const key = ++keyRef.current;
    setItems((prev) => [...prev, {key, kind, text}]);
  };

  useEffect(() => {
    const bridge = createBridge(
      (event) => {
        switch (event.type) {
          case 'user':
            pushItem('user', event.content);
            break;
          case 'stream':
            setStream((s) => s + event.content);
            break;
          case 'done':
            setStream((s) => {
              if (s.trim()) pushItem('assistant', s);
              return '';
            });
            setBusy(false);
            setStatus('');
            break;
          case 'log':
            pushItem(event.line.trim() ? 'log' : 'spacer', event.line);
            break;
          case 'notice':
            pushItem('notice', event.content);
            break;
          case 'status':
            setStatus(event.text);
            break;
          case 'result': {
            pushItem('result', event.content);
            if (event.verdict) {
              const {reason, exhausted} = event.verdict;
              if (exhausted) pushItem('notice', '核查未通过已达上限，以上为强制输出');
              if (reason) pushItem('log', `核查: ${reason}`);
            }
            if (event.attempts) {
              pushItem(
                'log',
                `打回统计: 复写 ${event.attempts.rewrite} 次，重搜 ${event.attempts.research} 次`
              );
            }
            setBusy(false);
            setStatus('');
            break;
          }
          case 'error':
            pushItem('error', event.message);
            setBusy(false);
            setStatus('');
            setStream('');
            break;
          case 'ready':
            pushItem('notice', '后端已就绪，输入 /chat /agent /agentic 选择模式');
            break;
          default:
            break;
        }
      },
      () => {
        // 子进程退出（正常结束或崩溃）
      },
      (message) => pushItem('error', message)
    );
    pushItem('notice', '正在连接后端...');
    bridgeRef.current = bridge;
    return () => {
      bridge.close();
    };
  }, []);

  const submit = (value) => {
    setInput('');
    const trimmed = value.trim();
    if (!trimmed) return;

    if (trimmed === '/exit') {
      bridgeRef.current?.send({type: 'exit'});
      bridgeRef.current?.close();
      process.exit(0);
      return;
    }
    if (trimmed === '/clear_history') {
      bridgeRef.current?.send({type: 'clear_history'});
      return;
    }
    if (trimmed === '/clear_memory' || trimmed === '/clear_memmory') {
      bridgeRef.current?.send({type: 'clear_memory'});
      return;
    }
    if (trimmed.startsWith('/')) {
      const name = trimmed.slice(1).toLowerCase();
      if (name in MODE_LABEL && name !== 'idle') {
        setMode(name);
        setStream('');
        pushItem('notice', `已进入${MODE_LABEL[name]}模式，输入 /exit 退出`);
        return;
      }
      pushItem('notice', '可用命令: /chat /agent /agentic /clear_history /clear_memory /exit');
      return;
    }
    if (mode === 'idle') {
      pushItem('notice', '先输入 /chat /agent /agentic 选择模式');
      return;
    }
    setBusy(true);
    setStream('');
    bridgeRef.current?.send({type: mode, content: trimmed});
  };

  const {columns, rows} = useTerminalSize();

  return (
    <Box flexDirection="column" width={columns}>
      <Header mode={mode} busy={busy} columns={columns} />
      <Transcript items={items} stream={stream} status={status} rows={rows} columns={columns} />
      <Composer input={input} setInput={setInput} submit={submit} mode={mode} busy={busy} columns={columns} />
    </Box>
  );
};

render(<App />);

export default App;
