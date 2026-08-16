# 常见问题排查

## esbuild 平台不匹配

现象：终端提示 “esbuild for another platform”。

原因：`node_modules` 从 Windows 拷贝到 WSL/Linux，里面是 `@esbuild/win32-x64`，而 Linux 需要 `@esbuild/linux-x64`。

处理：
- 不要复制 `node_modules`
- 在对应平台重新执行 `npm install`
- WSL 项目放在 Linux 原生目录，不要放在 `/mnt/c` 下运行

## SOCKS 代理导致 OpenAI 客户端报错

现象：运行时报 `Using SOCKS proxy, but the 'socksio' package is not installed`。

处理：
- 安装 `socksio`
- 或改用 HTTP 代理环境变量

## 向量库为空

现象：查询知识库时返回“向量库为空”。

处理：
- 先用 `add_documents` 或 `scripts/ingest_knowledge.py` 入库
- 支持 Markdown、TXT、HTML、JSON、YAML、代码文件、DOCX、PDF

## UI 文字重叠

原因：终端缩放导致 Ink 旧帧残留，或长文本在 auto-height 布局中未显式撑高。

处理：
- 使用 `useTerminalSize` 订阅 resize
- 根布局固定为终端行数，让 Ink 走全屏渲染路径
- 对长文本消息设置显式 `height` 和 `flexShrink={0}`
