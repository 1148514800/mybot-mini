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
        agent = AgentLoop(N(chat=N(completions=N(create=create))), GatewayConfig(skills_enabled=False, context_enabled=False, session_persist=False, debug=debug, workspace=workspace), tools, ContextBuilder(workspace))
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
    if Path(__file__).with_name("check_list_files.py").exists() and build_default_tool_registry(Path.cwd()).has_tool("list_files"):
        from scripts.check_list_files import check_list_files
        await check_list_files()
asyncio.run(main())
if Path(__file__).with_name("check_session.py").exists() and (Path(__file__).resolve().parent.parent / "mybot/agent/session.py").exists():
    from scripts.check_session import check_session
    check_session()
if Path(__file__).with_name("check_planning.py").exists() and (Path(__file__).resolve().parent.parent / "mybot/agent/planning.py").exists():
    from scripts.check_planning import check_planning
    check_planning()
if Path(__file__).with_name("check_persistence.py").exists() and (Path(__file__).resolve().parent.parent / "mybot/storage/session_store.py").exists():
    from scripts.check_persistence import check_persistence
    check_persistence()
if Path(__file__).with_name("check_context.py").exists() and (Path(__file__).resolve().parent.parent / "mybot/agent/context_manager.py").exists():
    from scripts.check_context import check_context
    check_context()
if Path(__file__).with_name("check_skills.py").exists() and (Path(__file__).resolve().parent.parent / "mybot/skills/registry.py").exists():
    from scripts.check_skills import check_skills
    check_skills()
if Path(__file__).with_name("check_evaluation.py").exists() and (Path(__file__).resolve().parent.parent / "mybot/evaluation/runner.py").exists():
    from scripts.check_evaluation import check_evaluation
    check_evaluation()
if Path(__file__).with_name("check_evaluation_v2.py").exists():
    from scripts.check_evaluation_v2 import check_evaluation_v2
    check_evaluation_v2()
if Path(__file__).with_name("check_diagnostics.py").exists():
    from scripts.check_diagnostics import check_diagnostics
    check_diagnostics()
if Path(__file__).with_name("check_mcp.py").exists():
    from scripts.check_mcp import check_mcp
    check_mcp()
if Path(__file__).with_name("check_approval.py").exists():
    from scripts.check_approval import check_approval
    check_approval()
if Path(__file__).with_name("check_mcp_http.py").exists():
    from scripts.check_mcp_http import check_mcp_http
    check_mcp_http()
if Path(__file__).with_name("check_mcp_auth.py").exists():
    from scripts.check_mcp_auth import check_mcp_auth
    check_mcp_auth()
if Path(__file__).with_name("check_mcp_oauth.py").exists():
    from scripts.check_mcp_oauth import check_mcp_oauth
    check_mcp_oauth()
if Path(__file__).with_name("check_tool_discovery.py").exists():
    from scripts.check_tool_discovery import check_tool_discovery
    check_tool_discovery()
if Path(__file__).with_name("check_tool_retrieval.py").exists():
    from scripts.check_tool_retrieval import check_tool_retrieval
    check_tool_retrieval()
if Path(__file__).with_name("check_tool_agent_eval.py").exists():
    from scripts.check_tool_agent_eval import check_tool_agent_eval
    check_tool_agent_eval()
if Path(__file__).with_name("check_adaptive_routing.py").exists():
    from scripts.check_adaptive_routing import check_adaptive_routing
    check_adaptive_routing()
print("Offline Phase checks passed: loop, logging, content masking, files, error paths.")
