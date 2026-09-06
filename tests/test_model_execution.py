import asyncio
import unittest
from types import SimpleNamespace

from mybot.agent.model_execution import ModelExecutor
from mybot.tracing.tracer import AgentTracer


class FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class SlowCompletions:
    async def create(self, **kwargs):
        await asyncio.sleep(60)


class Context:
    def prepare_messages(self, messages, *, task_anchor):
        return messages + [{"role": "system", "content": task_anchor}], {
            "context_chars_before": 12,
            "context_chars_after": 8,
        }


def config(**overrides):
    values = {
        "model": "test-model",
        "provider": "test-provider",
        "max_completion_tokens": 100,
        "rate_limit_retries": 0,
        "request_timeout_seconds": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ModelExecutionTests(unittest.TestCase):
    def test_request_returns_message_and_records_context_and_usage(self):
        message = SimpleNamespace(content=" answer ", tool_calls=None)
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )
        completions = FakeCompletions(response=response)
        tracer = AgentTracer()
        run = tracer.start_run("hello")
        step = tracer.start_step(1)
        executor = ModelExecutor(
            client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
            config=config(),
            context=Context(),
            tracer=tracer,
        )

        result = asyncio.run(
            executor.request(
                [{"role": "user", "content": "hello"}],
                step_id=step.step_id,
                task_anchor="anchor",
                tool_definitions=[{"type": "function"}],
            )
        )
        tracer.finish_step()
        tracer.finish_run(final_output=result.content)

        self.assertEqual(result.content, "answer")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.message, message)
        self.assertEqual(len(completions.calls), 1)
        self.assertEqual(completions.calls[0]["messages"][-1]["content"], "anchor")
        self.assertEqual(run.llm_calls[0].input_tokens, 3)
        self.assertEqual(run.llm_calls[0].output_tokens, 2)
        self.assertEqual(run.llm_calls[0].metadata["context_chars_after"], 8)

    def test_request_timeout_finishes_llm_trace(self):
        tracer = AgentTracer()
        tracer.start_run("hello")
        step = tracer.start_step(1)
        executor = ModelExecutor(
            client=SimpleNamespace(chat=SimpleNamespace(completions=SlowCompletions())),
            config=config(request_timeout_seconds=0.01),
            context=None,
            tracer=tracer,
        )

        result = asyncio.run(executor.request([], step_id=step.step_id))

        self.assertEqual(result.error, "LLM request timeout after 0.01s")
        self.assertEqual(result.error_reason, "llm_timeout")
        self.assertEqual(tracer.get_current_run().llm_calls[0].error, result.error)

    def test_request_without_active_trace_still_calls_model(self):
        message = SimpleNamespace(content="done", tool_calls=None)
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")]
        )
        completions = FakeCompletions(response=response)
        executor = ModelExecutor(
            client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
            config=config(),
            context=None,
            tracer=AgentTracer(),
        )

        result = asyncio.run(executor.request([]))

        self.assertEqual(result.content, "done")
        self.assertEqual(completions.calls[0]["tools"], None)
