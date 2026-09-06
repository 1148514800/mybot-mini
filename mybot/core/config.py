from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from openai import AsyncOpenAI

from ..guardrails import DEFAULT_APPROVAL_TTL_SECONDS
from ..mcp.config import MCPConfig
from ..storage.checkpoints.models import DEFAULT_RECENT_TASK_TTL_SECONDS


PACKAGE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = PACKAGE_DIR.parent
CONFIG_DIR = PROJECT_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_json_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}

    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in {CONFIG_FILE}: {exc}"
        ) from exc


def _section(data: dict, name: str) -> dict:
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}


def _config_value(data: dict, key: str, default=None):
    """优先从配置文件读取，如果没有则使用默认值。"""
    return data.get(key, default)


def _config_bool(
    data: dict,
    key: str,
    default: bool = False,
) -> bool:
    """优先从配置文件读取布尔值，如果没有则使用默认值。"""
    value = _config_value(data, key, default)

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


_JSON_CONFIG = _load_json_config()

_LLM_CONFIG = _section(_JSON_CONFIG, "llm")
_FEISHU_CONFIG = _section(_JSON_CONFIG, "feishu")
_WORKSPACE_CONFIG = _section(_JSON_CONFIG, "workspace")
_DEBUG_CONFIG = _section(_JSON_CONFIG, "debug")
_TRACING_CONFIG = _section(_JSON_CONFIG, "tracing")
_MCP_CONFIG = _section(_JSON_CONFIG, "mcp")
_BROWSER_RUNTIME_CONFIG = _section(_JSON_CONFIG, "browser_runtime")
_GUARDRAILS_CONFIG = _section(_JSON_CONFIG, "guardrails")
_CHECKPOINT_CONFIG = _section(_JSON_CONFIG, "checkpoint")


def _active_llm_provider() -> str:
    provider = str(_LLM_CONFIG.get("provider", "")).strip()
    if provider:
        return provider

    return ""


def _active_llm_config() -> dict:
    providers = _LLM_CONFIG.get("providers", {})

    if isinstance(providers, dict):
        provider_name = _active_llm_provider()
        provider_config = providers.get(provider_name, {})

        if isinstance(provider_config, dict):
            return provider_config

    return {}


_ACTIVE_LLM_PROVIDER = _active_llm_provider()
_ACTIVE_LLM_CONFIG = _active_llm_config()


def _resolve_workspace_path(raw_value: str | Path) -> Path:
    path = Path(raw_value).expanduser()

    if path.is_absolute():
        return path

    return (PROJECT_DIR / path).resolve()


def _resolve_optional_path(raw_value: str | Path | None) -> Path | None:
    if raw_value is None or not str(raw_value).strip():
        return None
    return _resolve_workspace_path(raw_value)


@dataclass
class FeishuConfig:

    enabled: bool = field(
        default_factory=lambda: _config_bool(
            _FEISHU_CONFIG,
            "enabled",
            False,
        )
    )

    app_id: str = field(
        default_factory=lambda: str(
            _config_value(
                _FEISHU_CONFIG,
                "app_id",
                "",
            )
        ).strip()
    )

    app_secret: str = field(
        default_factory=lambda: str(
            _config_value(
                _FEISHU_CONFIG,
                "app_secret",
                "",
            )
        ).strip()
    )


@dataclass
class GatewayConfig:

    max_concurrent_sessions: int = field(
        default_factory=lambda: int(
            _config_value(_JSON_CONFIG, "max_concurrent_sessions", 4)
        )
    )

    provider: str = field(
        default_factory=lambda: _ACTIVE_LLM_PROVIDER
    )

    model: str = field(
        default_factory=lambda: _config_value(
            _ACTIVE_LLM_CONFIG,
            "model",
            "gpt-4.1-mini",
        )
    )

    rate_limit_retries: int = field(
        default_factory=lambda: int(
            _config_value(
                _LLM_CONFIG or _ACTIVE_LLM_CONFIG,
                "rate_limit_retries",
                2,
            )
        )
    )

    max_react_steps: int = field(
        default_factory=lambda: int(
            _config_value(
                _LLM_CONFIG or _ACTIVE_LLM_CONFIG,
                "max_react_steps",
                10,
            )
        )
    )

    workspace: Path = field(
        default_factory=lambda: _resolve_workspace_path(
            _config_value(
                _WORKSPACE_CONFIG,
                "path",
                PROJECT_DIR / "workspace",
            )
        )
    )

    trace_dir: Path | None = field(
        default_factory=lambda: _resolve_optional_path(
            _config_value(_TRACING_CONFIG, "trace_dir", None)
        )
    )

    api_key: str | None = field(
        default_factory=lambda: _config_value(
            _ACTIVE_LLM_CONFIG,
            "api_key",
            None,
        )
    )

    base_url: str | None = field(
        default_factory=lambda: _config_value(
            _ACTIVE_LLM_CONFIG,
            "base_url",
            None,
        )
    )

    max_completion_tokens: int = field(
        default_factory=lambda: int(
            _config_value(
                _LLM_CONFIG or _ACTIVE_LLM_CONFIG,
                "max_completion_tokens",
                2000,
            )
        )
    )

    request_timeout_seconds: float = field(
        default_factory=lambda: float(
            _config_value(
                _LLM_CONFIG or _ACTIVE_LLM_CONFIG,
                "request_timeout_seconds",
                60,
            )
        )
    )

    browser_max_consecutive_tool_failures: int = field(
        default_factory=lambda: int(
            _config_value(
                _BROWSER_RUNTIME_CONFIG,
                "max_consecutive_tool_failures",
                2,
            )
        )
    )

    browser_max_open_attempts: int = field(
        default_factory=lambda: int(
            _config_value(
                _BROWSER_RUNTIME_CONFIG,
                "max_open_attempts",
                1,
            )
        )
    )

    browser_max_failed_action_retries: int = field(
        default_factory=lambda: int(
            _config_value(
                _BROWSER_RUNTIME_CONFIG,
                "max_failed_action_retries",
                1,
            )
        )
    )

    browser_max_eval_fallbacks: int = field(
        default_factory=lambda: int(
            _config_value(
                _BROWSER_RUNTIME_CONFIG,
                "max_eval_fallbacks",
                1,
            )
        )
    )

    browser_max_recovery_steps: int = field(
        default_factory=lambda: int(
            _config_value(
                _BROWSER_RUNTIME_CONFIG,
                "max_recovery_steps",
                2,
            )
        )
    )

    approval_ttl_seconds: int = field(
        default_factory=lambda: int(
            _config_value(
                _GUARDRAILS_CONFIG,
                "approval_ttl_seconds",
                DEFAULT_APPROVAL_TTL_SECONDS,
            )
        )
    )

    checkpoint_enabled: bool = field(
        default_factory=lambda: _config_bool(
            _CHECKPOINT_CONFIG,
            "enabled",
            True,
        )
    )

    checkpoint_recent_task_ttl_seconds: int = field(
        default_factory=lambda: int(
            _config_value(
                _CHECKPOINT_CONFIG,
                "recent_task_ttl_seconds",
                DEFAULT_RECENT_TASK_TTL_SECONDS,
            )
        )
    )

    max_context_chars: int = field(default_factory=lambda: int(_config_value(_LLM_CONFIG, "max_context_chars", 60000)))
    max_recent_messages: int = field(default_factory=lambda: int(_config_value(_LLM_CONFIG, "max_recent_messages", 12)))
    max_tool_result_chars: int = field(default_factory=lambda: int(_config_value(_LLM_CONFIG, "max_tool_result_chars", 8000)))
    max_memory_chars: int = field(default_factory=lambda: int(_config_value(_LLM_CONFIG, "max_memory_chars", 8000)))

    show_internal_process: bool = field(
        default_factory=lambda: _config_bool(
            _DEBUG_CONFIG,
            "show_internal_process",
            False,
        )
    )

    feishu: FeishuConfig = field(
        default_factory=FeishuConfig
    )

    mcp: MCPConfig = field(
        default_factory=lambda: MCPConfig.from_dict(_MCP_CONFIG)
    )

    def __post_init__(self) -> None:
        try:
            self.request_timeout_seconds = float(self.request_timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "llm.request_timeout_seconds must be a positive number"
            ) from exc
        if self.request_timeout_seconds <= 0:
            raise ValueError(
                "llm.request_timeout_seconds must be greater than 0"
            )
        limits = {
            "browser_runtime.max_open_attempts": self.browser_max_open_attempts,
            "browser_runtime.max_consecutive_tool_failures": (
                self.browser_max_consecutive_tool_failures
            ),
            "browser_runtime.max_failed_action_retries": (
                self.browser_max_failed_action_retries
            ),
            "browser_runtime.max_eval_fallbacks": self.browser_max_eval_fallbacks,
            "browser_runtime.max_recovery_steps": self.browser_max_recovery_steps,
        }
        for name, value in limits.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if (
            isinstance(self.approval_ttl_seconds, bool)
            or not isinstance(self.approval_ttl_seconds, int)
            or self.approval_ttl_seconds <= 0
        ):
            raise ValueError(
                "guardrails.approval_ttl_seconds must be a positive integer"
            )
        if (
            isinstance(self.checkpoint_recent_task_ttl_seconds, bool)
            or not isinstance(self.checkpoint_recent_task_ttl_seconds, int)
            or self.checkpoint_recent_task_ttl_seconds <= 0
        ):
            raise ValueError(
                "checkpoint.recent_task_ttl_seconds must be a positive integer"
            )
        for name, value in {
            "llm.max_context_chars": self.max_context_chars,
            "llm.max_recent_messages": self.max_recent_messages,
            "llm.max_tool_result_chars": self.max_tool_result_chars,
            "llm.max_memory_chars": self.max_memory_chars,
        }.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(self.max_concurrent_sessions, bool)
            or not isinstance(self.max_concurrent_sessions, int)
            or not 1 <= self.max_concurrent_sessions <= 32
        ):
            raise ValueError("max_concurrent_sessions must be an integer from 1 to 32")


def build_client(config: GatewayConfig) -> AsyncOpenAI:
    if not config.api_key:
        raise RuntimeError(
            f"Missing api_key for llm.provider='{config.provider}'. "
            f"Add it to {CONFIG_FILE}."
        )

    client_kwargs: dict[str, object] = {
        "api_key": config.api_key,
        "timeout": config.request_timeout_seconds,
    }

    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    return AsyncOpenAI(**client_kwargs)
