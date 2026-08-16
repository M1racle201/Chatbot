export const WIDE_LAYOUT_COLUMNS = 104;
export const SIDEBAR_WIDTH = 28;
export const MAX_RECENT_THREADS = 1;
export const THREAD_TITLE_MAX_WIDTH = 22;

const LEADING_FILLERS = [
  '麻烦你帮我',
  '麻烦帮我',
  '请你帮我',
  '请帮我',
  '可以帮我',
  '能帮我',
  '帮我',
  '麻烦你',
  '请你',
  '请问',
  '我想要',
  '我想',
  '我要',
  '能不能',
  '是否可以',
];

const COLLOQUIAL_REPLACEMENTS = [
  ['查看一下', '查看'],
  ['看一下', '查看'],
  ['看一看', '查看'],
  ['看看', '查看'],
  ['读取一下', '读取'],
  ['读一下', '读取'],
  ['查询一下', '查询'],
  ['查一下', '查询'],
  ['查一查', '查询'],
  ['编写一下', '编写'],
  ['写一下', '编写'],
  ['运行一下', '运行'],
  ['跑一下', '运行'],
  ['处理一下', '处理'],
  ['弄一下', '处理'],
  ['搞一下', '处理'],
  ['给我', ''],
  ['一下', ''],
];

function truncateTitle(text, maxWidth = THREAD_TITLE_MAX_WIDTH) {
  let width = 0;
  let result = '';
  for (const char of String(text)) {
    const code = char.codePointAt(0);
    const charWidth = code >= 0x2e80 && code <= 0x9fff ? 2 : 1;
    if (width + charWidth > maxWidth) {
      return `${result}…`;
    }
    result += char;
    width += charWidth;
  }
  return result;
}

function toThreadTitle(text) {
  let title = String(text || '').replace(/\s+/g, ' ').trim();
  if (!title) return '';

  for (const filler of LEADING_FILLERS) {
    if (title.startsWith(filler)) {
      title = title.slice(filler.length).trim();
      break;
    }
  }

  for (const [from, to] of COLLOQUIAL_REPLACEMENTS) {
    title = title.split(from).join(to);
  }

  title = title
    .replace(/\s*([,，。.!！?？;；])\s*/g, '$1')
    .replace(/[。.!！?？~～]+$/g, '')
    .replace(/[吧啊呀嘛呢]+$/g, '')
    .replace(/^[:\-—]+|[:\-—]+$/g, '')
    .trim();

  if (!title) {
    title = String(text || '').replace(/\s+/g, ' ').trim();
  }

  return truncateTitle(title);
}

export function isWideLayout(columns) {
  return columns >= WIDE_LAYOUT_COLUMNS;
}

export function deriveRecentThreads(items) {
  // 优先使用第一条 rewriter 步骤：它是对用户第一次对话的书面化复写，
  // 比原始口语更适合作为会话标题。快速通道没有 rewriter 时再回退到原始输入。
  const firstRewrite = items.find(
    (item) =>
      item.kind === 'step' &&
      item.stage === 'rewriter' &&
      String(item.text || '').trim()
  );
  if (firstRewrite) {
    const rewritten = String(firstRewrite.text)
      .replace(/^复写后任务[::]\s*/, '')
      .trim();
    const title = toThreadTitle(rewritten);
    if (title) return [title];
  }

  const firstUserMessage = items.find(
    (item) => item.kind === 'user' && String(item.text || '').trim()
  );
  if (!firstUserMessage) return [];
  const title = toThreadTitle(firstUserMessage.text);
  return title ? [title] : [];
}
