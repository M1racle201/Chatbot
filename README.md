# JobMatchAgent

面向岗位搜索与推荐的 Agentic RAG 助手。用户可以用自然语言按岗位类型、城市、薪资、学历、工作经验和技能等条件检索职位，系统从岗位知识库中筛选匹配岗位，整理岗位职责、必须技能和加分技能，并基于原始 JD 证据生成推荐结果。

项目将简单查询与文件操作走快速通道，复杂的岗位检索与推荐任务进入 **复写器 → 执行器 → 核查器** 闭环，减少岗位信息遗漏和无依据推荐。

## 安装

要求 Python >= 3.10。

```bash
pip install -e .                 # 推荐：同时获得 jobmatchagent 命令
# 或 pip install -r requirements.txt
```

## 配置

运行中的 Ink UI 输入 `/setting` 打开配置面板，填写以下内容后按 Enter 保存：

- API URL，例如 `https://api.deepseek.com`
- API Key，例如 `sk-your-key`
- Model，例如 `deepseek-v4-flash`

配置会保存到 `data/settings.json` 并立即热加载；API Key 在界面和事件日志中不会回显。API Key 留空表示保持当前配置，按 Esc 可取消设置。

```text
/setting
```

## 运行

```bash
终端运行:
1.
jobmatchagent #(需要进行 'pip install -e.' 后才能使用)
2.
CLI : python -m jobmatchagent.cli）
3.
Ink UI：cd ui && npm install && npm start

以上任意方法选其一即可
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
JobMatchAgent/
├── src/jobmatchagent/    # config / cli / chat / runtime / vector_store / agent / bridge
│   ├── agents/           # rewriter → executor → verifier 闭环
│   └── tools/            # file_tools + 注册表
├── prompt/               # system / rewriter / executor / verifier 提示词
├── data/                 # CHAT / TASK / AGENTIC / OUTPUT / VECTOR_DB
├── ui/                   # Ink 前端（index.jsx / workbench.jsx / layout.mjs）
└── tests/                # Python + UI 测试
```
