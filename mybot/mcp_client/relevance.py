"""Version 1 lexical evidence, never calibrated probability. Metadata and current query only."""
from dataclasses import dataclass
from .retrieval import tokenize, expand_query

# Frozen before the independent routing heldout is evaluated. No corpus/case-specific rules.
GENERIC = frozenset('a an the and or to for of in on by with is are be it this that please can you i me my we our tool tools available help synthetic catalog teaching read only use using need want find out show tell about information something anything'.split())
OPERATIONS = frozenset('list get search find query summarize inspect describe filter group lookup'.split())
CANONICAL = {'tasks':'task','documents':'document','modules':'module','events':'event',
             'symbols':'symbol','statistics':'stats','datasets':'dataset','data':'dataset',
             'references':'reference','columns':'column','rows':'row','labels':'label',
             'members':'member','versions':'version','sections':'section','links':'link',
             'milestones':'milestone','calendars':'calendar','metrics':'metric','imports':'import'}
MAX_EVIDENCE_TERMS = 128
MAX_CANDIDATES = 64


def concepts(text, *, aliases=False):
    tokens = tokenize(text) + (list(expand_query(text)) if aliases else [])
    # CJK single characters/bigrams are retrieval evidence only; fixed aliases supply concepts.
    return frozenset(CANONICAL.get(t,t) for t in tokens[:256]
                     if t not in GENERIC and t.isascii() and t.isalpha())


@dataclass(frozen=True)
class MatchEvidence:
    level: str
    matched: frozenset[str]
    reason: str


def evidence(query, catalog, names):
    """Name-domain evidence or >=2 independent, discriminative description concepts.

    DF discounts descriptions, never blindly removes all high-DF name concepts in small catalogs.
    Aliases are the SAME fixed retrieval vocabulary. Rank magnitude is intentionally unused.
    """
    query_terms = frozenset(sorted(concepts(query, aliases=catalog.config.get('retrieval_mode')=='hybrid'))[:MAX_EVIDENCE_TERMS])
    fields = {name:(concepts(entry.name.split('__')[-1]), concepts(entry.server), concepts(entry.description))
              for name,entry in catalog.entries.items()}
    df = {term:sum(term in set().union(*f) for f in fields.values()) for term in query_terms}
    result = {}
    for name in names:
        named, server, description = fields[name]
        matched = query_terms & (named | server | description)
        name_match = query_terms & (named | server)
        domain = name_match - OPERATIONS
        rare_description = {t for t in matched - OPERATIONS if df[t]*2 <= len(fields)}
        strong = bool(domain and (len(fields)<=4 or any(df[t]*2<=len(fields) for t in domain) or len(name_match)>=2))
        strong = strong or len(rare_description)>=2
        if strong: result[name] = MatchEvidence('strong',matched,'substantive_match')
        elif matched: result[name] = MatchEvidence('weak',matched,'weak_evidence')
        else:
            entry = catalog.entries[name]
            generic_match = set(tokenize(query)) & GENERIC & set(tokenize(entry.name+' '+entry.server+' '+entry.description))
            result[name] = MatchEvidence('weak' if generic_match else 'none',frozenset(),
                                         'generic_only_matches' if generic_match else 'no_substantive_match')
    return result
