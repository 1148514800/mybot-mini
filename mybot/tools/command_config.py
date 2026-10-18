"""Trusted host configuration only. Never accepted as command tool arguments."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSettings:
    mode: str = 'off'
    timeout_seconds: int = 30
    max_output_bytes: int = 32768


def validate_command(value, *, coding_enabled, patch_mode):
    if not isinstance(value, dict) or set(value) - {'mode', 'timeout_seconds', 'max_output_bytes'}:
        raise ValueError('coding.command contains unknown fields or is not an object')
    settings = CommandSettings(**value)
    if type(settings.mode) is not str or settings.mode not in ('off', 'host_confirm', 'macos_readonly'):
        raise ValueError('invalid coding.command.mode')
    for name, low, high in [('timeout_seconds', 1, 60), ('max_output_bytes', 4096, 131072)]:
        val = getattr(settings, name)
        if type(val) is not int or not low <= val <= high:
            raise ValueError('invalid coding.command.' + name)
    if settings.mode != 'off' and coding_enabled is not True:
        raise ValueError('coding.command requires coding.enabled=true')
    if settings.mode == 'host_confirm' and patch_mode != 'write':
        raise ValueError('host_confirm requires coding.patch_mode=write')
    return settings
