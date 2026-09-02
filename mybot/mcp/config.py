from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any


DEFAULT_TOOL_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_CHARS = 12_000
SUPPORTED_TRANSPORTS = frozenset({"stdio", "streamable_http"})
SUPPORTED_POLICY_OVERRIDES = frozenset({"allow", "confirm", "block"})
_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "password",
    "token",
    "api_key",
    "apikey",
    "cookie",
    "secret",
)


class MCPConfigError(ValueError):
    pass


class MissingEnvironmentVariable(MCPConfigError):
    def __init__(self, variable: str):
        self.variable = variable
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
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str):
            raise MCPConfigError(f"{field_name}.{key} must be a string")
        result[str(key)] = item
    return result


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
    trust_annotations: bool = False
    tool_timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    tool_policy: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MCPServerConfig:
        if not isinstance(data, dict):
            raise MCPConfigError(f"mcp.servers.{name} must be an object")
        transport = str(data.get("transport", "stdio")).strip().lower()
        if transport not in SUPPORTED_TRANSPORTS:
            raise MCPConfigError(
                f"mcp server '{name}' has unsupported transport '{transport}'"
            )

        raw_args = data.get("args", [])
        if not isinstance(raw_args, list) or not all(
            isinstance(item, str) for item in raw_args
        ):
            raise MCPConfigError(f"mcp.servers.{name}.args must be a string array")

        timeout = float(
            data.get("tool_timeout_seconds", DEFAULT_TOOL_TIMEOUT_SECONDS)
        )
        if timeout <= 0:
            raise MCPConfigError(
                f"mcp.servers.{name}.tool_timeout_seconds must be positive"
            )
        max_output = int(data.get("max_output_chars", DEFAULT_MAX_OUTPUT_CHARS))
        if max_output <= 0:
            raise MCPConfigError(
                f"mcp.servers.{name}.max_output_chars must be positive"
            )

        raw_policy = _string_mapping(
            data.get("tool_policy"),
            f"mcp.servers.{name}.tool_policy",
        )
        policy = {
            tool_name: decision.strip().lower()
            for tool_name, decision in raw_policy.items()
        }
        invalid = {
            decision
            for decision in policy.values()
            if decision not in SUPPORTED_POLICY_OVERRIDES
        }
        if invalid:
            raise MCPConfigError(
                f"mcp server '{name}' has unsupported tool policy decision(s): "
                + ", ".join(sorted(invalid))
            )

        command_value = data.get("command")
        url_value = data.get("url")
        command = str(command_value).strip() if command_value is not None else None
        url = str(url_value).strip() if url_value is not None else None
        if transport == "stdio" and not command:
            raise MCPConfigError(f"stdio MCP server '{name}' requires command")
        if transport == "streamable_http" and not url:
            raise MCPConfigError(
                f"streamable_http MCP server '{name}' requires url"
            )

        return cls(
            name=name,
            enabled=_as_bool(data.get("enabled"), True),
            transport=transport,
            required=_as_bool(data.get("required"), False),
            trust_annotations=_as_bool(
                data.get("trust_annotations"),
                False,
            ),
            tool_timeout_seconds=timeout,
            max_output_chars=max_output,
            command=command,
            args=tuple(raw_args),
            env=_string_mapping(
                data.get("env"),
                f"mcp.servers.{name}.env",
            ),
            url=url,
            headers=_string_mapping(
                data.get("headers"),
                f"mcp.servers.{name}.headers",
            ),
            tool_policy=policy,
        )

    def resolved_env(self) -> dict[str, str]:
        return {key: _expand_environment(value) for key, value in self.env.items()}

    def resolved_headers(self) -> dict[str, str]:
        return {
            key: _expand_environment(value) for key, value in self.headers.items()
        }

    def policy_for(self, external_tool_name: str) -> str | None:
        return self.tool_policy.get(external_tool_name)

    def redact_secrets(self, value: str) -> str:
        redacted = value
        referenced_names = {
            match.group(1)
            for configured in (*self.env.values(), *self.headers.values())
            for match in _ENV_REFERENCE.finditer(configured)
        }
        for name in referenced_names:
            secret = os.environ.get(name)
            if secret and len(secret) >= 4:
                redacted = redacted.replace(secret, "***REDACTED***")
        for key, configured in (*self.env.items(), *self.headers.items()):
            normalized_key = key.lower().replace("-", "_")
            if not any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
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
        servers = tuple(
            MCPServerConfig.from_dict(str(name), server)
            for name, server in raw_servers.items()
        )
        return cls(enabled=_as_bool(data.get("enabled"), False), servers=servers)
