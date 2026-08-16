# VibeChatbot 架构说明

## 核心组成

- 后端：Python 3.10+，采用 src-layout，核心代码位于 `src/vibechatbot/`
- 前端：Ink/React 终端 UI，位于 `ui/`，通过 stdio JSON 协议与 Python 桥接
- 向量库：Chroma + `bge-small-zh-v1.5` embedding，持久化在 `data/VECTOR_DB/`

## 任务模式

- 简单工具任务走快速通道，直接由执行器调用工具
- 复杂任务走复写器 -> 执行器 -> 核查器闭环
- 核查不通过时区分“复写打回”和“检索打回”，分别重试

## 关键目录

- `src/vibechatbot/agents/` 各 Agent
- `src/vibechatbot/tools/` 工具注册与实现
- `src/vibechatbot/runtime.py` 统一任务入口
- `src/vibechatbot/bridge.py` UI 与后端桥
- `prompt/` 系统提示词和 Agent 提示词
