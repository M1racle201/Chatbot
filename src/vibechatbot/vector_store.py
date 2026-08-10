"""Chroma 向量数据库：文档分块后向量化存储，支持语义检索（中文嵌入模型）。"""

from datetime import datetime

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from vibechatbot import config

DB_DIR = config.VECTOR_DB_DIR
COLLECTION_NAME = "documents"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class BgeZhEmbeddingFunction(SentenceTransformerEmbeddingFunction):
    """bge 中文嵌入：文本以 query: 开头时自动加检索指令（bge 官方建议）。"""

    def __call__(self, input):
        texts = [
            QUERY_INSTRUCTION + text[len("query:"):]
            if text.startswith("query:")
            else text
            for text in input
        ]
        return super().__call__(texts)


class VectorStore:
    """基于 Chroma 的本地持久化向量数据库。"""

    def __init__(
        self,
        db_dir: str = DB_DIR,
        collection_name: str = COLLECTION_NAME,
        embedding_function: SentenceTransformerEmbeddingFunction = None,
    ):
        self.db_dir = db_dir
        self.collection_name = collection_name
        self.embedding_function = embedding_function or BgeZhEmbeddingFunction(
            model_name=EMBEDDING_MODEL, normalize_embeddings=True
        )
        self.client = chromadb.PersistentClient(path=db_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
        )

    def add_texts(
        self,
        texts: list,
        metadatas: list = None,
        ids: list = None,
    ) -> list:
        """添加文本块到向量库。

        texts: 文本块列表（可用 load 工具的 chunks）
        metadatas: 每块的元数据（如来源路径、块索引）
        返回生成的 id 列表。
        """
        if not texts:
            return []
        if ids is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            ids = [f"{timestamp}_{index}" for index in range(len(texts))]
        if metadatas is None:
            metadatas = [{} for _ in texts]
        self.collection.add(documents=texts, metadatas=metadatas, ids=ids)
        return ids

    def query(self, text: str, top_k: int = 5) -> list:
        """按语义检索最相关的文本块，返回文档与元数据列表。"""
        query_embeddings = self.embedding_function(["query:" + text])
        result = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=top_k,
        )
        documents = result["documents"][0] if result.get("documents") else []
        metadatas = result["metadatas"][0] if result.get("metadatas") else []
        return [
            {"document": doc, "metadata": meta}
            for doc, meta in zip(documents, metadatas)
        ]

    def count(self) -> int:
        """返回向量库中的文本块数量。"""
        return self.collection.count()

    def clear(self) -> None:
        """清空向量库中的所有数据。"""
        self.collection.delete(where={})
