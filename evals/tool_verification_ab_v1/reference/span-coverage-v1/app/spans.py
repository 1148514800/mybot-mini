def merge_spans(spans):
    if not isinstance(spans,(list,tuple)): raise ValueError('invalid spans')
    valid=[]
    for span in spans:
        if not isinstance(span,(list,tuple)) or len(span)!=2: raise ValueError('invalid span')
        a,b=span
        if type(a) is not int or type(b) is not int or a>b: raise ValueError('invalid span')
        if a<b: valid.append((a,b))
    merged=[]
    for a,b in sorted(valid):
        if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(merged[-1][1],b))
        else: merged.append((a,b))
    return merged
