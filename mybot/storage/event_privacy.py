"""Bounded local history text; never accepts raw tool/request/SDK structures."""
import os
import re
from ..mcp_client.approval import CREDENTIAL


def safe_text(value,secrets=(),*,max_bytes=24000):
    if type(value) is not str:raise ValueError('history_text')
    result=value
    for secret in secrets:
        if isinstance(secret,str) and len(secret)>=6:result=result.replace(secret,'[已隐藏]')
    result=CREDENTIAL.sub('[已隐藏]',result)
    result=re.sub(r'(?i)((?:api[_-]?key|password|passwd|secret|authorization|access[_-]?token|oauth[_-]?token|receipt|nonce)\s*[:=]\s*)[^\n,;]+',r'\1[已隐藏]',result)
    result=re.sub(r'(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])','[摘要已隐藏]',result)
    result=re.sub(r'/(?:Users|Volumes|home|private/var|tmp)/[^\s"\'<>]+','[本地路径已隐藏]',result)
    # A conservative JSON byte budget also bounds escaped controls/Unicode.
    import json
    truncated=False
    while len(json.dumps(result,ensure_ascii=True).encode())>max_bytes:
        result=result[:max(0,len(result)*3//4)];truncated=True
    if truncated:result+='\n[历史文本因存储预算截断，不代表完整回复]'
    return result,truncated


def configured_secrets(config):
    from ..config import _section
    values=[config.api_key]
    providers=_section('llm').get('providers',{})
    for provider in (providers.values() if isinstance(providers,dict) else ()):
        if isinstance(provider,dict):values.append(provider.get('api_key'))
    for server in config.mcp_servers.values():
        auth=server.get('auth',{})
        if isinstance(auth,dict) and auth.get('token_env'):values.append(os.environ.get(auth['token_env']))
    return tuple(v for v in values if isinstance(v,str) and v)
