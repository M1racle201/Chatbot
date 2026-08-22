"""VibeChatbot 入口：统一任务模式（自动路由快速通道 / 复写→执行→核查）。"""

from vibechatbot import config
from vibechatbot.runtime import build_runtime
from vibechatbot.skill_sync import sync_skills_prompts

sync_skills_prompts()
runtime = build_runtime()
chat_client = runtime.chat


def show_help() -> None:
    """打印可用命令列表。"""
    print("可用命令:")
    print("/clear_history - 清空历史记录")
    print("/clear_memory  - 清除对话记忆")
    print("/exit          - 退出")
    print(f"任务记录 -> {config.TASK_DIR}，流水线记录 -> {config.AGENTIC_DIR}")


def task_loop() -> None:
    """统一任务循环：简单工具任务自动走快速通道，其余走复写→执行→核查。"""
    print("任务模式：简单工具任务自动走快速通道，其余走复写 → 执行 → 核查，输入 /exit 退出")
    while True:
        task = input("任务: ").strip()
        if not task:
            continue
        if task == "/exit":
            print("再见")
            break
        if task == "/clear_history":
            chat_client.history.clear()
            continue
        if task in ("/clear_memory", "/clear_memmory"):
            chat_client.clear_memory()
            continue
        if runtime.is_simple_tool_task(task):
            print("快速通道：直接执行工具任务")
        else:
            print("复写 → 执行 → 核查")
        result = runtime.run_task(task)
        verdict = result.get("verdict", {})
        if verdict.get("exhausted"):
            print("\n⚠ 核查未通过已达上限，以下为强制输出:")
        print(f"结论: {result['output']}")
        attempts = result.get("attempts", {})
        if not verdict.get("passed") and verdict.get("reason"):
            print(f"核查: {verdict['reason']}")
        if attempts.get("rewrite") or attempts.get("research"):
            print(
                f"打回统计: 复写 {attempts['rewrite']} 次，"
                f"重搜 {attempts['research']} 次"
            )


def main() -> None:
    """主入口：显示帮助并进入统一任务模式。"""
    show_help()
    task_loop()


if __name__ == "__main__":
    main()
