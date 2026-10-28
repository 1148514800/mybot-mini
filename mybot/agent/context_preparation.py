"""Request context preparation and compaction using the active turn state."""
from __future__ import annotations

import asyncio
from ..config import GatewayConfig
from .context_manager import ContextBudgetError


async def _prepare_context(self, messages, definitions, turns):
    from ..runtime_accounting import active_config
    from dataclasses import replace
    effective = active_config(self.client, self.config)
    if not isinstance(effective, GatewayConfig):
        effective = replace(self.config, model=effective.model, provider=effective.provider)
    self.context_manager.config = effective
    view, stats = self.context_manager.prepare(messages, definitions, turns, self.plan)
    count = stats['history_turns_omitted']
    if count and self.config.context_compaction['mode']=='semantic':
        controller = self.coding_controller
        async def summarize(request):
            # Keep at least one request for the actual task. The same original
            # Controller and Evaluation client budget gates remain authoritative.
            if controller is not None:
                if controller.settings.max_model_requests-controller.model_requests <= 1:
                    raise ContextBudgetError('compaction_request_reserve')
                if not controller.before_request(None):raise ContextBudgetError('compaction_controller_stopped')
            request_call = self._request_model(request, purpose='compaction')
            if controller is not None:
                return await asyncio.wait_for(request_call, max(.001, controller.remaining_seconds))
            return await request_call
        from ..runtime_accounting import find_gateway
        gateway = find_gateway(self.client)
        secrets = (self.config.api_key, getattr(effective,'api_key',None), *(gateway.secret_values if gateway else ()))
        summary_index=1+len(self.context_manager._pin_messages)+len(self.context_manager.lifecycle_reference)
        base = view[:summary_index] + view[summary_index+int(stats['summary_present']):]
        room = self.context_manager.summary_budget(base, definitions)
        stats['available_summary_budget'] = room
        summary,status = await self.compactor.compact(turns[:count], effective, summarize, secrets,
            available_summary_budget=room,
            fits=lambda item: self.context_manager.accepts(base[:summary_index]+[item]+base[summary_index:], definitions))
        if summary:
            projected = view[:summary_index]+[summary]+view[summary_index+int(stats['summary_present']):]
            if self.context_manager.accepts(projected,definitions):
                view=projected;stats['summary_present']=True;stats['history_turns_summarized']=count;stats['history_turns_summarized_indices']=list(range(1,count+1));stats['history_omitted']=False
            else:
                status='fallback_summary_does_not_fit'
                if self.config.context_compaction['on_failure']=='stop':raise ContextBudgetError(status)
        stats['context_compaction_status']=status
        stats['compaction_input_truncated']=self.compactor.input_truncated
        stats['compaction_evidence']=dict(self.compactor.diagnostics)
    from .token_counter import TokenCounter
    stats.update(TokenCounter.inspect(effective,TokenCounter.request(effective,view,definitions)))
    stats['after']=self.context_manager.count(view,definitions)
    projection=getattr(self.history,'projection_diagnostics',{})
    stats.update(projection)
    if getattr(self,'_pin_history_omitted',0):
        stats['pin_history_turns_removed']=self._pin_history_omitted
    stats['history_information_incomplete']=bool(stats['history_turns_omitted'] or stats.get('pins_omitted') or projection.get('history_projection_incomplete'))
    stats['context_truncated']=bool(stats['context_truncated'] or stats['history_information_incomplete'])
    stats['history_coverage']='unverified' if stats['history_information_incomplete'] else 'full_request_view'
    if self.history.turn_id and stats['history_turns_omitted']:
        status=stats['context_compaction_status']
        allowed=('deterministic','semantic_applied','semantic_reused','semantic_applied_partial','semantic_applied_pruned')
        self.history.event('context.compacted',dict(turn_id=self.history.turn_id,status=status if status in allowed else 'fallback',omitted_turns=stats['history_turns_omitted']))
    self.resources.context = dict(stats)
    self._notify('resource_update', resources=self.resources.snapshot())
    return view,stats


def _route_initial_tools(self, user_input, messages, turns):
    decision = self.router.route(user_input,messages=messages,turns=turns,plan=self.plan,context_manager=self.context_manager)
    self.discovery.apply_preselection(decision.selected_tool_names)
    self.routing_decision = decision
    self.routing_diagnostics = decision.diagnostics()
