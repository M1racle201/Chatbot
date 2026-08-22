---
name: security-best-practices
description: 在 agent 调用 run_python_script 前检查 Python 脚本是否安全；每次执行 Python 脚本前都必须使用本技能。仅在需要运行或审查 Python 脚本时触发。
---

# Python 脚本执行前安全检查

## 必须使用

- 调用 `run_python_script` 前必须加载本 SKILL.md
- 未通过检查的脚本禁止执行，不能通过改名、编码、拆段等方式绕过

## 检查流程

1. 把 `script` 参数完整读一遍，不要只检查片段
2. 对照下方高危清单
3. 给出结论：允许执行 / 禁止执行
4. 只有允许执行时才调用 `run_python_script`
5. `run_python_script` 内部也会做静态检查，命中高危规则会直接拒绝执行

## 高危清单（命中即禁止）

- shell 执行：`os.system`、`os.popen`、`subprocess` 的 `shell=True` 或字符串命令
- 动态执行：`eval`、`exec`、`compile`、`__import__`、动态导入外部模块
- 危险反序列化：`pickle.load(s)`、`shelve.open`、不安全的 `yaml.load`
- 网络外联：`requests`、`urllib.request`、`socket`、`http.client` 等访问外部网络
- 文件破坏：删除/移动/递归删除文件或目录，覆盖 `.env`、密钥、向量库等敏感路径
- 读取敏感文件：`.env`、`*.pem`、`*.key`、SSH 私钥、凭据文件
- 修改环境：写 `os.environ` 等影响进程环境的行为需说明并谨慎处理
- 资源耗尽：无界 `while True`、超大循环或内存分配，可能触发超时

## 允许执行的标准

- 只做本地计算、数据处理、文本处理
- 文件读写限定在 `OUTPUT` 或任务明确需要的安全目录
- 不访问外部网络，不读取密钥，不删除或覆盖敏感文件
- 脚本可以正常解析，不包含混淆或动态生成代码
