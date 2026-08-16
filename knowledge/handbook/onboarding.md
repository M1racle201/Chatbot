# 新成员上手

## 环境

- Python 3.10+，推荐 3.12
- Node.js 18+
- 创建虚拟环境并安装依赖

## 启动 UI

```bash
cd ui
npm install
npm start
```

## 入库知识

```bash
python scripts/ingest_knowledge.py knowledge
```

## 测试

```bash
.venv/bin/python -m unittest discover -s tests
cd ui && npm test
```
