from .spans import merge_spans

def coverage(spans):
    return sum(end-start for start,end in spans)
