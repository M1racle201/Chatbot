# VibeChatbot

DeepSeek 驱动的终端 Agentic RAG 助手。聊天/任务/Agent 三模式统一为「任务模式」：简单工具任务走快速通道，复杂任务自动进入 **复写器 → 执行器 → 核查器** 闭环。

## 安装

要求 Python >= 3.10。

```bash
pip install -e .                 # 推荐：同时获得 vibechat 命令
# 或 pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为项目根 `.env`：

```bash
DEEPSEEK_API=sk-your-key-here
BASE_URL=https://api.deepseek.com
MODEL_DEFAULT=deepseek-chat
PROMPT=prompt/system
```

> `.env` 须为无 BOM 的 UTF-8，程序自动从项目根加载。可选：`VIBECHAT_ROOT`（根目录覆盖）、`VIBECHAT_DATA_DIR`（数据根，默认 `data/`）、`HISTORY_FILE`。

如果你要启用 MCP 工具，再做两步：

1. 把 `config/mcp.json.example` 复制为 `config/mcp.json`。
2. 在 `.env` 里补上 `MCP_CONFIG=config/mcp.json`，并为对应的 MCP Server 配好环境变量，比如 `FIRECRAWL_API_KEY=your-key-here`。

MCP server 的命令需要由用户预先配置，模型不会动态启动任意命令。缺少 `mcp.json` 时，程序仍然只使用本地工具，不会影响原有任务流。Firecrawl 这里只是一个可替换示例，你也可以改成 Playwright 或其他 MCP server。使用 MCP server 需要本机有 Node.js / `npx`，以及对应依赖。

浏览器 / 网页类任务会进入 Agentic Pipeline，任务领域本身不绑定；是否接入 MCP 只是工具层的选择，不改变任务路由的核心逻辑。

## 运行

```bash
vibechat #(需要进行 'pip install -e.' 后才能使用)

CLI python -m vibechatbot.cli）

Ink UI：cd ui && npm install && npm start

## 核心特性

- **任务路由**：读取/保存/写入/入库等简单工具任务直达工具；其余走 Agentic RAG 闭环。
- **三 Agent 闭环**：复写器改写 → 执行器检索向量库、调用工具生成结论 → 核查器核对，不通过则打回（区分「重写」/「重搜」，最多 3 轮）。
- **流式输出**：仅执行器最终结论流式；重试跳过已发送前缀，避免 UI 重复。
- **会话存档**：每会话一个 JSON，存 `data/TASK`（快速通道）或 `data/AGENTIC`（闭环），工具调用完整记录。
- **语义检索**：Chroma 向量库 + `bge-small-zh-v1.5` embedding。
- **Ink UI**：`ui/` React/Ink 前端，经 stdio JSON 协议与 Python 桥接。

## 工具

| 工具 | 作用 |
| --- | --- |
| `load` | 读取 word/txt/pdf 并分块（约 500 字/块） |
| `query_documents` | 向量库语义检索 |
| `add_documents` | 文本块入库 |
| `save_file` | 保存到 `data/OUTPUT` |
| `write_file` | 写文件（白名单为除向量库外任意路径） |

## 测试

```powershell
$env:PYTHONPATH = "$PWD\src"; python -m unittest discover -s tests   # Python
cd ui; npm run build; npm test                                       # UI
```

## 目录结构

```
VibeChatbot/
├── src/vibechatbot/      # config / cli / chat / runtime / vector_store / agent / bridge
│   ├── agents/           # rewriter → executor → verifier 闭环
│   └── tools/            # file_tools + 注册表
├── prompt/               # system / rewriter / executor / verifier 提示词
├── data/                 # CHAT / TASK / AGENTIC / OUTPUT / VECTOR_DB
├── ui/                   # Ink 前端（index.jsx / workbench.jsx / layout.mjs）
└── tests/                # Python + UI 测试
```
