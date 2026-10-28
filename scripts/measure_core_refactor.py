"""Offline R1 measurements; synthetic response, temporary workspace, no SDK transport."""
import asyncio
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace as N


def imports():
    result = {}
    for module in ('mybot.agent.loop', 'mybot.app', 'mybot.web.runtime', 'mybot.config'):
        code = f'import time; t=time.perf_counter(); import {module}; print(time.perf_counter()-t)'
        samples = [float(subprocess.check_output([sys.executable, '-c', code], text=True)) * 1000 for _ in range(11)]
        result[module] = dict(median_ms=statistics.median(samples), min_ms=min(samples), max_ms=max(samples))
    return result


async def requests():
    from mybot.agent import AgentLoop, ContextBuilder
    from mybot.config import GatewayConfig
    from mybot.tools import build_default_tool_registry
    samples = []
    async def create(**kwargs):
        return N(choices=[N(message=N(content='offline done', tool_calls=None), finish_reason='stop')], usage=None)
    with tempfile.TemporaryDirectory() as folder:
        workspace = Path(folder)
        config = GatewayConfig(workspace=workspace, skills_enabled=False, mcp_enabled=False,
            session_persist=False, session_backend='memory', context_enabled=False, debug=False,
            api_key=None, provider='offline', model='synthetic')
        agent = AgentLoop(N(chat=N(completions=N(create=create))), config,
            build_default_tool_registry(workspace), ContextBuilder(workspace))
        for index in range(210):
            agent.session.clear()
            start = time.perf_counter()
            assert await agent.handle_message('hello') == 'offline done'
            elapsed = (time.perf_counter()-start)*1000
            assert agent.last_runtime_report['physical_requests'] == 1
            if index >= 10: samples.append(elapsed)
        agent.close_history()
    return dict(median_ms=statistics.median(samples), min_ms=min(samples), max_ms=max(samples), samples=len(samples))


if __name__ == '__main__':
    files = sorted(Path('mybot').rglob('*.py'))
    print(json.dumps(dict(python=platform.python_version(), platform=platform.platform(),
        python_files=len(files), production_lines=sum(len(p.read_text().splitlines()) for p in files),
        loop_lines=len(Path('mybot/agent/loop.py').read_text().splitlines()),
        imports=imports(), request=asyncio.run(requests())), indent=2))
