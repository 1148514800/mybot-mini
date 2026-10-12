"""Phase 02 offline checks for list_files and its model/tool round trip."""
import asyncio
import contextlib
import io
import tempfile
from pathlib import Path
from types import SimpleNamespace as N
from mybot.agent import AgentLoop, ContextBuilder
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry

async def check_list_files():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "Beta").mkdir()
        (workspace / "alpha.txt").write_text("sample")
        (workspace / "empty").mkdir()
        outside = root / "outside"
        outside.mkdir()
        (workspace / "external").symlink_to(outside, target_is_directory=True)
        (workspace / "internal").symlink_to(workspace / "Beta", target_is_directory=True)
        tools = build_default_tool_registry(workspace)
        definitions = {item["function"]["name"]: item["function"] for item in tools.get_definitions()}
        assert set(definitions) == {"read_file", "write_file", "list_files"}
        schema = definitions["list_files"]["parameters"]
        assert schema["required"] == ["path"] and schema["properties"]["path"]["type"] == "string"
        result = await tools.execute("list_files", {"path": "."})
        assert result.success and result.metadata == {"total": 5, "shown": 5}
        assert result.output.splitlines() == ["[FILE] alpha.txt", "[DIR] Beta", "[DIR] empty", "[DIR] external", "[DIR] internal"]
        empty = await tools.execute("list_files", {"path": "empty"})
        assert empty.success and empty.output == "(empty directory)" and empty.metadata == {"total": 0, "shown": 0}
        assert (await tools.execute("list_files", {"path": str(workspace / "Beta")})).success
        assert (await tools.execute("list_files", {"path": "internal"})).success
        for path in ("missing", "alpha.txt", "../outside", str(outside), "external"):
            assert not (await tools.execute("list_files", {"path": path})).success, path
        many = workspace / "many"
        many.mkdir()
        for number in range(105):
            (many / f"{number:03d}.txt").touch()
        limited = await tools.execute("list_files", {"path": "many"})
        assert limited.success and limited.metadata == {"total": 105, "shown": 100}
        assert len(limited.output.splitlines()) == 100 and limited.output.splitlines()[-1] == "[FILE] 099.txt"
        responses = iter([N(choices=[N(message=N(content=None, tool_calls=[N(id="list-1", function=N(name="list_files", arguments='{"path":"empty"}'))]))], usage=None), N(choices=[N(message=N(content="目录为空", tool_calls=None))], usage=None)])
        requests = []
        async def create(**kwargs):
            requests.append(kwargs)
            if len(requests) == 2:
                assert kwargs["messages"][-1]["role"] == "tool"
                assert kwargs["messages"][-1]["tool_call_id"] == "list-1"
                assert "(empty directory)" in kwargs["messages"][-1]["content"]
            return next(responses)
        agent = AgentLoop(N(chat=N(completions=N(create=create))), GatewayConfig(debug=True, workspace=workspace), tools, ContextBuilder(workspace))
        for arguments in ('{}', '{"path":12}', '{', '[]'):
            assert not (await agent._execute("list_files", arguments)).success
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert await agent.handle_message("列出空目录") == "目录为空"
        assert len(requests) == 2
        assert "[CALL] list_files" in output.getvalue() and "[RESULT] success=True" in output.getvalue()
    print("Phase 02 checks passed: schema, listing, sorting, limits, empty/error paths, symlinks, model round trip.")

if __name__ == "__main__":
    asyncio.run(check_list_files())
