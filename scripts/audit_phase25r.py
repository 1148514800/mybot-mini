"""Read-only reconstruction of the immutable Phase25 cohort. No model clients."""
import hashlib
import json
from pathlib import Path
from mybot.evaluation.coding_campaign import inventory, strict_success, file_sha


def audit(root=None):
    root = Path(root) if root else Path(__file__).resolve().parents[1]/'docs/reports/phase-25'
    index = json.loads((root/'evidence-sha256.json').read_bytes())['files']
    for name, digest in index.items():
        if file_sha(root/name) != digest:
            raise ValueError('historical_evidence_changed')
    manifest, rows = inventory(root/'standard')
    cancellations = []
    for row in rows:
        report = row['report']
        value = report['results'][0]
        if value['agent_state'] == 'cancelled':
            folder = root/'standard/runs'/row['run_id']
            cancellations.append(dict(run_id=row['run_id'],
                started_at=json.loads((folder/'started.json').read_bytes())['at'],
                finished_at=json.loads((folder/'finished.json').read_bytes())['at'],
                raw_sha256=file_sha(folder/'raw.json'), runtime_error=value['runtime_error'],
                stop_reason=value['controller']['stop_reason'],
                controller_command_attempts=value['controller']['command_attempts'],
                completed_commands=value['metrics']['command_attempts'],
                committed_patches=value['metrics']['committed_patches'],
                journal_mismatch=value['judge']['journal_attribution_mismatch'],
                changed_paths=value['judge']['changed_files'],
                hidden_state=value['judge']['judge_state']))
    external=json.loads((root/'phase25-external-v2/raw.json').read_bytes())
    return dict(historical_campaign_id=manifest['campaign_id'],
        frozen_harness_sha=manifest['frozen']['benchmark_harness_commit'],
        config_sha256=manifest['config_sha256'], historical_files_verified=len(index),
        denominator=len(rows), strict_successes=sum(strict_success(r['report']) for r in rows),
        agent_verified=sum(r['report']['results'][0]['agent_state']=='verified' for r in rows),
        judge_hidden_pass=sum(r['report']['results'][0]['judge']['judge_state']=='hidden_pass' for r in rows),
        judge_repair_success=sum(r['report']['results'][0]['judge']['verified_repair_success'] for r in rows),
        cancelled_runs=len(cancellations), journal_mismatch_files=sum(r['journal_mismatch'] for r in cancellations),
        cancellations=cancellations,
        external=dict(requests=external['metrics']['llm_requests'], responses=sum(e['event']=='llm_response' for e in external['trace']),
            stop_reason=external['controller']['stop_reason'], committed_patches=external['metrics']['committed_patches'],
            agent_test_runs=external['metrics']['real_test_runs'], raw_sha256=file_sha(root/'phase25-external-v2/raw.json')),
        limits_of_evidence=['Historical metadata lacks approval stack and input-read receipts; approval wait attribution combines operator incident record and code/command counters.',
            'The 26 mismatches are cumulative file occurrences, not 26 distinct paths or reconstructed ownership hashes.',
            'No new live cohort; offline fixes do not establish a model success-rate improvement.'])


if __name__ == '__main__':
    print(json.dumps(audit(),ensure_ascii=False,indent=2))
