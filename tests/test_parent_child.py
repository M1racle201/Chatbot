"""父子文档检索链路单元测试（fake store，不依赖 Chroma）。"""

import os
import tempfile
import unittest
from unittest.mock import patch

from vibechatbot.tools import file_tools


class FakeStore:
    def __init__(self):
        self.child_results = [
            {"document": "子文档A", "metadata": {"parent_id": "p1", "kind": "child"}},
            {"document": "子文档B", "metadata": {"parent_id": "p2", "kind": "child"}},
            {"document": "子文档C", "metadata": {"parent_id": "p1", "kind": "child"}},
        ]

    def count(self):
        return 10

    def query(self, query, top_k=10, where=None):
        self.last_query = query
        self.last_top_k = top_k
        self.last_where = where
        return self.child_results

    def get_by_ids(self, ids):
        return [
            {
                "id": parent_id,
                "document": f"父文档 {parent_id}",
                "metadata": {"source": "a.md", "parent_index": 0},
            }
            for parent_id in ids
        ]


class TestParentChildRetrieval(unittest.TestCase):
    def test_query_deduplicates_child_hits_to_parents(self):
        store = FakeStore()
        with patch.object(file_tools, "get_store", return_value=store):
            result = file_tools.query_documents("问题", top_k=2)

        self.assertEqual(store.last_where, {"kind": "child"})
        self.assertEqual(result["results"][0]["content"], "父文档 p1")
        self.assertEqual([item["parent_id"] for item in result["results"]], ["p1", "p2"])

    def test_empty_store_returns_error(self):
        class EmptyStore:
            def count(self):
                return 0

        with patch.object(file_tools, "get_store", return_value=EmptyStore()):
            result = file_tools.query_documents("问题")
        self.assertIn("error", result)

    def test_add_documents_creates_parent_and_child_records(self):
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write("第一段内容。" * 300)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)

        class CaptureStore:
            def __init__(self):
                self.added = None

            def add_texts(self, texts, metadatas=None, ids=None):
                self.added = (texts, metadatas, ids)
                return ids or []

        store = CaptureStore()
        with patch.object(file_tools, "get_store", return_value=store):
            result = file_tools.add_documents(tmp.name)

        self.assertGreater(result["parents"], 1)
        self.assertGreater(result["children"], result["parents"])
        texts, metadatas, ids = store.added
        kinds = [meta["kind"] for meta in metadatas]
        self.assertIn("parent", kinds)
        self.assertIn("child", kinds)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(all(text.strip() for text in texts))


if __name__ == "__main__":
    unittest.main()
