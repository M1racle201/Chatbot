"""VectorStore 生命周期测试。"""

import tempfile
import unittest

from jobmatchagent.vector_store import VectorStore


class TestVectorStoreLifecycle(unittest.TestCase):
    def test_close_releases_persistent_client_before_tempdir_cleanup(self):
        with tempfile.TemporaryDirectory() as db_dir:
            store = VectorStore(db_dir=db_dir, collection_name="lifecycle")
            store.add_texts(
                ["生命周期测试"],
                metadatas=[{"source": "test"}],
            )
            store.close()


if __name__ == "__main__":
    unittest.main()
