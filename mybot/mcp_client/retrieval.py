"""Deterministic weighted field BM25. Only bounded, validated Catalog metadata enters here."""
import math
import re
from collections import Counter
from .retrieval_aliases import ALIASES, MAX_ALIAS_MATCHES, MAX_EXPANDED_TERMS

K1, B = 1.2, 0.75
FIELD_WEIGHTS = (6, 3, 1)
MAX_QUERY_TERMS = 128


def tokenize(text):
    tokens = []
    for part in re.findall(r'[\u3400-\u9fff]+|[^\W_\u3400-\u9fff]+', text.casefold()):
        if '\u3400' <= part[0] <= '\u9fff':
            tokens.extend(part)
            tokens.extend(part[i:i+2] for i in range(len(part)-1))
        else:
            tokens.append(part)
    return tokens


def expand_query(query):
    """Longest CJK dictionary match; English whole words; fixed global expansion caps."""
    aliases, matches = [], 0
    keys = sorted((k for k in ALIASES if '\u3400' <= k[0] <= '\u9fff'), key=lambda k: (-len(k), k))
    index = 0
    while index < len(query) and matches < MAX_ALIAS_MATCHES:
        key = next((k for k in keys if query.startswith(k,index)), None)
        if key:
            aliases.extend(ALIASES[key]); matches += 1; index += len(key)
        else:
            index += 1
    for word in dict.fromkeys(tokenize(query)):
        if matches >= MAX_ALIAS_MATCHES: break
        if word in ALIASES and not ('\u3400' <= word[0] <= '\u9fff'):
            aliases.extend(ALIASES[word]); matches += 1
    return tuple(dict.fromkeys(aliases))[:MAX_EXPANDED_TERMS]


class BM25Index:
    def __init__(self, documents):
        # documents: name -> (name, server, bounded description), never schemas or golds.
        self.fields = {name: tuple(Counter(tokenize(f)) for f in fields) for name, fields in documents.items()}
        self.lengths = {name: tuple(sum(c.values()) for c in fields) for name,fields in self.fields.items()}
        self.n = len(self.fields)
        self.averages = tuple(sum(lengths[i] for lengths in self.lengths.values()) / self.n if self.n else 0 for i in range(3))
        self.df = Counter(term for fields in self.fields.values() for term in set().union(*fields))

    def idf(self, term):
        df = self.df.get(term,0)
        return math.log1p((self.n-df+0.5)/(df+0.5)) if df else 0.0

    def scores(self, query_terms):
        query_terms = tuple(sorted(set(query_terms)))[:MAX_QUERY_TERMS]
        scores = {}
        for name,fields in self.fields.items():
            score = 0.0
            for term in query_terms:
                for i,(counts,weight) in enumerate(zip(fields,FIELD_WEIGHTS)):
                    tf = counts[term]
                    if tf:
                        norm = 1-B+B*self.lengths[name][i]/self.averages[i]
                        score += weight*self.idf(term)*tf*(K1+1)/(tf+K1*norm)
            if score > 0: scores[name] = score
        return scores

    def rank(self, query, hybrid=False):
        exact = self.scores(tokenize(query))
        if hybrid:
            aliases = self.scores(expand_query(query))
            # Preserve original evidence at full weight, bounded alias evidence at 0.35.
            exact = {name: exact.get(name,0)+0.35*aliases.get(name,0) for name in exact.keys() | aliases.keys()}
        return sorted(exact,key=lambda name: (-exact[name],name))
