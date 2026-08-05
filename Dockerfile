# ================= VibeChatbot 容器镜像 =================
# 构建:
#   docker build -t vibechatbot .
#
# 运行 Web UI (Streamlit):
#   docker run -d --name vibe -p 8501:8501 --env-file .env ^
#     -v vibe_chat:/app/CHAT -v vibe_task:/app/TASK ^
#     -v vibe_output:/app/OUTPUT -v vibe_db:/app/VECTOR_DB ^
#     -v vibe_model:/app/.hf_cache vibechatbot
#
# 运行终端聊天模式 (main.py):
#   docker run -it --rm --env-file .env -v vibe_db:/app/VECTOR_DB ^
#     vibechatbot python main.py
# ========================================================

# 3.12-slim:chromadb / sentence-transformers / torch 在 3.14 上支持不稳定
FROM python:3.12-slim

# PYTHONUNBUFFERED: 日志实时输出; HF_HOME: 嵌入模型缓存目录(挂载卷持久化)
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.hf_cache \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# 先装 torch CPU 版(~200MB),避免 PyPI 默认 CUDA 版(2GB+)导致镜像过大
# 本项目只用 CPU 做嵌入推理,不需要 GPU
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install -r requirements.txt

# 预下载中文嵌入模型(bge-small-zh-v1.5),构建时需联网;
# 失败不阻塞构建,首次使用向量库时会自动补下载
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
    || echo "警告: 嵌入模型下载失败,首次运行向量库时会自动下载"

# 复制项目代码(.env / 数据目录已被 .dockerignore 排除)
COPY . .

# 数据持久化目录: 聊天/任务记录、输出文件、向量库、模型缓存
VOLUME ["/app/CHAT", "/app/TASK", "/app/OUTPUT", "/app/VECTOR_DB", "/app/.hf_cache"]

EXPOSE 8501

# 默认启动 Streamlit Web UI;终端聊天可覆盖 CMD,见顶部注释
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
