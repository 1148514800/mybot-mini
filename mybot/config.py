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
    return _LLM.get(key, _PROVIDER_CONFIG.get(key, default))


def _session_value(key: str, default):
    section = _CONFIG.get("session", {})
    if not isinstance(section, dict):
        raise ValueError("session must be a JSON object")
    return section.get(key, default)


def _context_value(key: str, default):
    section = _CONFIG.get("context", {})
    if not isinstance(section, dict):
        raise ValueError("context must be a JSON object")
    return section.get(key, default)


def _skills_value(key: str, default):
    section = _CONFIG.get("skills", {})
    if not isinstance(section, dict):
        raise ValueError("skills must be a JSON object")
    return section.get(key, default)


def _coding_value(key='enabled', default=False):
    value = _CONFIG.get('coding', {})
    if not isinstance(value,dict) or set(value)-{'enabled','patch_mode','command','autonomy','git_workflow','preview_receipt','file_access','task_contract'}:
        raise ValueError('coding contains unknown fields (allowed: enabled, patch_mode, preview_receipt, command, autonomy, git_workflow, file_access, task_contract)')
    return value.get(key,default)


def _mcp_value(key: str, default):
    section = _CONFIG.get("mcp", {})
    if not isinstance(section, dict):
        raise ValueError("mcp must be a JSON object")
    if set(section) - {"enabled", "servers", "discovery"}:
        raise ValueError("Unknown mcp configuration fields")
    return section.get(key, default)


def _resolve_path(raw_value) -> Path:
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else (PROJECT_DIR / path).resolve()


def _web_flag(name):
    web=_CONFIG.get('web',{})
    if type(web) is not dict or set(web)-{'streaming','steer'}:raise ValueError('invalid web config')
    value=web.get(name,{})
    if type(value) is not dict or set(value)-{'enabled'} or type(value.get('enabled',False)) is not bool:raise ValueError('invalid web.'+name)
    return value.get('enabled',False)


@dataclass
class GatewayConfig:
    web_streaming: bool = field(default_factory=lambda: _web_flag('streaming'), kw_only=True)
    web_steer: bool = field(default_factory=lambda: _web_flag('steer'), kw_only=True)
    coding_file_access: str = field(default_factory=lambda: _coding_value('file_access', 'read_only'), kw_only=True)
    coding_task_contract: bool = field(default_factory=lambda: _coding_value('task_contract', True), kw_only=True)
    coding_enabled: bool = field(default_factory=_coding_value)
    coding_patch_mode: str = field(default_factory=lambda: _coding_value('patch_mode', 'off'))
    coding_preview_receipt: bool = field(default_factory=lambda: _coding_value('preview_receipt', False), kw_only=True)
    coding_command: dict = field(default_factory=lambda: _coding_value('command', {}))
    coding_autonomy: dict = field(default_factory=lambda: _coding_value('autonomy', {}))
    coding_git_workflow: dict = field(default_factory=lambda: _coding_value('git_workflow', {}))
    mcp_enabled: bool = field(default_factory=lambda: _mcp_value("enabled", False))
    mcp_servers: dict = field(default_factory=lambda: _mcp_value("servers", {}))
    mcp_discovery: dict = field(default_factory=lambda: _mcp_value("discovery", {}))
    skills_enabled: bool = field(default_factory=lambda: _skills_value("enabled", False))
    skills_path: Path | str = field(default_factory=lambda: _skills_value("path", "./skills"))
    context_enabled: bool = field(default_factory=lambda: _context_value("enabled", False))
    context_max_chars: int = field(default_factory=lambda: _context_value("max_chars", 40000))
    context_recent_turns: int = field(default_factory=lambda: _context_value("recent_turns", 2))
    context_summary_max_chars: int = field(default_factory=lambda: _context_value("summary_max_chars", 1500))
    context_tool_result_max_chars: int = field(default_factory=lambda: _context_value("tool_result_max_chars", 4000))
    context_token_budget: dict = field(default_factory=lambda: _context_value('token_budget', {}), kw_only=True)
    context_compaction: dict = field(default_factory=lambda: _context_value('compaction', {}), kw_only=True)
    debug: bool = field(default_factory=lambda: _CONFIG.get("debug", False) is True)
    session_backend: str | None = field(default_factory=lambda: _session_value('backend', None), kw_only=True)
    session_event_path: Path | str = field(default_factory=lambda: _session_value('event_path', '~/.mybot-mini/events.sqlite3'), kw_only=True)
    session_event_limits: dict = field(default_factory=lambda: _session_value('event_limits', {}), kw_only=True)
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

    @property
    def storage_backend(self):
        return self.session_backend if self.session_backend is not None else 'legacy_json' if self.session_persist else 'memory'

    def __post_init__(self) -> None:
        if type(self.web_streaming) is not bool or type(self.web_steer) is not bool:raise ValueError('web streaming/steer enabled must be boolean')
        from .tools.authority import validate_file_access
        validate_file_access(self.coding_file_access, self.coding_patch_mode)
        if type(self.coding_task_contract) is not bool: raise ValueError('coding.task_contract must be boolean')
        if type(self.coding_enabled) is not bool:raise ValueError('coding.enabled must be a boolean')
        if type(self.coding_patch_mode) is not str or self.coding_patch_mode not in ('off', 'preview', 'write'):
            raise ValueError('coding.patch_mode must be off, preview or write')
        if self.coding_patch_mode != 'off' and not self.coding_enabled:
            raise ValueError('coding.patch_mode requires coding.enabled=true')
        if type(self.coding_preview_receipt) is not bool or (self.coding_preview_receipt and self.coding_patch_mode == 'off'):
            raise ValueError('coding.preview_receipt requires an explicit patch mode and boolean')
        from .tools.command_config import validate_command
        from dataclasses import asdict
        self.coding_command = asdict(validate_command(self.coding_command, coding_enabled=self.coding_enabled, patch_mode=self.coding_patch_mode))
        from .agent.coding_controller import validate_autonomy
        self.coding_autonomy = asdict(validate_autonomy(self.coding_autonomy, coding_enabled=self.coding_enabled,
            patch_mode=self.coding_patch_mode, command_mode=self.coding_command['mode']))
        from .agent.git_workflow import validate_git_workflow
        self.coding_git_workflow = asdict(validate_git_workflow(self.coding_git_workflow,
            coding_enabled=self.coding_enabled, patch_mode=self.coding_patch_mode,
            autonomy_enabled=self.coding_autonomy['enabled'], command_mode=self.coding_command['mode'], mcp_enabled=self.mcp_enabled))
        from .mcp_client.config import validate_mcp
        self.mcp_servers = validate_mcp(self.mcp_enabled,self.mcp_servers)
        from .mcp_client.discovery import validate_discovery
        self.mcp_discovery = validate_discovery(self.mcp_discovery)
        if type(self.skills_enabled) is not bool:
            raise ValueError("skills.enabled must be a boolean")
        if not isinstance(self.skills_path, (str, Path)) or not str(self.skills_path).strip():
            raise ValueError("skills.path must be a non-empty path string")
        raw = Path(self.skills_path).expanduser()
        raw = raw if raw.is_absolute() else PROJECT_DIR / raw
        if self.skills_enabled and raw.is_symlink():
            raise ValueError("skills.path cannot be a symlink")
        self.skills_path = raw.resolve()
        from .agent.token_counter import validate_token_budget
        from .agent.context_compactor import validate_compaction
        self.context_token_budget = validate_token_budget(self.context_token_budget)
        self.context_compaction = validate_compaction(self.context_compaction)
        if self.context_token_budget['mode'] != 'legacy_chars' and not self.context_enabled:
            raise ValueError('context.token_budget requires context.enabled=true')
        if self.context_compaction['mode'] == 'semantic' and not self.context_enabled:
            raise ValueError('context.compaction requires context.enabled=true')
        if type(self.context_enabled) is not bool:
            raise ValueError("context.enabled must be a boolean")
        for name, minimum in (("max_chars", 1), ("recent_turns", 0), ("summary_max_chars", 128), ("tool_result_max_chars", 128)):
            value = getattr(self, "context_" + name)
            if type(value) is not int or value < minimum:
                raise ValueError(f"context.{name} must be an integer >= {minimum}")
        if type(self.session_max_turns) is not int or self.session_max_turns < 1:
            raise ValueError("session.max_turns must be a positive integer")
        if type(self.session_persist) is not bool:
            raise ValueError("session.persist must be a boolean")
        if not isinstance(self.session_path, (str, Path)) or not str(self.session_path).strip():
            raise ValueError("session.path must be a non-empty path string")
        resolved_backend=self.storage_backend
        if resolved_backend not in ('memory','legacy_json','event_sqlite') or type(resolved_backend) is not str:
            raise ValueError('session.backend must be memory, legacy_json or event_sqlite')
        if self.session_persist and resolved_backend != 'legacy_json':
            raise ValueError('session.persist conflicts with session.backend')
        self.session_persist = resolved_backend == 'legacy_json'
        if not isinstance(self.session_event_path,(str,Path)) or not str(self.session_event_path).strip():raise ValueError('session.event_path')
        self.session_event_path = Path(self.session_event_path).expanduser()
        if not self.session_event_path.is_absolute():self.session_event_path = PROJECT_DIR / self.session_event_path
        from .storage.event_store import limits
        self.session_event_limits = limits(self.session_event_limits)
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
    if config.coding_autonomy['enabled']:
        kwargs['max_retries'] = 0

    if config.base_url:
        kwargs["base_url"] = config.base_url
    client = AsyncOpenAI(**kwargs)
    # Preserve the established constructor adapter contract, but configure every
    # returned SDK client before it can send requests (including non-Coding CLI).
    client.max_retries = 0
    return client
