# Agentic RAG 多智能体流水线 实现计划

> **目标:** 构建"复写 → 执行 → 核查"三段式异步多 Agent 流水线,让检索、工具调用、结论生成与质量核查形成闭环。

**架构:**
用户输入 → Agent1(复写)→ Agent2(向量检索 + 工具调用 + 生成结论)→ Agent3(核查)
→ 通过则输出最终结论;不通过则生成修正提示词返回 Agent1 重新复写,最多重试 N 轮。

**技术栈:** Python asyncio + openai(DeepSeek)+ 现有 `TOOLS/` 工具集 + `VectorStore` + pytest

---

## 关键设计决策(待确认)

- **D1 通信格式:** Agent 之间传递统一 `AgentMessage`(结构化 dict:task / context / output / meta),便于存档与审计
- **D2 异步方式:** `BaseAgent.run()` 为 `async`;LLM 调用用 `AsyncOpenAI`;同步工具(chroma/文件)用 `asyncio.to_thread` 包裹,不阻塞事件循环
- **D3 重试上限:** 核查不通过最多重试 3 轮;第 4 轮强制输出,并标注"未通过核查"
- **D4 复用策略:** Agent2 复用现有 `agent.py` 的工具循环逻辑;新增 `agents/` 目录,不改动已稳定的 `chat.py` / `agent.py` 主逻辑

## 文件结构

```
agents/
  __init__.py       # 导出 BaseAgent / Pipeline
  base.py           # AgentMessage 数据类 + BaseAgent 异步抽象基类
  rewriter.py       # Agent1 复写器
  executor.py       # Agent2 主题执行器(检索+工具+结论)
  verifier.py       # Agent3 核查器
  pipeline.py       # 编排器:顺序调度 + 重试闭环 + 过程存档
tests/
  test_base.py
  test_rewriter.py
  test_executor.py
  test_verifier.py
  test_pipeline.py
AGENTIC/            # 运行时生成:流水线过程存档 JSON(不入库,加 .gitignore)
```

## 任务分解

### 阶段 1:基座(可独立验证)
- [x] **T1 BaseAgent 基类**
  - 文件:`agents/base.py`、`agents/__init__.py`
  - 内容:`AgentMessage` 数据类;`BaseAgent(name, chat)` 抽象类,定义 `async run(msg) -> AgentMessage`,子类实现 `_process()`;统一的上下文与过程日志记录
  - 验收:mock 子类可异步跑通,过程日志结构正确
- [x] **T2 编排器骨架**
  - 文件:`agents/pipeline.py`
  - 内容:`Pipeline([a1, a2, a3])` 按序调用,捕获异常;先空实现跑通调度
  - 验收:注入 3 个假 agent,顺序与返回值正确
- [x] **T3 过程存档**
  - 内容:每轮把 复写结果 / 工具过程 / 结论 / 核查结果 写入 `AGENTIC/时间戳.json`
  - 验收:端到端空流程后 JSON 字段完整

### 阶段 2:Agent1 复写器
- [x] **T4 rewriter.py 主体**
  - 文件:`agents/rewriter.py`
  - 内容:调用 LLM 复写用户输入(澄清意图、补全上下文、输出适合检索的表述),输出结构化文本
- [x] **T5 复写提示词**
  - 内容:复用 `prompt/` 体系,新增 `prompt/rewriter`(不改原意、指出模糊点、为检索优化措辞)
  - 验收:mock LLM 固定返回,复写结果正确透传
- [x] **T6 复写单测**
  - 文件:`tests/test_rewriter.py`

### 阶段 3:Agent2 主题执行器
- [x] **T7 工具循环复用**
  - 文件:`agents/executor.py`
  - 内容:从 `agent.py` 抽取工具循环(load / query_documents / add_documents / save_file),保留上下文压缩保护
- [x] **T8 检索优先策略**
  - 内容:涉及知识库问题先 `query_documents`,基于检索结果生成结论并标注来源
- [x] **T9 执行器单测**
  - 文件:`tests/test_executor.py`(mock 工具注册表)

### 阶段 4:Agent3 核查器 + 闭环
- [x] **T10 verifier.py 主体**
  - 文件:`agents/verifier.py`
  - 内容:核查结论——是否回答问题、依据是否来自检索结果、是否与原文冲突(幻觉检测)
- [x] **T11 重试闭环**
  - 内容:核查不通过 → 生成"修正提示"(指出问题 + 修改建议)→ 返回 Agent1 重新复写 → Agent2 重跑;接入 D3 上限
- [x] **T12 核查单测**
  - 文件:`tests/test_verifier.py`、`tests/test_pipeline.py`(模拟"不通过→重试→通过"与"超限降级")

### 阶段 5:接入用户入口
- [ ] **T13 CLI 接入**
  - 文件:`main.py`
  - 内容:新增 `/agentic` 命令,复用 `agent_loop` 交互方式
- [ ] **T14 UI 接入**
  - 文件:`app.py`
  - 内容:新增"智能任务"模式;展示最终结论 + 流水线过程时间线(复写/执行/核查,不暴露工具细节)
  - 验收:手动跑通 3 个真实场景

### 阶段 6:真实验收
- [ ] **T15 场景 1**:知识库问答(检索命中,来源标注正确)
- [ ] **T16 场景 2**:文档任务(读文件 → 总结 → save_file 生成报告)
- [ ] **T17 场景 3**:核查失败重试(构造易幻觉问题,观察至少 1 轮重试)
- [ ] **T18 收尾**:更新 `requirements.txt`(如需新增依赖)、README 说明、commit

---

## 备注
- 每个 T 完成后独立 commit,分支 `codex/agentic-rag`
- 全程 mock LLM 优先,真实 API 只在阶段 6 使用,省 token
- 老代码(`chat.py` / `agent.py`)保持不动,Agent2 只抽取复用,不侵入改造
