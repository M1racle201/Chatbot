"""Chroma 向量数据库：文档分块后向量化存储，支持语义检索（中文嵌入模型）。"""

import os
from datetime import datetime

import chromadb
import numpy as np
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from sklearn.feature_extraction.text import HashingVectorizer

from vibechatbot import config

DB_DIR = config.VECTOR_DB_DIR
COLLECTION_NAME = "documents"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class LocalHashingEmbeddingFunction:
    """离线本地 embedding：基于字符 n-gram 的哈希向量。

    不依赖 Hugging Face 下载，适合没有外网/内网隔离的研发环境；
    语义能力弱于 bge，但能保证入库和检索可用。
    """

    def __init__(
        self,
        n_features: int = 512,
        ngram_range: tuple = (1, 3),
    ):
        self._vectorizer = HashingVectorizer(
            n_features=n_features,
            analyzer="char_wb",
            ngram_range=ngram_range,
            alternate_sign=False,
            norm=None,
        )

    def __call__(self, input):
        texts = [
            text[len("query:"):] if text.startswith("query:") else text
            for text in input
        ]
        matrix = self._vectorizer.transform(texts).toarray()
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / (norms + 1e-9)
        return matrix.tolist()

    @staticmethod
    def name() -> str:
        return "local_hashing_char_wb"

    def is_legacy(self) -> bool:
        return False

    def default_space(self) -> str:
        return "l2"

    def supported_spaces(self) -> list:
        return ["l2", "cosine", "ip"]

    def validate_config(self, config) -> None:
        return

    @staticmethod
    def build_from_config(config):
        return LocalHashingEmbeddingFunction(**config)

    def get_config(self) -> dict:
        return {
            "n_features": self._vectorizer.n_features,
            "ngram_range": list(self._vectorizer.ngram_range),
        }


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


def _default_embedding_function():
    """默认使用本地离线 embedding；设置 VIBECHAT_EMBEDDING=bge 可改用 bge 模型。"""
    if os.environ.get("VIBECHAT_EMBEDDING", "local").lower() == "bge":
        return BgeZhEmbeddingFunction(
            model_name=EMBEDDING_MODEL, normalize_embeddings=True
        )
    return LocalHashingEmbeddingFunction()


class VectorStore:
    """基于 Chroma 的本地持久化向量数据库。"""

    def __init__(
        self,
        db_dir: str = None,
        collection_name: str = COLLECTION_NAME,
        embedding_function=None,
    ):
        self.db_dir = db_dir or DB_DIR
        self.collection_name = collection_name
        self.embedding_function = embedding_function or _default_embedding_function()
        self.client = chromadb.PersistentClient(path=self.db_dir)
        # 旧版空集合可能残留 sentence_transformer 的 embedding 配置；
        # 集合为空时直接删除重建，避免离线本地 embedding 与旧配置冲突。
        try:
            existing = self.client.get_collection(collection_name)
            if existing.count() == 0:
                self.client.delete_collection(collection_name)
        except Exception:
            pass
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
        ids = self.collection.get()["ids"]
        if ids:
            self.collection.delete(ids=ids)
