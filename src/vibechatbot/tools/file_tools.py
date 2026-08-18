"""文件加载工具：将 Word / txt / PDF 文件输出为纯文本字符串，并支持长文本分块。"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET
import subprocess
import sys
import tempfile
from datetime import datetime

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
    if ext in (
        ".txt", ".md", ".markdown", ".html", ".htm",
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv",
        ".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".java",
        ".c", ".cpp", ".cc", ".h", ".hpp", ".go", ".rs", ".sh", ".sql",
    ):
        content = _read_txt(path)
    elif ext in (".docx", ".doc"):
        content = _read_docx(path)
    elif ext == ".pdf":
        content = _read_pdf(path)
    else:
        return {"error": f"不支持的文件类型: {ext}（支持 txt / md / html / json / yaml / 常见代码文件 / docx / pdf）"}
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


MEMORY_COLLECTION = "conversation_memory"
MAX_ASSISTANT_MEMORY_CHARS = 300  # assistant 内容只保留简略摘要


_memory_summarizer = None


def set_memory_summarizer(summarizer):
    """注入 chat._summarize_messages，让记忆工具用 LLM 总结助手回复。"""
    global _memory_summarizer
    _memory_summarizer = summarizer


def _memory_store() -> VectorStore:
    return VectorStore(collection_name=MEMORY_COLLECTION)


def _rough_summarize(text: str, max_chars: int = MAX_ASSISTANT_MEMORY_CHARS) -> str:
    """对助手回复做粗略的抽取式总结。

    优先保留开头和结尾的关键句子，而不是简单截断前 N 个字。
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) <= max_chars:
        return text

    sentences = [
        part.strip()
        for part in re.split(r"(?<=[。！？.!?])\s*|\n+", text)
        if part.strip()
    ]
    if not sentences:
        return text[:max_chars].rstrip() + "…"

    candidates = []
    if len(sentences) <= 4:
        candidates = sentences
    else:
        candidates = sentences[:2] + sentences[-2:]

    summary = []
    total = 0
    for sentence in candidates:
        if summary and total + len(sentence) > max_chars:
            break
        summary.append(sentence)
        total += len(sentence)

    result = " ".join(summary)
    if len(result) > max_chars:
        result = result[:max_chars].rstrip() + "…"
    return result


def remember_conversation(
    user_content: str,
    assistant_content: str,
    topic: str = "",
) -> dict:
    """把完整一轮对话写入 MemoryVectorDB。

    - user 的原始内容完整保留
    - assistant 的内容做粗略总结
    - 整轮对话作为一个记忆元素写入
    """
    user_content = (user_content or "").strip()
    assistant_content = (assistant_content or "").strip()
    if not user_content and not assistant_content:
        return {"error": "对话内容不能为空"}

    brief_assistant = None
    if _memory_summarizer is not None:
        try:
            brief_assistant = _memory_summarizer(
                [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content},
                ]
            ).strip()
        except Exception:
            brief_assistant = None
    if not brief_assistant:
        brief_assistant = _rough_summarize(assistant_content)

    memory_text = f"用户: {user_content}\n助手: {brief_assistant}"
    store = _memory_store()
    created = datetime.now().isoformat(timespec="seconds")
    ids = store.add_texts(
        [memory_text],
        metadatas=[
            {
                "type": "conversation_memory",
                "topic": topic.strip(),
                "source": "conversation",
                "created_at": created,
                "user_chars": len(user_content),
                "assistant_chars": len(assistant_content),
            }
        ],
    )
    return {
        "memory_ids": ids,
        "chunks": 1,
        "topic": topic.strip(),
        "created_at": created,
    }


def query_memory(query: str, top_k: int = 3) -> dict:
    """从 MemoryVectorDB 检索与用户问题相关的历史对话摘要。"""
    query = (query or "").strip()
    if not query:
        return {"error": "检索内容不能为空"}

    store = _memory_store()
    if store.count() == 0:
        return {"error": "对话记忆为空，还没有可检索的历史摘要"}

    results = store.query(query, top_k=max(1, min(top_k, 10)))
    return {
        "query": query,
        "results": [
            {
                "document": item["document"],
                "source": item["metadata"].get("source"),
                "topic": item["metadata"].get("topic"),
                "created_at": item["metadata"].get("created_at"),
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


_LONG_OUTPUT_EXTENSIONS = {
    "paper": ".md",
    "code": ".txt",
    "html": ".html",
    "text": ".txt",
}


def save_long_output(filename: str, content: str, kind: str = "text") -> dict:
    """把论文/代码/HTML 等长文本保存到 OUTPUT 目录，只返回文件路径和大小。

    该工具的返回结果不包含正文，模型应仅向终端汇报文件地址和大小。
    """
    filename = filename.strip()
    if "." not in filename:
        filename += _LONG_OUTPUT_EXTENSIONS.get(kind, ".txt")
    result = save_file(filename, content)
    if "error" in result:
        return result
    return {
        "filename": result["filename"],
        "path": result["path"],
        "chars": result["chars"],
        "kind": kind if kind in _LONG_OUTPUT_EXTENSIONS else "text",
        "note": "内容已写入文件；请仅向用户回复文件路径和大小，不要粘贴正文。",
    }


def _is_within(path: str, directory: str) -> bool:
    """判断 path 是否位于 directory 目录内（规范化后，防路径穿越）。"""
    path = os.path.abspath(path)
    directory = os.path.abspath(directory)
    return os.path.commonpath([path, directory]) == directory


def write_file(path: str, content: str) -> dict:
    """修改或创建文本文件（覆盖写入）。

    除向量库目录（VECTOR_DB）外，允许写入任意路径（自动创建父目录）；
    向量库目录无论如何都禁止写入。
    """
    path = path.strip().strip('"').strip("'")
    if not path:
        return {"error": "路径不能为空"}
    if _is_within(path, config.VECTOR_DB_DIR):
        return {"error": "禁止修改向量库目录（VECTOR_DB）下的文件"}
    try:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        updated = os.path.exists(path)
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)
    except OSError as exc:
        return {"error": f"写入失败: {exc}"}
    return {"path": path, "chars": len(content), "updated": updated}


def _kill_process_tree(pid: int) -> None:
    """终止进程树：Windows 用 taskkill /T /F，其他平台仅杀直接子进程。"""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
        )
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def _read_output(path: str) -> str:
    """读取子进程输出文件（尝试常见编码，避免中文乱码）。"""
    for encoding in ("utf-8", "gbk"):
        try:
            with open(path, encoding=encoding) as file:
                return file.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def run_python_script(script: str, timeout: int = 60) -> dict:
    """生成临时 Python 脚本并立即执行，执行后自动删除临时文件。
    使用当前 Python 解释器执行（不依赖 PATH 中的 python）；
    超时时通过 taskkill 终止整个进程树（含脚本启动的子进程）；
    无论成功还是失败、超时，临时文件都会被删除。
    """
    fd, path = tempfile.mkstemp(prefix="vibechat_run_", suffix=".py")
    out_fd, out_path = tempfile.mkstemp(prefix="vibechat_out_", suffix=".txt")
    err_fd, err_path = tempfile.mkstemp(prefix="vibechat_err_", suffix=".txt")
    os.close(out_fd)
    os.close(err_fd)
    timed_out = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(script)
        with open(out_path, "wb") as out_file, open(err_path, "wb") as err_file:
            process = subprocess.Popen(
                [sys.executable, path],
                stdin=subprocess.DEVNULL,
                stdout=out_file,
                stderr=err_file,
            )
            try:
                process.wait(timeout=timeout)
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                _kill_process_tree(process.pid)
                process.wait()
                timed_out = True
                exit_code = None
        stdout_text = _read_output(out_path)
        stderr_text = _read_output(err_path)
        if timed_out:
            return {
                "error": f"脚本执行超时（>{timeout}s），已终止整个进程树并删除临时文件",
                "stdout": stdout_text[-4000:],
                "stderr": stderr_text[-2000:],
            }
        return {
            "exit_code": exit_code,
            "stdout": stdout_text[-4000:],
            "stderr": stderr_text[-2000:],
        }
    except OSError as exc:
        return {"error": f"脚本执行失败: {exc}"}
    finally:
        for temp_path in (path, out_path, err_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


TOOLS = [
    {
        "name": "load",
        "description": (
            "读取本地文件内容并转换为纯文本字符串，"
            "支持 Word（.docx）、文本/ Markdown / HTML / JSON / YAML / 常见代码文件、"
            "PDF（.pdf）；长文本请设置 chunk=true，返回按 500 字分好的块，避免浪费 token"
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
            "读取本地文件（Word/txt/PDF/Markdown/HTML/JSON/YAML/代码文件），"
            "自动分块后存入向量数据库，供后续语义检索问答使用；"
            "重复入库同一文件会追加新块"
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
    {
        "name": "save_long_output",
        "description": (
            "将论文、长报告、代码、HTML 等长文本保存到 OUTPUT 目录，"
            "并只返回文件路径与大小；用于避免把大段正文直接输出到终端。"
            "除非用户明确要求源码或原文，否则长内容一律用本工具保存，"
            "终端只汇报文件地址。filename 建议带扩展名；kind 可为 "
            "paper/code/html/text"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "文件名，如 report.md、app.py、page.html",
                },
                "content": {
                    "type": "string",
                    "description": "要保存的完整文本内容",
                },
                "kind": {
                    "type": "string",
                    "description": "内容类型：paper/code/html/text，默认 text",
                },
            },
            "required": ["filename", "content"],
        },
        "function": save_long_output,
    },
    {
        "name": "write_file",
        "description": (
            "修改或创建文本文件（覆盖写入）；除向量库目录（VECTOR_DB）外"
            "允许任意路径，自动创建父目录；严禁写入向量库目录；"
            "用于按用户要求改写已有文件的内容"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要修改的文件完整路径"},
                "content": {"type": "string", "description": "写入的新内容（覆盖原文件）"},
            },
            "required": ["path", "content"],
        },
        "function": write_file,
    },
    {
        "name": "run_python_script",
        "description": (
            "生成临时 Python 脚本并立即执行（使用当前 Python 解释器），执行结束后自动删除临时文件；"
            "超时会终止整个进程树（含脚本启动的子进程），不会残留后台进程；"
            "适用于批量文件处理、数据分析等需要运行自定义代码的场景；"
            "timeout 为执行超时秒数，默认 60 秒，失败/超时都会自动清理"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "要执行的 Python 代码"},
                "timeout": {
                    "type": "integer",
                    "description": "执行超时秒数，1-300 秒，默认 60",
                },
            },
            "required": ["script"],
        },
        "function": run_python_script,
    },
    {
        "name": "remember_conversation",
        "description": (
            "把当前与用户的这一轮对话做简略总结后写入 MemoryVectorDB，"
            "供后续用户询问“之前说过什么/上下文/上次对话”时检索使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "user_content": {
                    "type": "string",
                    "description": "用户本轮输入的原始内容，完整写入记忆",
                },
                "assistant_content": {
                    "type": "string",
                    "description": "助手本轮回复内容，只保留简略片段",
                },
                "topic": {
                    "type": "string",
                    "description": "可选的话题标签，便于检索时区分主题",
                },
            },
            "required": ["user_content", "assistant_content"],
        },
        "function": remember_conversation,
    },
    {
        "name": "query_memory",
        "description": (
            "当用户询问关于上下文、历史对话、之前说过什么、上次结论等问题时，"
            "从 MemoryVectorDB 检索相关对话记忆。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要检索的上下文问题或关键词",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回记忆条数，默认 3",
                },
            },
            "required": ["query"],
        },
        "function": query_memory,
    },
]

