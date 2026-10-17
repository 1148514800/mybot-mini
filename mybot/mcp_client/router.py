"""One local initial visibility decision. No model, MCP I/O, evaluation data or authorization."""
from dataclasses import dataclass
import time


MAX_ROUTING_INPUT_CHARS = 4096


@dataclass(frozen=True)
class RoutingDecision:
    routing_strategy: str
    selected_tool_names: tuple[str, ...]
    selected_schema_chars: int
    candidate_count: int
    fallback_reason: str | None
    catalog_tool_count: int
    routing_overhead_ms: float

    def diagnostics(self):
        # No query, names, descriptions, arguments, messages or credentials.
        return {'routing_strategy':self.routing_strategy,'catalog_tool_count':self.catalog_tool_count,
                'preselection_count':len(self.selected_tool_names),'preselected_schema_chars':self.selected_schema_chars,
                'candidate_count':self.candidate_count,'fallback_reason':self.fallback_reason,
                'manual_fallback_used':self.routing_strategy=='manual_fallback','routing_overhead_ms':self.routing_overhead_ms}


class AdaptiveToolRouter:
    def __init__(self, catalog):
        self.catalog = catalog

    def route(self, user_input, *, messages, turns, plan, context_manager):
        from ..agent.context_manager import ContextBudgetError
        started = time.perf_counter()
        catalog = self.catalog
        config = catalog.config
        base_names = catalog.visible_names() - catalog.active

        def fits(names):
            definitions = catalog.registry.get_definitions(base_names | set(names)) or None
            # Original read-only request projection: canonical messages/turns/plan stay intact.
            context_manager.prepare(messages, definitions, turns, plan)

        def decision(strategy, names=(), candidates=0, reason=None):
            return RoutingDecision(strategy,tuple(names),catalog.schema_chars(names),candidates,reason,
                                   len(catalog.entries),(time.perf_counter()-started)*1000)

        fits(())  # Preserve ContextBudgetError if even the base request is impossible.
        if not catalog.entries:
            return decision('no_mcp_tools')
        if not isinstance(user_input,str):
            return decision('manual_fallback',reason='invalid_input')
        if len(user_input)>MAX_ROUTING_INPUT_CHARS:
            return decision('manual_fallback',reason='input_length_limit')
        if not user_input.strip() or any(not c.isprintable() and c not in '\n\r\t' for c in user_input):
            return decision('manual_fallback',reason='invalid_input')

        all_names = tuple(catalog.entries)
        reason = None
        if 0 < len(all_names) <= config.get('eager_tool_threshold',4):
            if len(all_names)>config['max_active_tools']:
                reason = 'small_eager_tool_limit'
            elif catalog.schema_chars(all_names)>config['max_active_schema_chars']:
                reason = 'small_eager_schema_limit'
            else:
                try: fits(all_names)
                except ContextBudgetError: reason = 'small_eager_context_limit'
                else: return decision('small_eager',all_names,len(all_names))

        ranked = catalog.ranked_names(user_input)  # Same fixed index and positive scores as search.
        if not ranked:
            return decision('manual_fallback',reason='no_positive_candidates')
        selected = []
        limit = min(config.get('preselect_limit',3),config['max_active_tools'])
        for name in ranked:
            if len(selected)>=limit: break
            proposed = [*selected,name]
            if catalog.schema_chars(proposed)>config['max_active_schema_chars']:
                reason = 'schema_budget_limited'
                continue  # Skip oversized candidates; never evict a higher-ranked accepted tool.
            try: fits(proposed)
            except ContextBudgetError:
                reason = 'context_budget_limited'
                continue
            selected = proposed
        if not selected:
            return decision('manual_fallback',candidates=len(ranked),reason=reason or 'no_feasible_candidates')
        return decision('ranked_preselect',selected,len(ranked),reason)
