"""对话历史持久化：将用户与 LLM 的对话以 JSON 格式读写。"""

import json
import os

HISTORY_FILE = os.path.join("CHAT", "history.json")


class History:
    """负责对话历史的加载与保存。"""

    def __init__(self, filename: str = HISTORY_FILE):
        self.filename = filename

    def load(self) -> list:
        """读取历史消息列表；文件不存在或内容损坏时返回空列表。"""
        if not os.path.exists(self.filename):
            return []
        try:
            with open(self.filename, encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def save(self, messages: list) -> None:
        """将消息列表写入 JSON 文件（自动创建目录）。"""
        directory = os.path.dirname(self.filename)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.filename, "w", encoding="utf-8") as file:
            json.dump(messages, file, ensure_ascii=False, indent=2)

    def clear(self) -> None:
        """清空历史记录。"""
        self.save([])
        print("历史记录已清空")
