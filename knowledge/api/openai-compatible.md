# OpenAI 兼容 API 接入说明

- 基础地址通过 `BASE_URL` 配置
- API Key 通过 `DEEPSEEK_API` 配置
- 模型名通过 `MODEL_DEFAULT` 配置
- 支持 OpenAI 兼容的 chat completions 和工具调用格式
- 超时、429、5xx 会自动重试
