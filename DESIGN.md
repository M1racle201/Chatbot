---
name: VibeChatbot
description: A focused terminal workspace for chat and agentic development tasks.
colors:
  accent-amber: "#F2B84B"
  agent-cyan: "#58D1C2"
  canvas: "#0D1117"
  sidebar: "#11161D"
  surface: "#191F27"
  border: "#30363D"
  text: "#F2F2ED"
  muted: "#9CA3AD"
  success: "#68D391"
  error: "#F47067"
typography:
  body:
    fontFamily: "terminal monospace"
    fontSize: "1 cell"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "terminal monospace"
    fontSize: "1 cell"
    fontWeight: 600
    lineHeight: 1.2
rounded:
  terminal: "0px"
spacing:
  cell: "1ch"
  compact: "2ch"
  section: "1 row"
components:
  active-navigation:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.accent-amber}"
    rounded: "{rounded.terminal}"
    padding: "1 row 2ch"
  composer:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.text}"
    rounded: "{rounded.terminal}"
    padding: "1 row 2ch"
---

# Design System: VibeChatbot

## Overview

**Creative North Star: "The Quiet Terminal Workbench"**

VibeChatbot 使用接近黑色的终端画布、结构化分栏和稀少的琥珀强调色，营造安静、可信的开发工作台。布局参考现代桌面编程助手的清晰层级，但所有组件必须能在字符网格中诚实工作。

设计拒绝霓虹赛博朋克、紫色渐变、玻璃拟态、营销型数据看板和层层嵌套的圆角卡片。界面不会用装饰掩盖信息，也不会显示后端没有提供的能力。

**Key Characteristics:**

- 宽屏双栏，窄屏单栏。
- 对话与结果占据最大阅读面积。
- 琥珀用于当前选择，青绿用于 Agent 状态。
- 单线边框和色调分层建立结构，不使用阴影。
- 键盘交互优先，输入框始终可见。

## Colors

色彩体系以深石墨中性色为底，使用一个温暖强调色和一个状态色。

### Primary

- **Workbench Amber**：仅用于当前导航、用户标签、输入焦点和发送提示。

### Secondary

- **Agent Cyan**：仅用于 Agent 身份、在线状态和可信的进行中反馈。

### Neutral

- **Terminal Canvas**：主工作区背景。
- **Sidebar Graphite**：侧栏与主画布的轻微色调区分。
- **Raised Graphite**：选中项、工具行和结果标题区。
- **Hairline Border**：顶栏、侧栏、工具行和输入区边界。
- **Warm Text**：正文与主要标签。
- **Muted Steel**：时间、提示和次要元数据。

**The Sparse Accent Rule.** 琥珀和青绿合计不超过可见字符的 10%，强调色的稀少是层级的一部分。

## Typography

**Display Font:** 终端当前等宽字体
**Body Font:** 终端当前等宽字体
**Label/Mono Font:** 终端当前等宽字体

**Character:** 使用单一等宽字体，通过字重、颜色、缩进和留白建立层级，避免在终端中模拟不存在的字体系统。

### Hierarchy

- **Title**（粗体，1 cell）：产品名、当前用户和 Agent 标签。
- **Body**（常规，1 cell）：对话、结果与代码文本；长内容必须换行。
- **Label**（粗体，1 cell）：导航项、工具动作和结果标题。
- **Metadata**（常规，1 cell，弱化）：时间、模式、命令提示和状态说明。

**The One-Font Rule.** 不通过多字体制造层级，终端里所有差异都来自语义样式。

## Elevation

系统不使用阴影。深度只通过画布、侧栏和轻抬升表面的色调差异，加上单线边框表达。

**The Flat Workbench Rule.** 每个区域默认平整；只有选中项、工具活动和输入焦点可以获得抬升表面色。

## Components

### Navigation

- 侧栏在宽度充足时固定显示，品牌位于顶部，Threads 为当前项，最近输入作为运行期线程摘要。
- 当前项使用琥珀文字和抬升表面；其他项使用弱化文字。
- 窄终端隐藏侧栏，在顶栏保留项目和模式上下文。

### Conversation

- 用户消息以 `You` 标签开场，Agent 消息以 `Agent` 标签开场。
- 正文限制在主内容宽度内自然换行，消息组之间留一行。
- 时间仅在空间充足时显示，不能挤压正文。

### Tool Activity

- 工具日志使用单线边框行，左侧符号与动作标签并存。
- 成功、进行中和错误必须同时用文字或符号表达，不能只依赖颜色。

### Cards / Containers

- 只为工具活动、结果或代码输出使用容器，禁止把每条消息都做成卡片。
- 容器使用单线边框、零圆角和一格内边距。

### Inputs / Fields

- 输入框固定在主区底部，聚焦时使用琥珀边框。
- 左侧提供输入提示，右侧显示模式提示与发送符号。
- 空值、忙碌和错误状态都保留输入区位置，避免布局跳动。

## Do's and Don'ts

### Do:

- **Do** 在宽屏使用 26-30 列侧栏，并把剩余空间交给对话区。
- **Do** 让正文、输入和真实任务结果拥有最高视觉权重。
- **Do** 在 80×24 等窄终端隐藏次要区域并保留核心工作流。
- **Do** 使用文字、符号和颜色共同表达状态。

### Don't:

- **Don't** 做霓虹赛博朋克、紫色渐变或装饰性发光。
- **Don't** 做玻璃拟态、营销型数据看板或层层嵌套的圆角卡片。
- **Don't** 展示后端没有提供的文件差异、任务状态或持久化线程。
- **Don't** 为了模仿 Web 控件而破坏终端键盘工作流。
- **Don't** 截断用户或 Agent 的主要文本。
