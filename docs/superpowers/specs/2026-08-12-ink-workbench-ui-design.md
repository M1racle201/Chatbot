# Ink Workbench UI 设计

## 背景

当前 `ui/index.jsx` 已包含 `Header`、`Transcript`、`Message` 和 `Composer`，能够处理终端尺寸变化、流式输出和现有桥接事件。本次改造以用户确认的桌面编程助手参考图为视觉基准，把现有单列界面调整为“终端工作台”。

参考图是像素界面，Ink 是字符网格。本设计追求结构、比例、信息层级、颜色语义和交互节奏的一致，不承诺终端无法实现的像素、字体抗锯齿、鼠标按钮和圆角效果。

## 目标

- 宽终端中还原参考图的左侧导航、顶部状态栏、中央对话流、工具活动、结果面板和底部输入框。
- 使用接近参考图的深石墨背景、琥珀主强调色和青绿 Agent 状态色。
- 保留 `/chat`、`/agent`、`/agentic`、`/clear_history`、`/clear_memory` 和 `/exit` 行为。
- 保留 `ready`、`user`、`stream`、`done`、`log`、`notice`、`status`、`result` 和 `error` 事件协议。
- 在窄终端和低高度终端中保持输入区与最近消息可用。

## 非目标

- 不把 Ink 替换为 Web、Electron 或其他桌面技术栈。
- 不修改 Python 后端、桥接协议、Agent 流程或向量库。
- 不新增持久化线程、文件浏览器、任务管理器或鼠标导航。
- 不伪造参考图中的文件差异、行数统计、时间戳或任务完成字段。
- 不新增 npm 依赖。

## 页面结构

### 宽屏布局

当终端宽度不少于 104 列时，根容器使用全高双栏：

1. `Sidebar` 占 28 列，包含品牌、Threads/Files/Tasks 导航、当前运行期的最近用户输入，以及底部 Settings 标签。
2. `Workspace` 占剩余宽度，纵向包含 `WorkspaceHeader`、`Transcript` 和 `Composer`。

侧栏与工作区之间使用单线分隔。侧栏只承担视觉上下文，不引入新的导航行为。最近线程从当前 `items` 中的用户消息派生，最多显示 6 条，文本按侧栏宽度截断；没有用户消息时显示一条空状态说明。

### 窄屏布局

当终端宽度小于 104 列时隐藏侧栏，`Workspace` 使用全部宽度。顶栏同时显示 `VibeChatbot`、当前模式和 Agent 状态，保证侧栏隐藏后上下文不丢失。

当终端高度不足 24 行时，减少 Transcript 的外边距和可见历史数量，但 Composer 始终保留。历史窗口继续有明确上限，防止长会话让 Ink 渲染失控。

## 组件

### `Sidebar({items, rows})`

- 顶部显示琥珀色 `VibeChatbot`。
- `Threads` 为当前项，使用抬升表面与琥珀文字；`Files` 和 `Tasks` 是弱化标签。
- `Recent threads` 使用当前会话的用户消息摘要，不持久化、不点击。
- `Settings` 固定在可用空间底部附近，只作视觉还原。

### `WorkspaceHeader({mode, busy, compact})`

- 左侧使用青绿色状态点和 `Agent ready`/`Agent working`。
- 右侧显示 `Context: VibeChatbot · <mode>`；窄屏改为更短的模式文本。
- 使用底部分隔线，不用完整卡片边框。

### `Message({item, columns})`

- 用户消息显示琥珀色 `You` 标签和正常正文。
- Assistant 和 stream 显示青绿色 `Agent` 标签，正文保持高对比度。
- log 渲染为 `ToolActivity`：单线边框、动作符号和弱化内容。
- result 渲染为 `ResultPanel`：标题行与正文区分开，正文允许换行。
- notice 作为低权重系统文本；error 同时使用红色标签和 `!` 符号。

### `Composer({input, setInput, submit, mode, busy, columns})`

- 使用单线琥珀边框模拟参考图的输入区域。
- 空输入时显示 `Ask the agent to inspect, build, or explain...`。
- 右侧显示当前模式或 `Auto` 等价提示，并显示 `↗` 发送符号；实际提交仍使用 Enter。
- busy 时文案改为处理中，但输入框位置不移动。

## 数据流与兼容性

`App` 继续拥有 bridge 生命周期、事件处理、模式切换、输入提交和 busy 状态。新增展示组件只接收派生属性，不发送新事件，也不修改任何命令分支。

`Sidebar` 的最近线程通过 `items.filter(item => item.kind === 'user')` 派生。工具与结果面板只使用现有 `log`、`status`、`result` 和 `error` 文本，不解析或推断不存在的文件元数据。

## 错误与边界

- 后端启动失败继续渲染为 error 消息。
- 未选择模式、未知命令和 ready 通知继续可见。
- 极窄终端下优先保证消息正文宽度不低于 20 列；必要时省略侧栏、时间和右侧上下文。
- 所有主要消息使用换行，只有导航摘要、状态和元数据允许截断。
- 颜色不可用时，`You`、`Agent`、`!`、`✓` 等文本或符号仍能表达语义。

## 验收标准

- 在 140×40 或更大终端中，能看到接近参考图比例的 28 列侧栏和主工作区。
- 顶部状态、用户消息、Agent 消息、工具活动、结果面板和输入框形成清晰的垂直阅读顺序。
- 在 80×24 终端中，侧栏自动隐藏，输入框和最新消息仍可见。
- 主要正文不使用主动截断。
- 所有现有命令和 bridge 事件路径保持不变。
- `tests/test_ui_layout.py` 覆盖宽窄布局标记、运行期线程派生、语义标签和 Composer 文案。
- `npm.cmd --prefix ui run start` 能完成 esbuild 打包；非交互环境只允许出现 Ink 不支持 raw mode 的预期运行时限制，打包阶段必须退出成功。
- Python 全量 unittest 通过。

## 验证计划

1. 先扩展 `tests/test_ui_layout.py`，确认新布局测试在生产代码修改前失败。
2. 修改 `ui/index.jsx`，运行聚焦测试直到通过。
3. 运行 Python 全量 unittest，确认 UI 源码检查和后端回归测试均通过。
4. 单独运行 esbuild 打包，不依赖交互式 TTY。
5. 在宽终端与窄终端中启动 Ink，人工检查布局比例、换行和输入区位置。
