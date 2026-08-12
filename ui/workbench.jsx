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
  const threads = recent.length ? recent : ['No recent threads'];

  return (
    <Box
      width={28}
      height={rows}
      flexDirection="column"
      paddingX={1}
      borderStyle="single"
      borderTop={false}
      borderBottom={false}
      borderLeft={false}
      borderColor={COLOR.border}
    >
      <Box height={3} alignItems="center">
        <Text bold color={COLOR.amber}>VibeChatbot⌄</Text>
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

export function WorkspaceHeader({mode, busy, compact}) {
  const context = compact
    ? `VibeChatbot · ${MODE_LABEL[mode]}`
    : `Context: VibeChatbot · ${MODE_LABEL[mode]}`;

  return (
    <Box
      height={3}
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
      </Text>
      <Text color={COLOR.muted}>{context}</Text>
    </Box>
  );
}

export function ToolActivity({text, busy = false}) {
  return (
    <Box
      borderStyle="single"
      borderColor={COLOR.border}
      paddingX={1}
      marginBottom={1}
      width="100%"
    >
      <Text color={busy ? COLOR.amber : COLOR.success}>
        {busy ? '○' : '✓'}
      </Text>
      <Text bold>{'  Tool  '}</Text>
      <Text color={COLOR.muted} wrap="truncate-end">{text}</Text>
    </Box>
  );
}

export function ResultPanel({text}) {
  return (
    <Box
      flexDirection="column"
      borderStyle="single"
      borderColor={COLOR.border}
      marginBottom={1}
      width="100%"
    >
      <Box paddingX={1} backgroundColor={COLOR.surface}>
        <Text bold>Result</Text>
      </Box>
      <Box paddingX={1}>
        <Text color={COLOR.text} wrap="wrap">{text}</Text>
      </Box>
    </Box>
  );
}

function Message({item, columns}) {
  const bodyWidth = Math.max(columns - 2, 20);

  switch (item.kind) {
    case 'user':
      return (
        <Box flexDirection="column" marginBottom={1} width={columns}>
          <Text bold color={COLOR.amber}>You</Text>
          <Text color={COLOR.text} wrap="wrap" width={bodyWidth}>
            {item.text}
          </Text>
        </Box>
      );
    case 'assistant':
      return (
        <Box flexDirection="column" marginBottom={1} width={columns}>
          <Text bold color={COLOR.cyan}>Agent</Text>
          <Text color={COLOR.text} wrap="wrap" width={bodyWidth}>
            {item.text}
          </Text>
        </Box>
      );
    case 'log':
      return <ToolActivity text={item.text} />;
    case 'notice':
      return (
        <Text color={COLOR.muted} wrap="wrap">
          {'· '}{item.text}
        </Text>
      );
    case 'result':
      return <ResultPanel text={item.text} />;
    case 'error':
      return (
        <Text bold color={COLOR.error} wrap="wrap">
          {'! Error  '}{item.text}
        </Text>
      );
    default:
      return <Text> </Text>;
  }
}

export function Transcript({items, stream, status, rows, columns}) {
  const messageColumns = Math.max(columns - 4, 20);

  return (
    <Box
      flexDirection="column"
      height={getTranscriptRows(rows)}
      width={columns}
      overflow="hidden"
      paddingX={2}
      paddingTop={1}
    >
      {items.slice(-60).map((item) => (
        <Message key={item.key} item={item} columns={messageColumns} />
      ))}
      {stream && (
        <Message
          item={{kind: 'assistant', text: `${stream}▌`}}
          columns={messageColumns}
        />
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
    <Box
      width={columns}
      height={4}
      paddingX={1}
      paddingY={1}
      borderStyle="single"
      borderColor={COLOR.amber}
    >
      <Box flexGrow={1} marginRight={1}>
        <TextInput
          value={input}
          onChange={setInput}
          onSubmit={submit}
          placeholder={placeholder}
        />
      </Box>
      <Text color={COLOR.muted}>{MODE_LABEL[mode]}{'  '}</Text>
      <Text bold color={COLOR.amber}>↗</Text>
    </Box>
  );
}
