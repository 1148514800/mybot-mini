import json
import tempfile
import unittest
from pathlib import Path

from mybot.tracing import (
    AgentTracer,
    load_trace,
    trace_from_dict,
    trace_to_dict,
    trace_to_json,
)


class TraceSerializerTests(unittest.TestCase):
    def completed_trace(self):
        tracer = AgentTracer()
        tracer.start_run("hello", metadata={"source": "unit"})
        step = tracer.start_step(1)
        tracer.finish_step()
        return tracer.finish_run("done")

    def test_trace_dict_and_json_round_trip_nested_models(self) -> None:
        trace = self.completed_trace()

        data = trace_to_dict(trace)
        restored = trace_from_dict(json.loads(trace_to_json(trace)))

        self.assertEqual(data["run_id"], trace.run_id)
        self.assertEqual(restored.run_id, trace.run_id)
        self.assertEqual(restored.steps[0].step_id, trace.steps[0].step_id)

    def test_trace_is_only_persisted_when_directory_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            memory_only = AgentTracer()
            memory_only.start_run("memory")
            memory_only.finish_run("done")
            self.assertEqual(list(root.iterdir()), [])

            persisted = AgentTracer(trace_dir=root / "runs")
            trace = persisted.start_run("persist")
            persisted.finish_run("done")
            path = root / "runs" / f"{trace.run_id}.json"

            self.assertTrue(path.is_file())
            self.assertEqual(load_trace(path).final_output, "done")

    def test_legacy_trace_without_task_fields_still_loads(self) -> None:
        data = trace_to_dict(self.completed_trace())
        data.pop("task_id")
        data.pop("task_status")

        restored = trace_from_dict(data)

        self.assertIsNone(restored.task_id)
        self.assertIsNone(restored.task_status)


if __name__ == "__main__":
    unittest.main()
