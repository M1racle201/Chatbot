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

    def compress(
        self,
        messages: list,
        summary: str,
        keep_recent_rounds: int = 20,
    ) -> list:
        """对话轮次超限时压缩历史：保留最近的对话轮数，旧对话总结为 system 消息。

        messages: 完整消息列表
        summary: 模型对全部对话的总结文本
        keep_recent_rounds: 保留的最近对话轮数（每轮 = user + assistant）
        返回压缩后的消息列表（最开始的 system 提示词保留）。
        """
        # 最开始的 system 提示词；历史中可能混有旧的总结 system，一并剔除
        original_system = (
            messages[0]
            if messages and messages[0].get("role") == "system"
            else None
        )
        # 只保留最近的 keep_recent_rounds 轮对话（每轮 = user + assistant 两条）
        recent = [
            m for m in messages if m.get("role") != "system"
        ][-(keep_recent_rounds * 2):]
        result = []
        if original_system:
            result.append(original_system)
        if summary.strip():
            result.append({"role": "system", "content": "对话总结：" + summary})
        return result + recent
