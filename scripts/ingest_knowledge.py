#!/usr/bin/env python3
"""把研发知识库目录/文件批量入库到 Chroma 向量库。

用法:
    python scripts/ingest_knowledge.py [path ...]

支持 txt/md/html/json/yaml/常见代码文件/docx/pdf。
"""

import argparse
import sys
from pathlib import Path

from vibechatbot.tools.file_tools import add_documents
from vibechatbot.vector_store import VectorStore

SUPPORTED_SUFFIXES = {
    ".txt", ".md", ".markdown", ".html", ".htm",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".java",
    ".c", ".cpp", ".cc", ".h", ".hpp", ".go", ".rs", ".sh", ".sql",
    ".docx", ".doc", ".pdf",
}


def collect_files(paths):
    files = []
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_dir():
            for item in sorted(path.rglob("*")):
                if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES:
                    files.append(item)
        elif path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(path)
        else:
            print(f"跳过不支持的路径: {raw}", file=sys.stderr)
    return files


def main():
    parser = argparse.ArgumentParser(description="批量入库研发知识库")
    parser.add_argument("paths", nargs="+", help="要入库的文件或目录")
    args = parser.parse_args()

    files = collect_files(args.paths)
    if not files:
        print("没有找到可入库的文件", file=sys.stderr)
        return 1

    ok = 0
    failed = 0
    for file in files:
        result = add_documents(str(file))
        if "error" in result:
            print(f"FAIL  {file}: {result['error']}")
            failed += 1
        else:
            print(
                f"OK    {file}: parents={result.get('parents')}, "
                f"children={result.get('children')}"
            )
            ok += 1

    count = VectorStore().count()
    print(f"\n完成: 成功 {ok}, 失败 {failed}, 向量库当前记录数 {count}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
