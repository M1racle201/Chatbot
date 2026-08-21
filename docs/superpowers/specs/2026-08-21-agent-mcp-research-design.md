# Agent 接入 MCP 研究工具设计

## 目标

让当前 VibeChatbot Agent 能够读取配置并动态使用 Firecrawl 等外部 MCP Server，完成“搜索软件工程岗位、提取字段、去重总结、保存为文档”的端到端任务。

新增 MCP 工具时，Agent 不增加专用工具函数或专用结果变量；工具 schema 和调用均由 MCP Registry 动态处理。

## 当前边界

当前实现有两条执行路径：

- src/vibechatbot/agent.py 是同步快速通道，直接使用本地 TOOL_DEFINITIONS 与 execute_tool。
- src/vibechatbot/agents/executor.py 位于异步 Pipeline，负责携带工具 schema 调用模型、执行工具并把结果回传。

Runtime.run_task() 是同步入口，每次 Pipeline 任务通过 asyncio.run() 创建事件循环。因此 MCP 会话不能跨任务或跨事件循环长期复用。

## 方案

采用任务级 MCP 生命周期：

1. Runtime 识别到网页研究任务后进入 Pipeline。
2. Pipeline 的同一个异步生命周期内创建 MCP Registry。
3. Registry 读取配置、启动每个已启用 MCP Server、初始化 ClientSession 并发现工具。
4. Executor 将本地工具和 MCP 工具 schema 合并后发送给模型。
5. 模型调用工具时，Router 按名称将本地工具交给 execute_tool，将 MCP 工具交给 Registry。
6. Registry 将 MCP CallToolResult 转成 Agent 可回传的 JSON 字符串。
7. Pipeline 结束后关闭所有 MCP session 和子进程，再结束 asyncio.run()。
8. 没有 MCP 配置时，现有本地工具路径保持可用。

不把同步 Agent 改造成全异步，也不让外部浏览器 Agent 脱离现有 Pipeline 独立运行。

## 配置

新增可选配置文件 config/mcp.json.example，实际配置路径由 MCP_CONFIG 指定，默认是 config/mcp.json。配置只保存命令、参数和环境变量名，不保存密钥值：

~~~json
{
  "servers": {
    "firecrawl": {
      "enabled": true,
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "env": ["FIRECRAWL_API_KEY"]
    }
  }
}
~~~

密钥通过项目 .env 或系统环境变量提供。配置文件不存在、内容为空或没有启用 server 时，Registry 返回空工具集合，不阻断本地 Agent。

## MCP Registry

新增 src/vibechatbot/mcp_registry.py，只负责 MCP 连接和协议适配：

- MCPRegistry.from_config(path)：读取并校验配置。
- async start() / async close()：管理 stdio client、session 和子进程。
- tool_definitions()：将 MCP 工具的 inputSchema 转换为 OpenAI function tool schema。
- async call(exposed_name, arguments)：按命名空间解析工具并调用。
- format_result(result)：统一处理文本、结构化内容、未知内容块和 MCP 错误。

外部工具名采用 <server>__<tool> 命名空间，例如 firecrawl__search，避免与本地工具冲突。模型只看到转换后的 schema，不接触 Python callable 或 session 对象。

## Agent 与路由

修改 ExecutorAgent，增加任务级 MCP 工具提供器和异步调用支持，同时保持现有 tool_executor 测试注入接口兼容：

- 每次 _call_llm() 使用本地 schema 加当前 Registry 的远程 schema。
- 本地同步工具继续通过线程执行。
- MCP 异步工具通过 Registry 直接 await。
- 所有工具结果都以字符串放入 role=tool 消息。
- 通用证据抽取从工具结果中识别 results、data、url、title、content、markdown 等字段，不按 Firecrawl 工具名写分支。

修改 Runtime 和 Pipeline 的任务级注入，使 Registry 只在一次 Pipeline 任务的异步生命周期内有效，并在异常时也关闭连接。

修改 is_simple_tool_task()：网页、搜索、岗位、招聘、职位、研究等任务优先走 Pipeline，即使任务文字同时包含“生成”或“保存”，也不能被同步快速通道绕过。

## Prompt 与输出

更新 prompt/executor：

- 明确岗位研究字段：公司、职位、地点、远程状态、薪资、发布时间、来源 URL。
- 优先官方招聘页，去重并标记未知信息。
- 需要多来源搜索和网页内容提取时使用 MCP 工具。
- 最终调用 save_long_output 保存 Markdown 报告。
- 结论保留来源 URL，不把大段网页原文直接输出到终端。

## 错误与安全

- 未配置 MCP 时本地工具正常工作。
- 配置文件格式错误、server 启动失败或 session 初始化失败时，返回包含 server 名称的明确错误，不静默伪造搜索结果。
- 密钥只从环境变量读取，不写入配置文件、任务存档或模型消息。
- 模型不能动态指定任意命令、路径或环境变量；MCP Server 只能来自用户配置。
- 不绕过目标网站登录、验证码或访问控制。

## 测试

新增测试覆盖：

- 配置读取、环境变量解析、禁用/空配置。
- MCP 工具 schema 命名空间转换。
- 文本、结构化内容、错误结果和未知内容块格式化。
- 任意 MCP 工具名和参数转发。
- Executor 合并本地与远程 schema，并正确区分同步本地工具和异步 MCP 工具。
- MCP server 启动失败时清理已启动的 session。
- 网页研究任务不会走简单工具快速通道。
- 现有本地工具和既有 Executor 测试保持通过。

真实联调使用已配置的 Firecrawl Server；没有 API key 时只运行 fake session 测试，不把外部服务可用性当作单元测试前置条件。

## 非目标

- 本次不实现 Browserbase、登录态浏览器或云浏览器账号管理。
- 本次不修改顶层 mcp/server.py demo 工具。
- 本次不重写同步快速通道 Agent。
- 本次不新增 Word 文档排版系统，首版保存 Markdown；后续可单独接入 docx 生成。

