# Provider failover smoke acceptance

This is an *independent* test branch based on `d07f64d`. It does not change the frozen Phase25 Campaign, evaluation client, model scores, or credentials.

## Preflight

Ensure local ignored `config/config.json` has `llm.provider="coco"`; `coco.model="deepseek-v4.1-flash"`; `coco2.model="glm-5.3-flash"`; and valid credentials for the provider(s) being contacted. The repository's example config does not include these credentials.

## Offline (no paid requests)

```bash
uv run python -m scripts.check_provider_failover
uv run python -m scripts.check_provider_failover_smoke
uv run python -m scripts.smoke_provider_failover
```

## Opt-in live (may incur fees)

```bash
# Fault injection: no real request to coco; up to 2 real calls to coco2.
uv run python -m scripts.smoke_provider_failover --live --confirm-api-cost --mode forced

# Natural: 1 application-level model request to coco, then to coco2 only on failure.
uv run python -m scripts.smoke_provider_failover --live --confirm-api-cost --mode natural
```

Both modes use a constant, read-only prompt. No agent tools, patches, Campaign case execution, or user data are sent. Model response bodies are not printed. The forced mode verifies sticky provider selection across two requests. The natural mode cannot prove failover if the primary succeeds. The SDK's retries are disabled by the existing failover wrapper.

**Evidence discipline:** Offline success is not live success. Live calls here are a dedicated connectivity smoke test, *not* a Phase25 evaluation or a coding quality score. If live verification fails, keep error type only in console and diagnose privately; do not print API keys or raw provider errors. Do not append results to any frozen Campaign.

Original `codex/provider-failover` remains unchanged. Run the new smoke files in `codex/provider-failover-smoke`.
