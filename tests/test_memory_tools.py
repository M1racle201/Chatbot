"""对话记忆工具测试：写入 MemoryVectorDB 并可检索。"""

import os
import tempfile
import unittest
from unittest.mock import patch

from vibechatbot import vector_store
from vibechatbot.tools import TOOL_DEFINITIONS, execute_tool
from vibechatbot.tools.file_tools import (
    query_memory,
    remember_conversation,
    set_memory_summarizer,
)


class TestMemoryTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_dir = os.path.join(self.tmp.name, "memory_db")
        os.makedirs(self.db_dir)
        set_memory_summarizer(None)
        self.addCleanup(set_memory_summarizer, None)

    def _call(self, func, *args, **kwargs):
        with patch.object(vector_store, "DB_DIR", self.db_dir):
            return func(*args, **kwargs)

    def test_remember_and_query_memory(self):
        self._call(
            remember_conversation,
            "用户要求把项目架构说明保存到知识库，结论是已保存并返回路径。",
            "助手已把架构说明保存到文件，并返回路径。",
            topic="知识库",
        )
        result = self._call(query_memory, "之前是不是保存过项目架构说明？")
        self.assertNotIn("error", result)
        self.assertGreaterEqual(len(result["results"]), 1)
        self.assertIn("项目架构", result["results"][0]["document"])

    def test_query_memory_empty_returns_error(self):
        result = self._call(query_memory, "之前说过什么")
        self.assertIn("error", result)

    def test_remember_rejects_empty_content(self):
        result = self._call(remember_conversation, "", "")
        self.assertIn("error", result)

    def test_memory_tools_registered(self):
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        self.assertIn("remember_conversation", names)
        self.assertIn("query_memory", names)

    def test_execute_tool_roundtrip(self):
        self._call(
            remember_conversation,
            "用户问过离线 embedding 怎么用，回答是使用本地哈希向量。",
            "离线 embedding 使用本地哈希向量。",
            topic="embedding",
        )
        raw = self._call(
            execute_tool, "query_memory", {"query": "离线 embedding 怎么用"}
        )
        self.assertIn("本地哈希", raw)

    def test_remember_uses_injected_chat_summarizer(self):
        set_memory_summarizer(
            lambda messages: "LLM总结：" + messages[-1]["content"][:10]
        )
        self._call(
            remember_conversation,
            "用户问题",
            "助手非常长的回复内容",
        )
        result = self._call(query_memory, "用户问题")
        self.assertIn("LLM总结", result["results"][0]["document"])

    def test_assistant_content_is_roughly_summarized_not_truncated(self):
        assistant = (
            "首先我说明了背景。"
            + "中间有很多不重要的补充内容。" * 30
            + "最后结论是必须使用离线 embedding。"
        )
        self._call(
            remember_conversation,
            "用户问 embedding 怎么选",
            assistant,
            topic="embedding",
        )
        result = self._call(query_memory, "embedding 怎么选")
        memory = result["results"][0]["document"]
        self.assertIn("最后结论是必须使用离线 embedding", memory)
        self.assertNotIn("中间有很多不重要的补充内容。" * 30, memory)

    def test_memory_element_contains_full_user_and_brief_assistant(self):
        user_text = "请帮我读取这个很长的文件，并总结其中的技术方案。" + "补充内容。" * 50
        assistant_text = "好的，我已经读取完成，总结如下：" + "这里是非常长的助手回复。" * 30
        self._call(
            remember_conversation,
            user_text,
            assistant_text,
            topic="长对话",
        )
        result = self._call(query_memory, "读取这个很长的文件")
        self.assertNotIn("error", result)
        memory = result["results"][0]["document"]
        self.assertIn(user_text, memory)
        self.assertIn("这里是非常长的助手回复", memory)
        # assistant 只保留简略片段，不应包含完整长回复
        self.assertLess(len(memory), len(user_text) + len(assistant_text))


if __name__ == "__main__":
    unittest.main()
