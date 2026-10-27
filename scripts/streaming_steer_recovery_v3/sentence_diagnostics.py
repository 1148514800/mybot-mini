"""Deterministic format hints, never semantic entailment or output rewriting."""
import re

def diagnose(text,expected=None):
    if not isinstance(text,str):raise TypeError('text_required')
    review=[]
    if re.search(r'```|~~~|(?m:^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s))',text):review.append('markdown_structure')
    if re.search(r'\.\.\.|…',text):review.append('ellipsis')
    if re.search(r'\b(?:Mr|Mrs|Ms|Dr|Prof|etc|vs)\.|\b(?:e\.g|i\.e)\.',text,re.I):review.append('abbreviation')
    if any(x in text for x in ('“','”','「','」','"')):review.append('quoted_punctuation')
    # Code does not count as prose; its presence always requires review.
    prose=re.sub(r'(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*(?:\n|$)','',text)
    prose=re.sub(r'`[^`\n]*`','',prose)
    prose=re.sub(r'(?<=\d)\.(?=\d)','',prose)
    prose=re.sub(r'\.{2,}|…+','',prose)
    prose=re.sub(r'\b(?:Mr|Mrs|Ms|Dr|Prof|etc|vs)\.',lambda m:m[0][:-1],prose,flags=re.I)
    prose=re.sub(r'\b(?:e\.g|i\.e)\.',lambda m:m[0].replace('.',''),prose,flags=re.I)
    count=len(re.findall(r'[。！？!?]+|\.(?=\s|$|[”\"])',prose))
    return dict(deterministic_sentence_count=count,expected_sentences=expected,format_check='FORMAT_REVIEW_REQUIRED' if review else 'NOT_EVALUATED' if expected is None else 'PASS' if count==expected else 'FAIL',independent_semantic_review='NOT_PERFORMED',review_reasons=review,rewritten=False)
