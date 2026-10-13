"""Local configuration loaded from config/config.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from openai import AsyncOpenAI



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

_PROVIDER = str(_LLM.get("provider", "")).strip()
_PROVIDERS = _LLM.get("providers", {})
_PROVIDER_CONFIG = _PROVIDERS.get(_PROVIDER, {}) if isinstance(_PROVIDERS, dict) else {}
if not isinstance(_PROVIDER_CONFIG, dict):
    _PROVIDER_CONFIG = {}


def _llm_value(key: str, default):
    """Read a key from the llm section, falling back to the active provider."""
    return (_LLM or _PROVIDER_CONFIG).get(key, default)


def _session_value(key: str, default):
    section = _CONFIG.get("session", {})
    if not isinstance(section, dict):
        raise ValueError("session must be a JSON object")
    return section.get(key, default)


def _resolve_path(raw_value) -> Path:
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else (PROJECT_DIR / path).resolve()


@dataclass
class GatewayConfig:
    debug: bool = field(default_factory=lambda: _CONFIG.get("debug", False) is True)
    session_max_turns: int = field(default_factory=lambda: _session_value("max_turns", 6))
    session_persist: bool = field(default_factory=lambda: _session_value("persist", False))
    session_path: Path | str = field(default_factory=lambda: _session_value("path", "./.mybot_state/session.json"))
    provider: str = _PROVIDER
    model: str = field(default_factory=lambda: _PROVIDER_CONFIG.get("model", "gpt-4.1-mini"))
    api_key: str | None = _PROVIDER_CONFIG.get("api_key")
    base_url: str | None = _PROVIDER_CONFIG.get("base_url")
    max_react_steps: int = field(default_factory=lambda: int(_llm_value("max_react_steps", 10)))
    max_completion_tokens: int = field(default_factory=lambda: int(_llm_value("max_completion_tokens", 2000)))
    request_timeout_seconds: float = field(default_factory=lambda: float(_llm_value("request_timeout_seconds", 60)))
    workspace: Path = field(
        default_factory=lambda: _resolve_path(_section("workspace").get("path", PROJECT_DIR / "workspace"))
    )

    def __post_init__(self) -> None:
        if type(self.session_max_turns) is not int or self.session_max_turns < 1:
            raise ValueError("session.max_turns must be a positive integer")
        if type(self.session_persist) is not bool:
            raise ValueError("session.persist must be a boolean")
        if not isinstance(self.session_path, (str, Path)) or not str(self.session_path).strip():
            raise ValueError("session.path must be a non-empty path string")
        self.session_path = _resolve_path(self.session_path)
        self.request_timeout_seconds = float(self.request_timeout_seconds)
        self.workspace = _resolve_path(self.workspace)
        if self.session_persist and self.session_path.is_relative_to(self.workspace):
            raise ValueError("session.path must be outside workspace.path")


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
