import React, {useEffect, useRef, useState} from 'react';
import {Box, render} from 'ink';
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import readline from 'node:readline';
import path from 'node:path';
import {isWideLayout} from './layout.mjs';
import {
  Composer,
  Sidebar,
  Transcript,
  WorkspaceHeader,
} from './workbench.jsx';

// bundle ????? .build/??????????? bridge.py
const entryDir = path.dirname(process.argv[1] || process.cwd());
const bridgePath =
  [
    path.join(process.cwd(), 'bridge.py'),
    path.join(entryDir, 'bridge.py'),
    path.join(entryDir, '..', 'bridge.py'),
  ].find(existsSync) ?? path.join(process.cwd(), 'bridge.py');
const pythonCmd = process.env.VIBECHAT_PYTHON || 'python';


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

const App = () => {
  const [input, setInput] = useState('');
  const [items, setItems] = useState([]); // {key, kind, text}
  const [stream, setStream] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState('');
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
            setStream((s) => {
              if (s.trim()) pushItem('assistant', s);
              return '';
            });
            // 流式已展示完整结论时不再重复 Result 面板；无流式任务用面板兜底
            if (!event.streamed) pushItem('result', event.content);
            if (event.verdict) {
              const {reason, exhausted} = event.verdict;
              if (exhausted) pushItem('notice', '核查未通过已达上限，以上为强制输出');
              if (!event.verdict.passed && reason)
                pushItem('log', `核查: ${reason}`);
            }
            const attempts = event.attempts || {};
            const hasRetries = (attempts.rewrite || 0) + (attempts.research || 0) > 0;
            if (hasRetries) {
              pushItem(
                'log',
                `打回统计: 复写 ${attempts.rewrite} 次，重搜 ${attempts.research} 次`
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
            pushItem('notice', '后端已就绪，输入任务即可执行');
            setModel(event.model || '');
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
      pushItem('notice', '可用命令: /clear_history /clear_memory /exit');
      return;
    }
    setBusy(true);
    setStream('');
    bridgeRef.current?.send({type: 'task', content: trimmed});
  };

  const {columns} = useTerminalSize();
  const wide = isWideLayout(columns);

  return (
    <Box width="100%" height="100%" flexDirection="row">
      {wide && <Sidebar items={items} />}
      <Box flexGrow={1} minWidth={0} flexDirection="column">
<WorkspaceHeader label="Task" busy={busy} compact={!wide} model={model} />
        <Transcript items={items} stream={stream} status={status} />
        <Composer
          input={input}
          setInput={setInput}
          submit={submit}
          label="Task"
          busy={busy}
        />
      </Box>
    </Box>
  );
};

render(<App />);

export default App;
