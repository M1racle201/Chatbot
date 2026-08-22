import React, {useEffect, useRef, useState} from 'react';
import {Box, render, useStdout} from 'ink';
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import readline from 'node:readline';
import path from 'node:path';
import {isWideLayout} from './layout.mjs';
import {
  Composer,
  Sidebar,
  SettingsPanel,
  Transcript,
  WorkspaceHeader,
} from './workbench.jsx';

// bundle ????? .build/??????????? bridge.py
const entryDir = path.dirname(process.argv[1] || process.cwd());
const exeDir = path.dirname(process.execPath);
const backendExe =
  [
    process.env.VIBECHAT_BRIDGE_EXE,
    path.join(exeDir, 'vibechatbot-backend.exe'),
    path.join(exeDir, 'backend.exe'),
  ].find((candidate) => candidate && existsSync(candidate)) || '';
const bridgePath =
  [
    path.join(process.cwd(), 'bridge.py'),
    path.join(entryDir, 'bridge.py'),
    path.join(entryDir, '..', 'bridge.py'),
  ].find(existsSync) ?? path.join(process.cwd(), 'bridge.py');
const pythonCmd = process.env.VIBECHAT_PYTHON || 'python';


function useTerminalSize() {
  const {stdout} = useStdout();
  const getSize = () => ({
    columns: stdout.columns || 80,
    rows: stdout.rows || 24,
  });
  const [size, setSize] = useState(getSize);

  useEffect(() => {
    const update = () => {
      setSize((current) => {
        const next = getSize();
        return next.columns === current.columns && next.rows === current.rows
          ? current
          : next;
      });
    };
    stdout.on?.('resize', update);
    update();
    return () => stdout.off?.('resize', update);
  }, [stdout]);

  return size;
}


function createBridge(onEvent, onClose, onError) {
  const child = backendExe
    ? spawn(backendExe, [], {
        stdio: ['pipe', 'pipe', 'inherit'],
      })
    : spawn(pythonCmd, [bridgePath], {
        stdio: ['pipe', 'pipe', 'inherit'],
      });
  child.on('error', (err) => {
    onError(
      backendExe
        ? `无法启动后端程序（${backendExe}）：${err.message}`
        : `无法启动 Python 后端（${pythonCmd}）：${err.message}。请安装 Python 或用 VIBECHAT_PYTHON 指定路径`
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


const App = () => {
  const [input, setInput] = useState('');
  const [items, setItems] = useState([]); // {key, kind, text}
  const [stream, setStream] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [settingsDraft, setSettingsDraft] = useState({
    base_url: '',
    model: '',
  });
  const bridgeRef = useRef(null);
  const keyRef = useRef(0);

  const pushItem = (kind, text, meta = {}) => {
    const key = ++keyRef.current;
    setItems((prev) => [...prev, {key, kind, text, ...meta}]);
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
          case 'step':
            // 被核查打回时，丢弃本轮的流式候选输出，避免终端残留未通过内容。
            if (event.stage === 'verify_reject' || event.stage === 'retry') {
              setStream('');
            }
            pushItem('step', event.content, {
              stage: event.stage,
              tool: event.tool || '',
            });
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
            if (settingsOpen || settingsSaving) {
              setSettingsSaving(false);
              setSettingsError(event.message || '配置更新失败');
            } else {
              pushItem('error', event.message);
            }
            setBusy(false);
            setStatus('');
            setStream('');
            break;
          case 'ready':
            pushItem('notice', '后端已就绪，输入任务即可执行');
            setModel(event.model || '');
            setSettingsDraft((current) => ({
              ...current,
              base_url: event.base_url || current.base_url,
              model: event.model || current.model,
            }));
            break;
          case 'settings_result':
            setSettingsSaving(false);
            if (event.ok) {
              setSettingsOpen(false);
              setSettingsError('');
              if (event.model) {
                setModel(event.model);
                setSettingsDraft((current) => ({...current, model: event.model}));
              }
              pushItem('notice', event.content || '配置已生效');
            } else {
              setSettingsError(event.content || '配置更新失败');
            }
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

    if (trimmed === '/setting') {
      setSettingsOpen(true);
      setSettingsError('');
      return;
    }

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
      pushItem('notice', '可用命令: /setting /clear_history /clear_memory /exit');
      return;
    }
    setBusy(true);
    setStream('');
    bridgeRef.current?.send({type: 'task', content: trimmed});
  };

  const saveSettings = (settings) => {
    setSettingsSaving(true);
    setSettingsError('');
    bridgeRef.current?.send({type: 'settings', settings});
  };

  // 用 React state 订阅终端尺寸变化，交给 Ink 的 log-update 清理旧帧。
  // 自己直接写 ANSI 清屏会破坏 Ink 内部的光标/行数状态，缩放时反而会重叠或空白。
  const {columns, rows} = useTerminalSize();
  const wide = isWideLayout(columns);

  return (
    // 根节点高度固定为终端行数，让 Ink 进入全屏渲染路径：
    // 终端缩放后每次重绘都会整屏清除再绘制，避免残留旧帧造成内容重叠。
    <Box width="100%" height={rows} flexDirection="row">
      {wide && <Sidebar items={items} />}
      <Box flexGrow={1} minWidth={0} flexDirection="column">
        <WorkspaceHeader label="Task" busy={busy} compact={!wide} model={model} />
        <Transcript
          items={items}
          stream={stream}
          status={status}
          columns={columns}
          wide={wide}
        />
        {settingsOpen ? (
          <SettingsPanel
            initial={settingsDraft}
            onSave={saveSettings}
            onCancel={() => {
              setSettingsOpen(false);
              setSettingsError('');
            }}
            error={settingsError}
            busy={settingsSaving}
            columns={columns}
          />
        ) : (
          <Composer
            input={input}
            setInput={setInput}
            submit={submit}
            label="Task"
            busy={busy}
            columns={columns}
            maxHeight={Math.max(3, rows - 3)}
          />
        )}
      </Box>
    </Box>
  );
};

render(<App />);

export default App
