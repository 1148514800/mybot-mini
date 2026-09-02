from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

from mcp import InputRequiredRoundsExceededError

from ..tools.base import Tool
from ..tools.result import ToolResult
from ..tracing import redact_mapping, redact_text
from .config import MCPServerConfig


MAX_DESCRIPTION_CHARS = 2_000


class UnsupportedMCPSchema(ValueError):
    pass


def normalize_input_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise UnsupportedMCPSchema("inputSchema must be a JSON object")
    normalized = copy.deepcopy(schema)
    schema_type = normalized.get("type")
    if schema_type is None:
        normalized["type"] = "object"
    elif schema_type != "object":
        raise UnsupportedMCPSchema("inputSchema root type must be object")
    properties = normalized.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise UnsupportedMCPSchema("inputSchema.properties must be an object")
    required = normalized.get("required")
    if required is not None and (
        not isinstance(required, list)
        or not all(isinstance(item, str) for item in required)
    ):
        raise UnsupportedMCPSchema("inputSchema.required must be a string array")
    try:
        json.dumps(normalized)
    except (TypeError, ValueError) as exc:
        raise UnsupportedMCPSchema(
            f"inputSchema is not JSON serializable: {exc}"
        ) from exc
    return normalized


def _annotation_value(annotations: Any, name: str) -> bool | None:
    if annotations is None:
        return None
    value = getattr(annotations, name, None)
    return value if isinstance(value, bool) else None


def annotation_metadata(annotations: Any) -> dict[str, bool]:
    return {
        name: value
        for name in (
            "read_only_hint",
            "destructive_hint",
            "idempotent_hint",
            "open_world_hint",
        )
        if (value := _annotation_value(annotations, name)) is not None
    }


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


class MCPToolAdapter(Tool):
    def __init__(
        self,
        *,
        client: Any,
        server_config: MCPServerConfig,
        mcp_tool: Any,
        local_name: str,
        protocol_version: str | None,
    ) -> None:
        self._client = client
        self._server_config = server_config
        self._mcp_tool_name = str(mcp_tool.name)
        self._name = local_name
        raw_description = str(getattr(mcp_tool, "description", "") or "")
        self._description = raw_description[:MAX_DESCRIPTION_CHARS]
        self._parameters = normalize_input_schema(mcp_tool.input_schema)
        self._metadata: dict[str, Any] = {
            "tool_source": "mcp",
            "mcp_server": server_config.name,
            "mcp_tool_name": self._mcp_tool_name,
            "local_tool_name": local_name,
            "transport": server_config.transport,
            "protocol_version": protocol_version,
            "trust_annotations": server_config.trust_annotations,
            **annotation_metadata(getattr(mcp_tool, "annotations", None)),
        }
        override = server_config.policy_for(self._mcp_tool_name)
        if override:
            self._metadata["mcp_policy_override"] = override
        if len(raw_description) > MAX_DESCRIPTION_CHARS:
            self._metadata["description_truncated"] = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return copy.deepcopy(self._parameters)

    @property
    def runtime_metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    async def execute(self, **kwargs) -> ToolResult:
        try:
            result = await asyncio.wait_for(
                self._client.call_tool(self._mcp_tool_name, dict(kwargs)),
                timeout=self._server_config.tool_timeout_seconds,
            )
        except TimeoutError:
            return ToolResult(
                success=False,
                error=(
                    f"MCP tool timed out after "
                    f"{self._server_config.tool_timeout_seconds:g}s"
                ),
                metadata={**self.runtime_metadata, "timed_out": True},
            )
        except InputRequiredRoundsExceededError:
            return ToolResult(
                success=False,
                error="Unsupported MCP tool result type 'input_required' in Phase 4",
                metadata={
                    **self.runtime_metadata,
                    "unsupported_result_type": "input_required",
                },
            )
        except Exception as exc:
            error = self._server_config.redact_secrets(
                redact_text(f"{type(exc).__name__}: {exc}")
            )
            return ToolResult(
                success=False,
                error=f"MCP tool call failed: {error}",
                metadata=self.runtime_metadata,
            )

        result_type = str(getattr(result, "result_type", "complete"))
        if result_type != "complete":
            return ToolResult(
                success=False,
                error=(
                    f"Unsupported MCP tool result type '{result_type}' in Phase 4"
                ),
                metadata={
                    **self.runtime_metadata,
                    "unsupported_result_type": result_type,
                },
            )

        output, result_metadata = self._convert_result(result)
        metadata = {**self.runtime_metadata, **result_metadata}
        if bool(getattr(result, "is_error", False)):
            return ToolResult(
                success=False,
                error=output or "MCP tool returned an error",
                metadata=metadata,
            )
        return ToolResult(success=True, output=output, metadata=metadata)

    def _convert_result(self, result: Any) -> tuple[str, dict[str, Any]]:
        parts: list[str] = []
        content_types: list[str] = []
        unsupported_count = 0
        for item in list(getattr(result, "content", []) or []):
            content_type = str(getattr(item, "type", "unknown"))
            content_types.append(content_type)
            if content_type == "text":
                parts.append(str(getattr(item, "text", "")))
            elif content_type == "image":
                unsupported_count += 1
                parts.append(
                    "[MCP returned image content; multimodal MCP result is not "
                    "supported in Phase 4]"
                )
            elif content_type == "audio":
                unsupported_count += 1
                parts.append(
                    "[MCP returned audio content; multimodal MCP result is not "
                    "supported in Phase 4]"
                )
            elif content_type in {"resource", "resource_link"}:
                unsupported_count += 1
                parts.append(
                    "[MCP returned resource content; MCP resources are not "
                    "supported in Phase 4]"
                )
            else:
                unsupported_count += 1
                parts.append(
                    f"[MCP returned unsupported content type: {content_type}]"
                )

        structured = getattr(result, "structured_content", None)
        if structured is not None:
            safe_structured = redact_mapping(
                {"structured_content": _json_safe(structured)}
            )["structured_content"]
            serialized = json.dumps(
                safe_structured,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            label = f"structuredContent={serialized}" if parts else serialized
            parts.append(label)

        output = self._server_config.redact_secrets(
            redact_text("\n\n".join(part for part in parts if part))
        )
        truncated = len(output) > self._server_config.max_output_chars
        if truncated:
            output = output[: self._server_config.max_output_chars]
        metadata: dict[str, Any] = {
            "content_types": content_types,
            "result_type": "complete",
        }
        if unsupported_count:
            metadata["unsupported_content_count"] = unsupported_count
        if truncated:
            metadata["output_truncated"] = True
            metadata["original_output_chars"] = len("\n\n".join(parts))
        return output, metadata
