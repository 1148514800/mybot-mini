from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from ..mcp.config import MCPConfig


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


def build_client(config: GatewayConfig) -> OpenAI:
    if not config.api_key:
        raise RuntimeError(
            f"Missing api_key for llm.provider='{config.provider}'. "
            f"Add it to {CONFIG_FILE}."
        )

    client_kwargs: dict[str, str] = {
        "api_key": config.api_key
    }

    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    return OpenAI(**client_kwargs)
