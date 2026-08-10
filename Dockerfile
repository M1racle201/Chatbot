# ================= VibeChatbot 容器镜像 =================
# 构建:
#   docker build -t vibechatbot .
#
# 运行终端聊天 (交互式):
#   docker run -it --rm --env-file .env -v vibe_db:/app/data/VECTOR_DB \
#     vibechatbot
#
# 数据卷: 聊天记录 / 任务记录 / 流水线 / 输出 / 向量库 统一挂到 /app/data 下
# ========================================================

# 3.12-slim: chromadb / sentence-transformers / torch 在 3.14 上支持不稳定
FROM python:3.12-slim

# PYTHONUNBUFFERED: 日志实时输出; HF_HOME: 嵌入模型缓存目录(挂载卷持久化)
# PYTHONPATH: src-layout 包位置,`python -m vibechatbot.cli` 无需安装即可运行
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    HF_HOME=/app/.hf_cache

WORKDIR /app

# 先装 torch CPU 版(~200MB),避免 PyPI 默认 CUDA 版(2GB+)导致镜像过大
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install -r requirements.txt

# 预下载中文嵌入模型(bge-small-zh-v1.5),失败不阻塞构建
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
    || echo "警告: 嵌入模型下载失败,首次运行向量库时会自动下载"

# 复制项目代码(.env / data 已被 .dockerignore 排除)
COPY . .

# 数据持久化目录: 聊天/任务/流水线/输出/向量库 + 模型缓存
VOLUME ["/app/data", "/app/.hf_cache"]

# 默认启动终端聊天 CLI;`docker run -it` 交互使用
CMD ["python", "-m", "vibechatbot.cli"]
