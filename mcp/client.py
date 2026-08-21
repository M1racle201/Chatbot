import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client


SERVER_SCRIPT = Path(__file__).resolve().parent / "server.py"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _content_text(item: Any) -> str:
    if isinstance(item, dict) and "text" in item:
        return str(item["text"])
    text = getattr(item, "text", None)
    if text is not None:
        return str(text)
    return _json_text(item)


def format_tool_result(result: Any) -> str:
    parts = [_content_text(item) for item in (getattr(result, "content", None) or [])]

    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured is not None:
        parts.append(_json_text(structured))

    return "\n".join(parts) or "(empty result)"


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description="调用 MCP 服务端工具")
    parser.add_argument("--list", action="store_true", dest="list_tools")
    parser.add_argument("tool_name", nargs="?")
    parser.add_argument("arguments", nargs="?", default="{}")
    args = parser.parse_args(argv)

    if args.list_tools:
        if args.tool_name is not None:
            parser.error("--list 不能与工具名同时使用")
        args.arguments = {}
        return args

    if args.tool_name is None:
        parser.error("需要提供工具名，或使用 --list")

    try:
        args.arguments = json.loads(args.arguments)
    except json.JSONDecodeError as exc:
        parser.error(f"工具参数不是合法 JSON: {exc.msg}")
    if not isinstance(args.arguments, dict):
        parser.error("工具参数必须是 JSON 对象")
    return args


async def call_tool(session: ClientSession, tool_name: str, arguments: dict) -> Any:
    return await session.call_tool(tool_name, arguments)


def format_tool_list(result: Any) -> str:
    lines = ["tools:"]
    for tool in getattr(result, "tools", []) or []:
        description = getattr(tool, "description", None) or ""
        schema = getattr(tool, "inputSchema", None)
        suffix = f" inputSchema={_json_text(schema)}" if schema else ""
        lines.append(f"- {tool.name}: {description}{suffix}")
    return "\n".join(lines)


async def run(argv=None) -> int:
    args = parse_arguments(argv)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT)],
    )

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                if args.list_tools:
                    print(format_tool_list(await session.list_tools()))
                    return 0

                result = await call_tool(session, args.tool_name, args.arguments)
                output = format_tool_result(result)
                if getattr(result, "isError", False):
                    print(output, file=sys.stderr)
                    return 1
                print(output)
                return 0
    except Exception as exc:
        print(f"MCP client error: {exc}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
