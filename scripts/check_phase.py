"""Offline regression checks; no API credentials or network calls."""
import asyncio
import contextlib
import io
import tempfile
from pathlib import Path
from types import SimpleNamespace as N
from mybot.agent import AgentLoop, ContextBuilder
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry

async def check(debug):
    with tempfile.TemporaryDirectory() as folder:
        workspace = Path(folder)
        tools = build_default_tool_registry(workspace)
        calls = [N(id="1", function=N(name="write_file", arguments='{"path":"note.txt","content":"PRIVATE_BODY"}'))]
        responses = iter([N(choices=[N(message=N(content=None, tool_calls=calls))], usage=N(total_tokens=42)), N(choices=[N(message=N(content="done", tool_calls=None))], usage=None)])
        async def create(**kwargs):
            if len(kwargs["messages"]) > 2:
                assert kwargs["messages"][-1]["role"] == "tool"
            return next(responses)
        agent = AgentLoop(N(chat=N(completions=N(create=create))), GatewayConfig(debug=debug, workspace=workspace), tools, ContextBuilder(workspace))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert await agent.handle_message("write a note") == "done"
        log = output.getvalue()
        assert workspace.joinpath("note.txt").read_text() == "PRIVATE_BODY"
        if debug:
            assert "[LLM 1]" in log and "[LLM 2]" in log and "tokens=42" in log and "tokens=?" in log
            assert "<12 chars>" in log and "PRIVATE_BODY" not in log and "success=True" in log
        else:
            assert not log
        assert not (await agent._execute("write_file", "{")).success
        assert not (await agent._execute("unknown", "{}")).success
        assert not (await agent._execute("read_file", '{"path":"../outside"}')).success
        assert (await agent._execute("read_file", '{"path":"note.txt"}')).output == "PRIVATE_BODY"

async def main():
    await check(False)
    await check(True)
asyncio.run(main())
print("Offline Phase checks passed: loop, logging, content masking, files, error paths.")
