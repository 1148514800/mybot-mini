"""Explicit configuration parsing shared by CLI, Web and read-only checks."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
CONFIG_FILE = PROJECT_DIR / "config/config.json"


class ConfigError(ValueError):
    def __init__(self, code, *, line=None, column=None):
        self.result = dict(ok=False, error_type=code)
        if code.startswith('MIGRATION_REQUIRED_'):
            self.result['hint'] = 'Run python -m scripts.migrate_config_v2 --config PATH --dry-run; session data migration is separate.'
        if line is not None:
            self.result.update(line=line, column=column)
        super().__init__(code)


def read_config(path):
    def constant(_):
        tokens = re.finditer(r'"(?:[^"\\]|\\.)*"|(?P<bad>-?Infinity|NaN)', text)
        position = next(m.start() for m in tokens if m.group('bad'))
        raise json.JSONDecodeError('invalid_json_constant', text, position)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        text = Path(path).read_text(encoding='utf-8')
        document = json.loads(text,
                              parse_constant=constant, object_pairs_hook=pairs)
    except json.JSONDecodeError as exc:
        raise ConfigError('CONFIG_JSON_INVALID', line=exc.lineno, column=exc.colno) from None
    except FileNotFoundError:
        raise ConfigError('CONFIG_NOT_FOUND') from None
    except (OSError, UnicodeError):
        raise ConfigError('CONFIG_UNREADABLE') from None
    except ValueError:
        raise ConfigError('CONFIG_JSON_INVALID') from None
    if type(document) is not dict:
        raise ConfigError('CONFIG_ROOT_INVALID')
    return document


def provider_order(default, providers):
    """JSON declaration order, rotated to the default; no client construction."""
    if not isinstance(providers, dict) or any(not isinstance(n,str) or not n for n in providers):
        raise ValueError('invalid_provider_configuration')
    names = list(providers)
    if default in names:
        start = names.index(default)
        names = names[start:] + names[:start]
    return names


def check_providers(document):
    llm = document.get('llm', {})
    if type(llm) is not dict:
        raise ConfigError('LLM_CONFIG_INVALID')
    providers, default = llm.get('providers'), llm.get('provider')
    if type(default) is not str or type(providers) is not dict or default not in providers:
        raise ConfigError('DEFAULT_PROVIDER_MISSING')
    try:
        names = provider_order(default, providers)
        for name in names:
            validate_provider(providers[name])
    except (ValueError, TypeError):
        raise ConfigError('PROVIDER_FIELDS_INVALID') from None
    return names


def validate_provider(raw):
    if (type(raw) is not dict or any(type(raw.get(k)) is not str or not raw[k].strip()
            for k in ('api_key', 'base_url', 'model')) or raw['api_key'].startswith('YOUR_')):
        raise ValueError('invalid_provider_configuration')
    url = urlsplit(raw['base_url'])
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
            or url.fragment or url.port is not None and not 1 <= url.port <= 65535
            or any(ord(c) < 33 for c in raw['base_url']) or raw['api_key'] != raw['api_key'].strip()):
        raise ValueError('invalid_provider_configuration')


def _resolve_path(value):
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_DIR / path).resolve()


@dataclass
class GatewayConfig:
    web_streaming: bool = field(default=False, kw_only=True)
    web_steer: bool = field(default=False, kw_only=True)
    coding_task_contract: bool = field(default=True, kw_only=True)
    coding_enabled: bool = False
    coding_patch_mode: str = 'off'
    coding_preview_receipt: bool = field(default=False, kw_only=True)
    coding_command: dict = field(default_factory=dict)
    coding_autonomy: dict = field(default_factory=dict)
    coding_git_workflow: dict = field(default_factory=dict)
    mcp_enabled: bool = False
    mcp_servers: dict = field(default_factory=dict)
    mcp_discovery: dict = field(default_factory=dict)
    skills_enabled: bool = False
    skills_path: Path | str = './skills'
    context_enabled: bool = False
    context_max_chars: int = 40000
    context_recent_turns: int = 2
    context_summary_max_chars: int = 1500
    context_tool_result_max_chars: int = 4000
    context_token_budget: dict = field(default_factory=dict, kw_only=True)
    context_compaction: dict = field(default_factory=dict, kw_only=True)
    debug: bool = False
    session_backend: str = field(default='memory', kw_only=True)
    session_event_path: Path | str = field(default='~/.mybot-mini/events.sqlite3', kw_only=True)
    session_event_limits: dict = field(default_factory=dict, kw_only=True)
    session_max_turns: int = 6
    provider: str = ''
    providers: dict = field(default_factory=dict, repr=False, kw_only=True)
    model: str = 'gpt-4.1-mini'
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = field(default=None, repr=False)
    max_react_steps: int = 10
    max_completion_tokens: int = 2000
    request_timeout_seconds: float = 60
    workspace: Path = field(default_factory=lambda: PROJECT_DIR / 'workspace')

    @property
    def storage_backend(self):
        return self.session_backend

    def __post_init__(self) -> None:
        if type(self.web_streaming) is not bool or type(self.web_steer) is not bool:raise ValueError('web streaming/steer enabled must be boolean')
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
        if self.session_backend not in ('memory', 'event_sqlite'):
            raise ValueError('session.backend must be memory or event_sqlite')
        if not isinstance(self.session_event_path,(str,Path)) or not str(self.session_event_path).strip():raise ValueError('session.event_path')
        self.session_event_path = Path(self.session_event_path).expanduser()
        if not self.session_event_path.is_absolute():self.session_event_path = PROJECT_DIR / self.session_event_path
        from .storage.event_store import limits
        self.session_event_limits = limits(self.session_event_limits)
        self.request_timeout_seconds = float(self.request_timeout_seconds)
        self.workspace = _resolve_path(self.workspace)

def config_from_document(document, *, workspace=None):
    """Validate once, without constructing clients or executing project code."""
    if type(document) is not dict:
        raise ConfigError('CONFIG_ROOT_INVALID')
    sections = ('coding', 'context', 'session', 'skills', 'mcp', 'web', 'workspace', 'llm')
    if set(document) - {*sections, 'debug'}:
        raise ConfigError('CONFIG_UNKNOWN_FIELDS')
    if any(type(document.get(name, {})) is not dict for name in sections):
        raise ConfigError('CONFIG_SECTION_INVALID')
    coding, session, context = (document.get(name, {}) for name in ('coding', 'session', 'context'))
    if 'file_access' in coding:
        raise ConfigError('MIGRATION_REQUIRED_CODING_FILE_ACCESS')
    if 'persist' in session or 'path' in session or session.get('backend') == 'legacy_json':
        raise ConfigError('MIGRATION_REQUIRED_SESSION_JSON')
    if isinstance(context.get('token_budget'), dict) and context['token_budget'].get('mode') == 'legacy_chars':
        raise ConfigError('MIGRATION_REQUIRED_TOKEN_BUDGET')
    check_providers(document)
    values = {}
    try:
        for section in ('coding', 'context', 'session', 'skills', 'mcp'):
            for key, value in document.get(section, {}).items():
                target = section + '_' + key
                if target not in GatewayConfig.__dataclass_fields__:
                    raise ValueError('unknown field')
                values[target] = deepcopy(value)
        web = document.get('web', {})
        if set(web) - {'streaming', 'steer'}:
            raise ValueError('unknown web field')
        for name, value in web.items():
            if type(value) is not dict or set(value) - {'enabled'}:
                raise ValueError('invalid web field')
            values['web_' + name] = value.get('enabled', False)
        llm = document['llm']
        values.update(provider=llm['provider'], providers=deepcopy(llm['providers']))
        selected = llm['providers'][llm['provider']]
        for name in ('api_key', 'base_url', 'model'):
            values[name] = selected[name]
        for name in ('max_react_steps', 'max_completion_tokens', 'request_timeout_seconds'):
            if name in llm or name in selected:
                values[name] = (float if name == 'request_timeout_seconds' else int)(llm.get(name, selected.get(name)))
        values['workspace'] = workspace if workspace is not None else document.get('workspace', {}).get('path', PROJECT_DIR / 'workspace')
        values['debug'] = document.get('debug', False)
        if type(values['debug']) is not bool or set(document.get('workspace', {})) - {'path'}:
            raise ValueError('invalid configuration')
        return GatewayConfig(**values)
    except (ValueError, TypeError, OSError):
        raise ConfigError('CONFIG_VALIDATION_FAILED') from None


def load_config(path=None, *, workspace=None):
    return config_from_document(read_config(CONFIG_FILE if path is None else path), workspace=workspace)


def build_client(config: GatewayConfig):
    from openai import AsyncOpenAI
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
