"""VibeChatbot 入口：命令模式 + 持续对话循环 + 自主任务模式。"""

from agent import Agent
from chat import Chat
from history import HISTORY_FILE, History

chat_client = Chat()
agent_client = Agent(chat_client)


def show_help() -> None:
    """打印可用命令列表。"""
    print("/chat          - 开始聊天")
    print("/agent         - 自主任务模式（拆解任务、调用工具、汇报结果）")
    print("/clear_history - 清空历史记录")
    print("/clear_memory  - 清除对话记忆")
    print("/exit          - 退出")
    print("聊天记录 -> CHAT/，任务记录 -> TASK/")


def agent_loop() -> None:
    """任务循环：持续接收任务，输入 /exit 退出。"""
    print("已进入自主任务模式，输入 /exit 退出")
    while True:
        task = input("任务: ").strip()
        if not task:
            continue
        if task == "/exit":
            print("已退出任务模式")
            break
        if task == "/clear_history":
            chat_client.history.clear()
            continue
        if task in ("/clear_memory", "/clear_memmory"):
            chat_client.clear_memory()
            continue
        agent_client.run(task)


def chat_loop() -> None:
    """聊天循环：持续对话，输入 /exit 退出对话。"""
    print("已进入聊天模式，输入 /exit 退出对话")
    while True:
        user_input = input("你: ").strip()
        if not user_input:
            continue
        if user_input == "/exit":
            print("已退出对话")
            break
        if user_input == "/clear_history":
            chat_client.history.clear()
            continue
        if user_input in ("/clear_memory", "/clear_memmory"):
            chat_client.clear_memory()
            continue
        print("AI: ", end="")
        chat_client.chat(user_input)


def main() -> None:
    """主循环：命令模式。"""
    print("输入 /chat 开始聊天，/agent 执行任务，/exit 退出")
    while True:
        command = input("> ").strip()
        if command == "/chat":
            chat_loop()
        elif command == "/agent":
            agent_loop()
        elif command == "/clear_history":
            chat_client.history.clear()
        elif command in ("/clear_memory", "/clear_memmory"):
            chat_client.clear_memory()
        elif command == "/exit":
            print("再见！")
            break
        else:
            show_help()


if __name__ == "__main__":
    main()
