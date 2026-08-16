# 开发规范

## Python

- 使用 `src/vibechatbot/` 包结构
- 新增工具在 `src/vibechatbot/tools/` 下实现，并注册到 `TOOLS`
- 保持单元测试覆盖，测试放在 `tests/`
- 避免在测试环境引入重型依赖，工具按需延迟加载

## UI

- 终端 UI 使用 Ink/React
- 长文本不要直接刷到终端，优先调用 `save_long_output` 保存成文件
- 终端内容变化后需要处理 resize，避免旧帧重叠
- 输入框超过最大可见行数时折叠为 `[x lines * y rows]`

## 通用

- 危险操作如删除向量库、清空数据必须拒绝
- 文件输出默认写入 `data/OUTPUT/`
- 不得写入 `data/VECTOR_DB/`
