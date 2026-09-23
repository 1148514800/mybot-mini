"""MCP external tools: connect official SDK clients and expose them as Tools."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

import httpx2
from mcp import Client, InputRequiredRoundsExceededError, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from .tools.base import Tool, ToolResult
from .tracing import redact_mapping, redact_text


MAX_TOOL_NAME_LENGTH = 64
MAX_DESCRIPTION_CHARS = 2000
DEFAULT_TOOL_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_CHARS = 12000
SUPPORTED_TRANSPORTS = frozenset({"stdio", "streamable_http"})

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")
_SENSITIVE_KEY_PARTS = (
    "authorization", "password", "token", "api_key", "apikey", "cookie", "secret",
)


class MCPConfigError(ValueError):
    pass


class MissingEnvironmentVariable(MCPConfigError):
    def __init__(self, variable: str):
        super().__init__(f"environment variable '{variable}' is not set")


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _string_mapping(value: Any, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MCPConfigError(f"{field_name} must be an object")
    for key, item in value.items():
        if not isinstance(item, str):
            raise MCPConfigError(f"{field_name}.{key} must be a string")
    return {str(key): item for key, item in value.items()}


def _expand_environment(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in os.environ:
            raise MissingEnvironmentVariable(name)
        return os.environ[name]

    return _ENV_REFERENCE.sub(replace, value)


@dataclass(slots=True, frozen=True)
class MCPServerConfig:
    name: str
    enabled: bool = True
    transport: str = "stdio"
    required: bool = False
    tool_timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MCPServerConfig:
        if not isinstance(data, dict):
            raise MCPConfigError(f"mcp.servers.{name} must be an object")
        transport = str(data.get("transport", "stdio")).strip().lower()
        if transport not in SUPPORTED_TRANSPORTS:
            raise MCPConfigError(f"mcp server '{name}' has unsupported transport '{transport}'")

        raw_args = data.get("args", [])
        if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
            raise MCPConfigError(f"mcp.servers.{name}.args must be a string array")

        timeout = float(data.get("tool_timeout_seconds", DEFAULT_TOOL_TIMEOUT_SECONDS))
        if timeout <= 0:
            raise MCPConfigError(f"mcp.servers.{name}.tool_timeout_seconds must be positive")
        max_output = int(data.get("max_output_chars", DEFAULT_MAX_OUTPUT_CHARS))
        if max_output <= 0:
            raise MCPConfigError(f"mcp.servers.{name}.max_output_chars must be positive")

        command_value = data.get("command")
        url_value = data.get("url")
        command = str(command_value).strip() if command_value is not None else None
        url = str(url_value).strip() if url_value is not None else None
        if transport == "stdio" and not command:
            raise MCPConfigError(f"stdio MCP server '{name}' requires command")
        if transport == "streamable_http" and not url:
            raise MCPConfigError(f"streamable_http MCP server '{name}' requires url")

        return cls(
            name=name,
            enabled=_as_bool(data.get("enabled"), True),
            transport=transport,
            required=_as_bool(data.get("required"), False),
            tool_timeout_seconds=timeout,
            max_output_chars=max_output,
            command=command,
            args=tuple(raw_args),
            env=_string_mapping(data.get("env"), f"mcp.servers.{name}.env"),
            url=url,
            headers=_string_mapping(data.get("headers"), f"mcp.servers.{name}.headers"),
        )

    def resolved_env(self) -> dict[str, str]:
        return {key: _expand_environment(value) for key, value in self.env.items()}

    def resolved_headers(self) -> dict[str, str]:
        return {key: _expand_environment(value) for key, value in self.headers.items()}

    def redact_secrets(self, value: str) -> str:
        """Remove configured secret values, including ones only known via the environment."""
        redacted = value
        for configured in (*self.env.values(), *self.headers.values()):
            for match in _ENV_REFERENCE.finditer(configured):
                secret = os.environ.get(match.group(1))
                if secret and len(secret) >= 4:
                    redacted = redacted.replace(secret, "***REDACTED***")
        for key, configured in (*self.env.items(), *self.headers.items()):
            normalized = key.lower().replace("-", "_")
            if not any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                continue
            try:
                secret = _expand_environment(configured)
            except MissingEnvironmentVariable:
                continue
            candidates = [secret]
            if secret.lower().startswith("bearer "):
                candidates.append(secret[7:].strip())
            for candidate in candidates:
                if len(candidate) >= 4:
                    redacted = redacted.replace(candidate, "***REDACTED***")
        return redacted


@dataclass(slots=True, frozen=True)
class MCPConfig:
    enabled: bool = False
    servers: tuple[MCPServerConfig, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MCPConfig:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise MCPConfigError("mcp must be an object")
        raw_servers = data.get("servers", {})
        if not isinstance(raw_servers, dict):
            raise MCPConfigError("mcp.servers must be an object")
        return cls(
            enabled=_as_bool(data.get("enabled"), False),
            servers=tuple(
                MCPServerConfig.from_dict(str(name), server)
                for name, server in raw_servers.items()
            ),
        )


@dataclass(slots=True)
class MCPServerStatus:
    name: str
    transport: str
    enabled: bool
    required: bool
    connected: bool = False
    error: str | None = None
    tool_count: int = 0
    discovery_errors: list[str] = field(default_factory=list)


class MCPStartupError(RuntimeError):
    """Raised when a required MCP server cannot start."""


def _sanitize(value: str) -> str:
    return _UNSAFE_NAME.sub("_", value.strip()).strip("_-") or "unnamed"


def _hash_identity(server_name: str, tool_name: str, salt: str = "") -> str:
    return hashlib.sha256(f"{server_name}\0{tool_name}\0{salt}".encode()).hexdigest()[:8]


def build_mcp_tool_name(server_name: str, tool_name: str, occupied: set[str]) -> str:
    """Namespace an MCP tool, adding a stable hash when sanitizing changed it."""
    server, tool = _sanitize(server_name), _sanitize(tool_name)
    candidate = f"mcp__{server}__{tool}"
    unchanged = (
        server == server_name
        and tool == tool_name
        and "__" not in server_name
        and "__" not in tool_name
        and len(candidate) <= MAX_TOOL_NAME_LENGTH
    )
    for counter in range(0 if unchanged else 1, 101):
        suffix = "" if counter == 0 else "_" + _hash_identity(server_name, tool_name, str(counter))
        trimmed = candidate[: MAX_TOOL_NAME_LENGTH - len(suffix)].rstrip("_-")
        if f"{trimmed}{suffix}" not in occupied:
            return f"{trimmed}{suffix}"
    raise ValueError(f"unable to name MCP tool {server_name}/{tool_name}")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_safe(model_dump(mode="json"))
    return str(value)


class MCPTool(Tool):
    """Expose one discovered MCP tool through the local Tool interface."""

    def __init__(
        self,
        *,
        client: Any,
        server_config: MCPServerConfig,
        mcp_tool: Any,
        local_name: str,
    ) -> None:
        self._client = client
        self._config = server_config
        self._remote_name = str(mcp_tool.name)
        self._name = local_name
        raw_description = str(getattr(mcp_tool, "description", "") or "")
        self._description = raw_description[:MAX_DESCRIPTION_CHARS]
        self._parameters = self._normalize_schema(mcp_tool.input_schema)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return copy.deepcopy(self._parameters)

    async def execute(self, **kwargs) -> ToolResult:
        try:
            result = await asyncio.wait_for(
                self._client.call_tool(self._remote_name, dict(kwargs)),
                timeout=self._config.tool_timeout_seconds,
            )
        except TimeoutError:
            return ToolResult(
                success=False,
                error=f"MCP tool timed out after {self._config.tool_timeout_seconds:g}s",
            )
        except InputRequiredRoundsExceededError:
            return ToolResult(success=False, error="MCP tool requested unsupported user input")
        except Exception as exc:
            error = self._config.redact_secrets(redact_text(f"{type(exc).__name__}: {exc}"))
            return ToolResult(success=False, error=f"MCP tool call failed: {error}")

        if str(getattr(result, "result_type", "complete")) != "complete":
            return ToolResult(success=False, error="MCP tool returned an unsupported result type")

        output = self._convert_result(result)
        if bool(getattr(result, "is_error", False)):
            return ToolResult(success=False, error=output or "MCP tool returned an error")
        return ToolResult(success=True, output=output)

    @staticmethod
    def _normalize_schema(schema: Any) -> dict[str, Any]:
        if not isinstance(schema, dict):
            raise ValueError("inputSchema must be a JSON object")
        normalized = copy.deepcopy(schema)
        if normalized.setdefault("type", "object") != "object":
            raise ValueError("inputSchema root type must be object")
        properties = normalized.get("properties")
        if properties is not None and not isinstance(properties, dict):
            raise ValueError("inputSchema.properties must be an object")
        required = normalized.get("required")
        if required is not None and (
            not isinstance(required, list) or not all(isinstance(item, str) for item in required)
        ):
            raise ValueError("inputSchema.required must be a string array")
        json.dumps(normalized)
        return normalized

    def _convert_result(self, result: Any) -> str:
        parts: list[str] = []
        for item in list(getattr(result, "content", []) or []):
            content_type = str(getattr(item, "type", "unknown"))
            if content_type == "text":
                parts.append(str(getattr(item, "text", "")))
            else:
                # Multimodal and resource payloads would blow up model context.
                parts.append(f"[MCP returned unsupported content: {content_type}]")

        structured = getattr(result, "structured_content", None)
        if structured is not None:
            safe = redact_mapping({"structured_content": _json_safe(structured)})["structured_content"]
            parts.append(
                json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )

        output = self._config.redact_secrets(
            redact_text("\n\n".join(part for part in parts if part))
        )
        return output[: self._config.max_output_chars]


class MCPClientFactory:
    """Build connected official SDK clients for the supported transports."""

    async def connect(self, config: MCPServerConfig, stack: AsyncExitStack) -> Any:
        if config.transport == "stdio":
            client = Client(
                StdioServerParameters(
                    command=config.command or "",
                    args=list(config.args),
                    env=config.resolved_env() or None,
                ),
                read_timeout_seconds=config.tool_timeout_seconds,
                input_required_max_rounds=0,
            )
            return await stack.enter_async_context(client)

        http_client = await stack.enter_async_context(
            httpx2.AsyncClient(
                headers=config.resolved_headers() or None,
                follow_redirects=True,
                timeout=httpx2.Timeout(config.tool_timeout_seconds),
            )
        )
        client = Client(
            streamable_http_client(config.url or "", http_client=http_client),
            read_timeout_seconds=config.tool_timeout_seconds,
            input_required_max_rounds=0,
        )
        return await stack.enter_async_context(client)


class MCPManager:
    """Register tools discovered from every enabled MCP server at startup."""

    def __init__(self, config: MCPConfig, registry: Any, factory: MCPClientFactory | None = None) -> None:
        self.config = config
        self.registry = registry
        self.factory = factory or MCPClientFactory()
        self._stack: AsyncExitStack | None = None
        self._statuses: dict[str, MCPServerStatus] = {}

    @property
    def statuses(self) -> tuple[MCPServerStatus, ...]:
        return tuple(self._statuses.values())

    async def start(self) -> None:
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for server in self.config.servers:
            status = MCPServerStatus(
                name=server.name,
                transport=server.transport,
                enabled=self.config.enabled and server.enabled,
                required=server.required,
            )
            self._statuses[server.name] = status
            if not status.enabled:
                continue
            try:
                await self._connect(server, status)
            except Exception as exc:
                status.error = server.redact_secrets(redact_text(f"{type(exc).__name__}: {exc}"))
                if server.required:
                    await self.close()
                    raise MCPStartupError(
                        f"required MCP server '{server.name}' failed: {status.error}"
                    ) from exc

    async def _connect(self, server: MCPServerConfig, status: MCPServerStatus) -> None:
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            client = await self.factory.connect(server, stack)
            tools = await self._list_tools(client)
        except BaseException:
            await stack.aclose()
            raise
        self._stack.push_async_callback(stack.aclose)
        status.connected = True

        occupied = {
            definition.get("function", {}).get("name", "")
            for definition in self.registry.get_definitions()
        }
        for mcp_tool in tools:
            remote_name = str(getattr(mcp_tool, "name", ""))
            if not remote_name:
                status.discovery_errors.append("skipped MCP tool with empty name")
                continue
            try:
                local_name = build_mcp_tool_name(server.name, remote_name, occupied)
                self.registry.register(
                    MCPTool(
                        client=client,
                        server_config=server,
                        mcp_tool=mcp_tool,
                        local_name=local_name,
                    )
                )
            except (ValueError, TypeError) as exc:
                status.discovery_errors.append(f"tool '{remote_name}' skipped: {exc}")
                continue
            occupied.add(local_name)
            status.tool_count += 1

    @staticmethod
    async def _list_tools(client: Any) -> list[Any]:
        tools: list[Any] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            result = await client.list_tools(cursor=cursor)
            if str(getattr(result, "result_type", "complete")) != "complete":
                raise RuntimeError("unsupported MCP tools/list result type")
            tools.extend(list(getattr(result, "tools", []) or []))
            next_cursor = getattr(result, "next_cursor", None)
            if not next_cursor:
                return tools
            if next_cursor in seen:
                raise RuntimeError("MCP tools/list returned a repeated cursor")
            seen.add(next_cursor)
            cursor = str(next_cursor)

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        for status in self._statuses.values():
            status.connected = False
