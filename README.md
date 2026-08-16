# VibeChatbot

DeepSeek 驱动的终端 Agentic RAG 助手：把聊天、任务、Agent 三种模式统一为「任务模式」，复杂任务自动走 **复写器 → 执行器 → 核查器** 闭环，简单工具任务走快速通道直达工具。

## 使用教程

### 安装

要求 Python >= 3.10。

```bash
# 方式一：以可编辑方式安装（推荐，同时获得 vibechat 命令）
pip install -e .

# 方式二：只装依赖
pip install -r requirements.txt
```

### 配置

复制 `.env.example` 为项目根目录下的 `.env` 并填写：

```bash
DEEPSEEK_API=sk-your-key-here
BASE_URL=https://api.deepseek.com
MODEL_DEFAULT=deepseek-chat
PROMPT=prompt/system
```

> 注意：`.env` 必须是**无 BOM 的 UTF-8** 编码；程序会自动从项目根目录加载，任意工作目录下运行都能找到。

环境变量一览：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API` | 空 | DeepSeek API Key（必填） |
| `BASE_URL` | `https://api.deepseek.com` | API 地址，可切换其他 OpenAI 兼容服务 |
| `MODEL_DEFAULT` | `deepseek-chat` | 默认模型名 |
| `PROMPT` | `prompt/system` | 系统提示词文件路径（相对项目根） |

### 运行

#### CLI

```bash
vibechat
# 或 python -m vibechatbot.cli
```

可用命令：

| 命令 | 作用 |
| --- | --- |
| `/clear_history` | 清空历史记录文件 |
| `/clear_memory` | 清除当前对话记忆（messages 重置，不清 JSON） |
| `/exit` | 退出任务模式 |

#### Ink UI

```bash
cd ui
npm install
npm start
```

UI 通过 `ui/bridge.py`（stdio JSON 协议）与 Python 后端通信，界面右上角显示当前模型名。
