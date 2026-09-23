"""Local configuration loaded from config/config.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from openai import AsyncOpenAI

from .mcp import MCPConfig


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
CONFIG_FILE = PROJECT_DIR / "config" / "config.json"


def _load_json_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {CONFIG_FILE}: {exc}") from exc


def _section(name: str) -> dict:
    value = _CONFIG.get(name, {})
    return value if isinstance(value, dict) else {}


_CONFIG = _load_json_config()
_LLM = _section("llm")
_DEBUG = _section("debug")
_TRACING = _section("tracing")

_PROVIDER = str(_LLM.get("provider", "")).strip()
_PROVIDERS = _LLM.get("providers", {})
_PROVIDER_CONFIG = _PROVIDERS.get(_PROVIDER, {}) if isinstance(_PROVIDERS, dict) else {}
if not isinstance(_PROVIDER_CONFIG, dict):
    _PROVIDER_CONFIG = {}


def _llm_value(key: str, default):
    """Read a key from the llm section, falling back to the active provider."""
    return (_LLM or _PROVIDER_CONFIG).get(key, default)


def _resolve_path(raw_value) -> Path:
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else (PROJECT_DIR / path).resolve()


def _resolve_optional_path(raw_value) -> Path | None:
    return None if raw_value is None else _resolve_path(raw_value)


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class GatewayConfig:
    provider: str = _PROVIDER
    model: str = field(default_factory=lambda: _PROVIDER_CONFIG.get("model", "gpt-4.1-mini"))
    api_key: str | None = _PROVIDER_CONFIG.get("api_key")
    base_url: str | None = _PROVIDER_CONFIG.get("base_url")
    rate_limit_retries: int = field(default_factory=lambda: int(_llm_value("rate_limit_retries", 2)))
    max_react_steps: int = field(default_factory=lambda: int(_llm_value("max_react_steps", 10)))
    max_completion_tokens: int = field(default_factory=lambda: int(_llm_value("max_completion_tokens", 2000)))
    request_timeout_seconds: float = field(default_factory=lambda: float(_llm_value("request_timeout_seconds", 60)))
    workspace: Path = field(
        default_factory=lambda: _resolve_path(_section("workspace").get("path", PROJECT_DIR / "workspace"))
    )
    trace_dir: Path | None = field(
        default_factory=lambda: _resolve_optional_path(_TRACING.get("trace_dir"))
    )
    show_internal_process: bool = field(
        default_factory=lambda: _as_bool(_DEBUG.get("show_internal_process"), False)
    )
    mcp: MCPConfig = field(default_factory=lambda: MCPConfig.from_dict(_section("mcp")))

    def __post_init__(self) -> None:
        self.request_timeout_seconds = float(self.request_timeout_seconds)
        self.workspace = Path(self.workspace)


def build_client(config: GatewayConfig) -> AsyncOpenAI:
    if not config.api_key:
        raise RuntimeError(
            f"Missing api_key for llm.provider='{config.provider}'. "
            f"Add it to {CONFIG_FILE}."
        )
    kwargs: dict[str, object] = {
        "api_key": config.api_key,
        "timeout": config.request_timeout_seconds,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return AsyncOpenAI(**kwargs)
