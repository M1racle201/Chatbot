from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from mcp import ClientSession, StdioServerParameters, stdio_client
except ImportError:
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None


DEFAULT_PARAMETERS_SCHEMA = {"type": "object", "properties": {}}


class MCPConfigError(ValueError):
    """Raised when MCP configuration data is invalid."""


class MCPRegistryError(RuntimeError):
    """Raised when MCP registry startup or runtime behavior fails."""


@dataclass(frozen=True)
class ServerSpec:
    name: str
    command: str
    args: tuple[str, ...] = ()
    environment: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True)
class _DiscoveredTool:
    exposed_name: str
    original_name: str
    session: Any
    schema: dict[str, Any]


class MCPRegistry:
    def __init__(self, server_specs: Iterable[ServerSpec]):
        self._server_specs = tuple(
            spec for spec in server_specs if isinstance(spec, ServerSpec) and spec.enabled
        )
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, Any] = {}
        self._tools: dict[str, _DiscoveredTool] = {}
        self._tool_definitions: list[dict[str, Any]] = []

    @classmethod
    def from_config(cls, path: str | os.PathLike[str]) -> "MCPRegistry":
        config_path = Path(path)
        if not config_path.exists():
            return cls(())

        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise MCPConfigError(f"Unable to read MCP config '{config_path}': {exc}") from exc
        except json.JSONDecodeError as exc:
            raise MCPConfigError(f"Invalid JSON in MCP config '{config_path}': {exc.msg}") from exc

        if not isinstance(payload, Mapping):
            raise MCPConfigError("MCP config must be a JSON object")

        raw_servers = payload.get("servers", {})
        if not isinstance(raw_servers, Mapping):
            raise MCPConfigError("MCP config field 'servers' must be an object")

        specs: list[ServerSpec] = []
        seen_names: set[str] = set()

        for raw_name, raw_spec in raw_servers.items():
            name = _normalize_name(raw_name, "servers")
            if not isinstance(raw_spec, Mapping):
                raise MCPConfigError(f"Server '{name}' config must be an object")

            enabled = raw_spec.get("enabled", True)
            if not isinstance(enabled, bool):
                raise MCPConfigError(f"Server '{name}' field 'enabled' must be a boolean")
            if not enabled:
                continue

            command = _normalize_command(raw_spec.get("command"), f"server '{name}'")
            args = _coerce_args(raw_spec.get("args", ()), f"server '{name}'")
            environment = _resolve_env_names(raw_spec.get("env", ()), f"server '{name}'")

            if name in seen_names:
                raise MCPConfigError(f"Duplicate MCP server name '{name}'")
            seen_names.add(name)
            specs.append(
                ServerSpec(
                    name=name,
                    command=command,
                    args=args,
                    environment=environment,
                    enabled=True,
                )
            )

        return cls(specs)

    @classmethod
    def from_server_specs(
        cls,
        specs: Mapping[str, Any] | Iterable[ServerSpec | Mapping[str, Any]],
    ) -> "MCPRegistry":
        normalized_specs: list[ServerSpec] = []
        seen_names: set[str] = set()

        if isinstance(specs, Mapping):
            if _is_single_server_spec_mapping(specs):
                iterable: Iterable[ServerSpec | Mapping[str, Any]] = [specs]
            else:
                iterable = []
                for raw_name, raw_spec in specs.items():
                    if isinstance(raw_spec, ServerSpec):
                        if raw_spec.name != raw_name:
                            raise MCPConfigError(
                                f"ServerSpec name '{raw_spec.name}' does not match key '{raw_name}'"
                            )
                        iterable = [*iterable, raw_spec]
                        continue
                    if not isinstance(raw_spec, Mapping):
                        raise MCPConfigError(
                            f"Server '{raw_name}' config must be an object"
                        )
                    merged_spec = dict(raw_spec)
                    if "name" in merged_spec and merged_spec["name"] != raw_name:
                        raise MCPConfigError(
                            f"Server config name '{merged_spec['name']}' does not match key '{raw_name}'"
                        )
                    merged_spec["name"] = raw_name
                    iterable = [*iterable, merged_spec]
        else:
            iterable = specs

        for index, raw_spec in enumerate(iterable):
            spec = _coerce_server_spec(raw_spec, f"server spec #{index}")
            if not spec.enabled:
                continue
            if spec.name in seen_names:
                raise MCPConfigError(f"Duplicate MCP server name '{spec.name}'")
            seen_names.add(spec.name)
            normalized_specs.append(spec)

        return cls(normalized_specs)

    def server_names(self) -> list[str]:
        return [spec.name for spec in self._server_specs]

    def server_specs(self) -> list[ServerSpec]:
        return list(self._server_specs)

    def tool_definitions(self) -> list[dict[str, Any]]:
        return list(self._tool_definitions)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    async def start(self) -> "MCPRegistry":
        if self._stack is not None:
            return self
        if ClientSession is None or StdioServerParameters is None or stdio_client is None:
            raise MCPRegistryError("MCP SDK is not available")

        pending_stack = AsyncExitStack()
        pending_sessions: dict[str, Any] = {}
        pending_tools: dict[str, _DiscoveredTool] = {}
        pending_definitions: list[dict[str, Any]] = []

        try:
            for spec in self._server_specs:
                params = StdioServerParameters(
                    command=spec.command,
                    args=list(spec.args),
                    env=dict(spec.environment),
                )
                read, write = await pending_stack.enter_async_context(stdio_client(params))
                session = await pending_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tool_list = await session.list_tools()
                pending_sessions[spec.name] = session

                for tool in getattr(tool_list, "tools", None) or []:
                    original_name = _tool_name(tool)
                    exposed_name = f"{spec.name}__{original_name}"
                    if exposed_name in pending_tools:
                        raise MCPRegistryError(
                            f"MCP server '{spec.name}' exposed duplicate tool '{exposed_name}'"
                        )
                    schema = _tool_schema(exposed_name, tool)
                    pending_tools[exposed_name] = _DiscoveredTool(
                        exposed_name=exposed_name,
                        original_name=original_name,
                        session=session,
                        schema=schema,
                    )
                    pending_definitions.append(schema)
        except Exception as exc:
            try:
                await pending_stack.aclose()
            except Exception:
                pass
            finally:
                self._clear_runtime_state()
            if isinstance(exc, MCPRegistryError):
                raise
            raise MCPRegistryError(
                f"Failed to start MCP server '{spec.name}': {exc}"
            ) from exc

        self._stack = pending_stack
        self._sessions = pending_sessions
        self._tools = pending_tools
        self._tool_definitions = pending_definitions
        return self

    async def close(self) -> None:
        stack = self._stack
        self._stack = None
        self._clear_runtime_state()
        if stack is not None:
            await stack.aclose()

    async def __aenter__(self) -> "MCPRegistry":
        return await self.start()

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def call(self, exposed_name: str, args: Mapping[str, Any] | None) -> str:
        discovered = self._tools.get(exposed_name)
        if discovered is None:
            return _error_payload(f"Unknown MCP tool '{exposed_name}'")

        arguments = dict(args or {})
        try:
            result = await discovered.session.call_tool(discovered.original_name, arguments)
            if _truthy_attr(result, "isError", "is_error"):
                return _error_payload(_format_result_message(result))
            return _format_success_result(result)
        except Exception as exc:
            return _error_payload(f"MCP tool '{exposed_name}' failed: {exc}")

    def _clear_runtime_state(self) -> None:
        self._sessions = {}
        self._tools = {}
        self._tool_definitions = []


def _coerce_server_spec(raw_spec: ServerSpec | Mapping[str, Any], context: str) -> ServerSpec:
    if isinstance(raw_spec, ServerSpec):
        name = _normalize_name(raw_spec.name, context)
        command = _normalize_command(raw_spec.command, context)
        return ServerSpec(
            name=name,
            command=command,
            args=_coerce_args(raw_spec.args, context),
            environment=_coerce_environment_mapping(raw_spec.environment, context),
            enabled=bool(raw_spec.enabled),
        )

    if not isinstance(raw_spec, Mapping):
        raise MCPConfigError(f"{context} must be a ServerSpec or mapping")

    name = _normalize_name(raw_spec.get("name"), context)
    command = _normalize_command(raw_spec.get("command"), context)
    args = _coerce_args(raw_spec.get("args", ()), context)
    enabled = raw_spec.get("enabled", True)
    if not isinstance(enabled, bool):
        raise MCPConfigError(f"{context} field 'enabled' must be a boolean")

    if "environment" in raw_spec:
        environment = _coerce_environment_mapping(raw_spec.get("environment"), context)
    else:
        environment = _resolve_env_names(raw_spec.get("env", ()), context)

    return ServerSpec(
        name=name,
        command=command,
        args=args,
        environment=environment,
        enabled=enabled,
    )


def _is_single_server_spec_mapping(value: Mapping[str, Any]) -> bool:
    return (
        isinstance(value.get("name"), str)
        and isinstance(value.get("command"), str)
    )


def _normalize_name(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MCPConfigError(f"{context} requires a non-empty server name")
    return value.strip()


def _normalize_command(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MCPConfigError(f"{context} requires a non-empty command")
    return value.strip()


def _coerce_args(value: Any, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if (
        isinstance(value, (str, bytes))
        or isinstance(value, Mapping)
        or not isinstance(value, Iterable)
    ):
        raise MCPConfigError(f"{context} field 'args' must be an iterable of strings")
    args: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise MCPConfigError(f"{context} field 'args' must contain only strings")
        args.append(item)
    return tuple(args)


def _resolve_env_names(value: Any, context: str) -> dict[str, str]:
    if value is None:
        return {}
    if (
        isinstance(value, (str, bytes))
        or isinstance(value, Mapping)
        or not isinstance(value, Iterable)
    ):
        raise MCPConfigError(f"{context} field 'env' must be an iterable of environment names")

    environment: dict[str, str] = {}
    for raw_name in value:
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise MCPConfigError(
                f"{context} field 'env' must contain non-empty environment names"
            )
        name = raw_name.strip()
        if name in os.environ:
            environment[name] = os.environ[name]
    return environment


def _coerce_environment_mapping(value: Any, context: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise MCPConfigError(f"{context} field 'environment' must be an object")

    environment: dict[str, str] = {}
    for raw_name, raw_value in value.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise MCPConfigError(
                f"{context} field 'environment' must use non-empty string keys"
            )
        if raw_value is None:
            continue
        if not isinstance(raw_value, str):
            raise MCPConfigError(
                f"{context} field 'environment' must contain only string values"
            )
        environment[raw_name.strip()] = raw_value
    return environment


def _tool_name(tool: Any) -> str:
    name = _read_field(tool, "name")
    if not isinstance(name, str) or not name:
        raise MCPRegistryError("Discovered MCP tool is missing a name")
    return name


def _tool_schema(exposed_name: str, tool: Any) -> dict[str, Any]:
    description = _read_field(tool, "description")
    raw_parameters = _read_field(tool, "inputSchema", "input_schema")
    if raw_parameters is None:
        parameters = DEFAULT_PARAMETERS_SCHEMA.copy()
    else:
        if not isinstance(raw_parameters, Mapping):
            raise MCPRegistryError(
                f"MCP tool '{exposed_name}' has invalid input schema: {raw_parameters!r}"
            )
        parameters = dict(raw_parameters)
    return {
        "type": "function",
        "function": {
            "name": exposed_name,
            "description": description or "",
            "parameters": parameters,
        },
    }


def _read_field(value: Any, *names: str) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None

    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _truthy_attr(value: Any, *names: str) -> bool:
    return bool(_read_field(value, *names))


def _format_success_result(result: Any) -> str:
    structured = _read_field(result, "structuredContent", "structured_content")
    if structured is not None:
        return json.dumps(structured, ensure_ascii=False)

    texts = [_content_text(item) for item in (_read_field(result, "content") or [])]
    texts = [text for text in texts if text]
    return "\n".join(texts) or "(empty result)"


def _format_result_message(result: Any) -> str:
    structured = _read_field(result, "structuredContent", "structured_content")
    if structured is not None:
        return json.dumps(structured, ensure_ascii=False)

    texts = [_content_text(item) for item in (_read_field(result, "content") or [])]
    texts = [text for text in texts if text]
    return "\n".join(texts) or "(empty result)"


def _content_text(item: Any) -> str:
    text = _read_field(item, "text")
    if text is not None:
        return str(text)
    if isinstance(item, Mapping):
        return json.dumps(item, ensure_ascii=False, default=str)
    return str(item)


def _error_payload(message: str) -> str:
    return json.dumps({"error": str(message)}, ensure_ascii=False)
