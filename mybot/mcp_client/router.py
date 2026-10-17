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

    selection_policy: str = 'legacy'
    evidence_level: str | None = None
    abstained: bool = False
    abstention_reason: str | None = None
    eligible_candidate_count: int = 0
    rejected_weak_count: int = 0
    covered_query_concepts_count: int = 0
    redundant_candidates_skipped: int = 0

    def diagnostics(self):
        # No query, names, descriptions, arguments, messages or credentials.
        return {'routing_strategy':self.routing_strategy,'catalog_tool_count':self.catalog_tool_count,
                'preselection_count':len(self.selected_tool_names),'preselected_schema_chars':self.selected_schema_chars,
                'selection_policy':self.selection_policy,'evidence_level':self.evidence_level,
                'abstained':self.abstained,'abstention_reason':self.abstention_reason,
                'eligible_candidate_count':self.eligible_candidate_count,'rejected_weak_count':self.rejected_weak_count,
                'selected_count':len(self.selected_tool_names),'covered_query_concepts_count':self.covered_query_concepts_count,
                'redundant_candidates_skipped':self.redundant_candidates_skipped,
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

        selective = config.get("selection_policy","legacy") == "selective"

        def decision(strategy, names=(), candidates=0, reason=None, **extra):
            return RoutingDecision(strategy,tuple(names),catalog.schema_chars(names),candidates,reason,
                                   len(catalog.entries),(time.perf_counter()-started)*1000,
                                   selection_policy='selective' if selective else 'legacy',
                                   abstained=not names,abstention_reason=reason if not names else None,**extra)

        fits(())  # Preserve ContextBudgetError if even the base request is impossible.
        if not catalog.entries:
            return decision('no_mcp_tools')
        if not isinstance(user_input,str):
            return decision('manual_fallback',reason='invalid_input')
        if len(user_input)>MAX_ROUTING_INPUT_CHARS:
            return decision('manual_fallback',reason='input_length_limit')
        if not user_input.strip() or any(not c.isprintable() and c not in '\n\r\t' for c in user_input):
            return decision('manual_fallback',reason='invalid_input')

        if selective:
            return self._selective(user_input, fits, decision)

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

    def _selective(self, query, fits, decision):
        from ..agent.context_manager import ContextBudgetError
        from .relevance import evidence, MAX_CANDIDATES
        catalog = self.catalog
        config = catalog.config
        names = catalog.ranked_names(query)[:MAX_CANDIDATES]
        if not names:
            return decision('manual_fallback',reason='no_positive_candidates',evidence_level='none')
        matches = evidence(query,catalog,names)
        eligible = [n for n in names if matches[n].level=='strong']
        weak = sum(e.level=='weak' for e in matches.values())
        diagnostics = dict(evidence_level='strong' if eligible else ('weak' if weak else 'none'),
                           eligible_candidate_count=len(eligible),rejected_weak_count=weak)
        if not eligible:
            reason = ('generic_only_matches' if all(e.reason=='generic_only_matches' for e in matches.values())
                      else 'weak_evidence')
            return decision('manual_fallback',candidates=len(names),reason=reason,**diagnostics)
        all_names = tuple(catalog.entries)
        if (len(eligible)==len(all_names) and len(all_names)<=config.get('eager_tool_threshold',4)
                and len(all_names)<=min(config.get('preselect_limit',3),config['max_active_tools'])
                and catalog.schema_chars(all_names)<=config['max_active_schema_chars']):
            try: fits(all_names)
            except ContextBudgetError: pass
            else:
                covered = set().union(*(matches[n].matched for n in all_names))
                return decision('small_eager',all_names,len(names),covered_query_concepts_count=len(covered),**diagnostics)
        selected, covered = [], set()
        reason, redundant = None, 0
        remaining = list(eligible)
        limit = min(config.get('preselect_limit',3),config['max_active_tools'])
        while remaining and len(selected)<limit:
            # Common scale: concept gain / (1 + full Schema fraction). Ranking only breaks ties.
            def utility(n):
                gain = len(matches[n].matched - covered)
                return (-gain/(1+catalog.entries[n].schema_chars/config['max_active_schema_chars']),
                        -len(matches[n].matched),names.index(n),n)
            name = min(remaining,key=utility)
            remaining.remove(name)
            if not matches[name].matched - covered:
                redundant += 1
                continue
            proposed = [*selected,name]
            if catalog.schema_chars(proposed)>config['max_active_schema_chars']:
                reason = 'schema_budget_limited'
                continue
            try: fits(proposed)
            except ContextBudgetError:
                reason = 'context_budget_limited'
                continue
            selected = proposed
            covered.update(matches[name].matched)
        redundant += sum(not (matches[n].matched - covered) for n in remaining)
        return decision('coverage_preselect' if selected else 'manual_fallback',selected,len(names),
                        reason if selected else reason or 'no_feasible_candidates',
                        covered_query_concepts_count=len(covered),redundant_candidates_skipped=redundant,**diagnostics)
