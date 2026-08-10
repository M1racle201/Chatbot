"""文件加载工具：将 Word / txt / PDF 文件输出为纯文本字符串，并支持长文本分块。"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET

from vibechatbot import config
from vibechatbot.vector_store import VectorStore

# Word 文档的命名空间
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# 分块切分符优先级：换行最优，其次感叹号，最后句号
SEPARATORS = ("\n", "!", "！", ".", "。")

# 向量库单例（首次使用时自动建库）
_store = None

# agent 可写文件的白名单目录
OUTPUT_DIR = config.OUTPUT_DIR

# 合法文件名：不含路径分隔符、点号开头、路径穿越等
_SAFE_FILENAME = re.compile(r"^[\w\u4e00-\u9fff.\-]+$")


def get_store() -> VectorStore:
    """获取向量库实例（惰性创建）。"""
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def split_text(text: str, max_chars: int = 500) -> list:
    """将长文本分割为不超过 max_chars 字的块。

    切分优先级：换行符 \n 最优，其次 !/！，再次 ./。
    仅当窗口内找不到合适分隔符时才硬切。
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    window = text[:max_chars]
    cut = -1
    for separator in SEPARATORS:
        position = window.rfind(separator)
        # 分隔符位置太靠前时换下一优先级，避免切出过小的块
        if position >= max_chars // 2:
            cut = position
            break
    if cut == -1:
        cut = max_chars
    else:
        cut += 1  # 保留分隔符本身

    return [text[:cut].strip()] + split_text(text[cut:], max_chars)


def _read_txt(path: str) -> str:
    """读取 txt 文件（自动尝试常见编码）。"""
    for encoding in ("utf-8", "gbk", "utf-16"):
        try:
            with open(path, encoding=encoding) as file:
                return file.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法识别文件编码: {path}")


def _read_docx(path: str) -> str:
    """读取 docx 文件：解包 zip，提取 word/document.xml 中的段落文本。"""
    with zipfile.ZipFile(path) as archive:
        try:
            xml_content = archive.read("word/document.xml").decode("utf-8")
        except KeyError:
            raise ValueError("不是有效的 docx 文件")
    root = ET.fromstring(xml_content)
    paragraphs = []
    for paragraph in root.iter(f"{{{_W_NS}}}p"):
        text = "".join(
            node.text or ""
            for node in paragraph.iter(f"{{{_W_NS}}}t")
        )
        paragraphs.append(text)
    return "\n".join(paragraphs)


def _read_pdf(path: str) -> str:
    """读取 pdf 文件：按页提取文本。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ValueError("缺少 PDF 解析库，请安装 pypdf：pip install pypdf")
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def load_file(path: str, chunk: bool = False) -> dict:
    """将 word/txt/pdf 文件内容转换为纯文本字符串。

    chunk=True 时在程序内直接分块返回（避免文本经模型复述浪费 token）。
    """
    path = path.strip().strip('"').strip("'")
    if not os.path.exists(path):
        return {"error": f"文件不存在: {path}"}
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        content = _read_txt(path)
    elif ext in (".docx", ".doc"):
        content = _read_docx(path)
    elif ext == ".pdf":
        content = _read_pdf(path)
    else:
        return {"error": f"不支持的文件类型: {ext}（支持 txt / docx / pdf）"}
    result = {"path": path, "content": content}
    if chunk:
        result["chunks"] = split_text(content)
    return result


def add_documents(path: str) -> dict:
    """读取文件、自动分块并存入向量数据库，供后续语义检索。"""
    path = path.strip().strip('"').strip("'")
    loaded = load_file(path, chunk=True)
    if "error" in loaded:
        return loaded
    chunks = loaded["chunks"]
    store = get_store()
    metadatas = [
        {"source": path, "index": index, "total": len(chunks)}
        for index in range(len(chunks))
    ]
    ids = store.add_texts(chunks, metadatas=metadatas)
    return {"path": path, "chunks": len(chunks), "added_ids": len(ids)}


def query_documents(query: str, top_k: int = 5) -> dict:
    """语义检索向量库中最相关的文档片段。"""
    store = get_store()
    if store.count() == 0:
        return {"error": "向量库为空，请先用 add_documents 存入文档"}
    results = store.query(query, top_k=top_k)
    return {
        "query": query,
        "results": [
            {
                "content": item["document"],
                "source": item["metadata"].get("source"),
                "index": item["metadata"].get("index"),
            }
            for item in results
        ],
    }


def save_file(filename: str, content: str) -> dict:
    """生成文件到 OUTPUT 白名单目录（仅文件名，禁止路径穿越）。"""
    filename = filename.strip()
    if not filename or filename.startswith(".") or not _SAFE_FILENAME.match(filename):
        return {"error": f"非法文件名: {filename}（仅允许文件名，不含路径）"}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
    return {"filename": filename, "path": path, "chars": len(content)}


TOOLS = [
    {
        "name": "load",
        "description": (
            "读取本地文件内容并转换为纯文本字符串，"
            "支持 Word（.docx）、文本（.txt）、PDF（.pdf）文件；"
            "长文本请设置 chunk=true，返回按 500 字分好的块，避免浪费 token"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要读取的文件路径"},
                "chunk": {
                    "type": "boolean",
                    "description": "是否分块返回（长文本建议 true），默认 false",
                },
            },
            "required": ["path"],
        },
        "function": load_file,
    },
    {
        "name": "add_documents",
        "description": (
            "读取本地文件（Word/txt/PDF），自动分块后存入向量数据库，"
            "供后续语义检索问答使用；重复入库同一文件会追加新块"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要入库的文件路径"}
            },
            "required": ["path"],
        },
        "function": add_documents,
    },
    {
        "name": "query_documents",
        "description": (
            "语义检索向量数据库，返回与问题最相关的文档片段及其来源，"
            "用于基于知识库的问答"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索问题或关键词"},
                "top_k": {
                    "type": "integer",
                    "description": "返回片段数量，默认 5",
                },
            },
            "required": ["query"],
        },
        "function": query_documents,
    },
    {
        "name": "save_file",
        "description": (
            "生成文本文件并保存到 OUTPUT 目录（白名单），"
            "filename 只允许文件名（不含路径）；用于保存报告、总结等输出内容"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "文件名，如 报告.md"},
                "content": {"type": "string", "description": "要写入的文件内容"},
            },
            "required": ["filename", "content"],
        },
        "function": save_file,
    },
]

