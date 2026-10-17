"""Separate pure routing quality, core success and challenge success; offline only."""
import asyncio
import json
from mybot.evaluation.tool_agent import evaluate as evaluate_agent, Limits
from mybot.evaluation.tool_routing import evaluate as evaluate_routing

MODES=('eager','progressive_hybrid','adaptive_hybrid','adaptive_selective_hybrid')

async def compare():
    return {'mode':'offline','actual_tokens':None,'actual_cost':None,'live_task_success_rate':None,
            'routing':evaluate_routing(),
            'core':await evaluate_agent(modes=MODES),
            'challenge':await evaluate_agent(modes=MODES,case_set='routing',limits=Limits(max_cases=15))}

if __name__=='__main__':print(json.dumps(asyncio.run(compare()),ensure_ascii=False,indent=2))
