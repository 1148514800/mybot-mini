"""Request-view measurements; estimates are never provider billing or exact tokens."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict


class ContextBudgetError(RuntimeError):
    pass


class TokenBudgetError(ContextBudgetError):
    pass


def validate_token_budget(value):
    defaults = {'mode': 'legacy_chars', 'input_limit': 16000, 'model_windows': {}}
    if not isinstance(value, dict) or set(value) - defaults.keys():
        raise ValueError('context.token_budget has unknown fields')
    result = {**defaults, **value}
    if result['mode'] not in ('legacy_chars', 'estimate', 'strict'):
        raise ValueError('context.token_budget.mode must be legacy_chars, estimate or strict')
    if type(result['input_limit']) is not int or not 256 <= result['input_limit'] <= 2_000_000:
        raise ValueError('context.token_budget.input_limit must be 256..2000000')
    windows = result['model_windows']
    if (not isinstance(windows, dict) or len(windows) > 16 or any(
            not isinstance(k, str) or not 1 <= len(k) <= 256 or '/' not in k
            or type(v) is not int or not 512 <= v <= 4_000_000 for k, v in windows.items())):
        raise ValueError('context.token_budget.model_windows requires provider/model integer limits')
    return {**result, 'model_windows': dict(windows)}


@dataclass(frozen=True)
class Measurement:
    request_chars: int
    request_utf8_bytes: int
    estimated_input_tokens: int
    local_tokenizer_tokens: int | None = None
    token_accuracy: str = 'conservative_utf8_estimate_v1'


class TokenCounter:
    """One UTF-8 byte per estimated token + explicit framing/hidden-overhead margin.

    Intentionally pessimistic for ordinary text; NOT a mathematical bound for
    an unknown server encoder. No GPT tokenizer substitution or implicit download.
    No verified coco/coco2 deployment tokenizer mapping is available, so local
    tokenizer count remains unknown and strict mode refuses dispatch.
    """
    @staticmethod
    def measure(request):
        text = json.dumps(request, ensure_ascii=False, allow_nan=False)
        size = len(text.encode('utf-8'))
        overhead = 256 + 32 * len(request.get('messages') or []) + 64 * len(request.get('tools') or [])
        return asdict(Measurement(len(text), size, size + overhead))

    @staticmethod
    def request(config, messages, tools, *, max_tokens=None):
        return dict(model=config.model, messages=messages, tools=tools, temperature=0.1,
                    max_tokens=config.max_completion_tokens if max_tokens is None else max_tokens)

    @staticmethod
    def policy(config, request):
        settings = getattr(config, 'context_token_budget', {'mode':'legacy_chars'})
        mode = settings['mode']
        window = settings.get('model_windows', {}).get(f'{getattr(config,"provider","")}/{request.get("model","")}')
        reserve = request.get('max_tokens', getattr(config, 'max_completion_tokens', 0))
        if type(reserve) is not int or reserve < 1:
            if mode != 'legacy_chars': raise TokenBudgetError('invalid_output_reserve')
            reserve = None
        limit = settings.get('input_limit') if mode != 'legacy_chars' else None
        if window is not None and reserve is not None:
            limit = min(limit, window - reserve) if limit is not None else None
        return dict(context_budget_unit='chars' if mode == 'legacy_chars' else 'estimated_tokens',
                    context_budget_mode=mode, model_window_tokens=window, model_window_status='configured' if window else 'unknown',
                    output_reserved_tokens=reserve, input_token_limit=limit,
                    exact_remaining_tokens=None, tokenizer_status='unverified_for_deployment')

    @classmethod
    def inspect(cls, config, request):
        return {**cls.measure(request), **cls.policy(config, request)}

    @classmethod
    def enforce(cls, config, request):
        result = cls.inspect(config, request)
        if result['context_budget_mode'] == 'strict':
            raise TokenBudgetError('strict_tokenizer_or_window_unverified')
        if result['input_token_limit'] is not None and result['estimated_input_tokens'] > result['input_token_limit']:
            raise TokenBudgetError('estimated_context_budget_exceeded')
        return result
