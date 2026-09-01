import unittest

from mybot.tools.result import ToolResult
from mybot.tracing import AgentTracer, replay_trace


class TraceReplayTests(unittest.TestCase):
    def test_replay_renders_ordered_llm_and_tool_timeline(self) -> None:
        tracer = AgentTracer()
        tracer.start_run("read file")
        step = tracer.start_step(1)
        llm = tracer.start_llm_call(
            step_id=step.step_id,
            model="fake",
            provider="fake",
            message_count=1,
        )
        tracer.finish_llm_call(llm, finish_reason="tool_calls")
        tool = tracer.start_tool_call(
            step_id=step.step_id,
            tool_name="read_file",
            arguments={"path": "README.md"},
        )
        tracer.finish_tool_call(tool, ToolResult(success=True, output="ok"))
        tracer.finish_step()
        trace = tracer.finish_run("done")

        replay = replay_trace(trace)

        self.assertIn("STEP 1", replay)
        self.assertIn("LLM -> read_file", replay)
        self.assertIn("TOOL read_file", replay)
        self.assertIn("success=True", replay)


if __name__ == "__main__":
    unittest.main()
