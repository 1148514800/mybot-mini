def validate_stock(stock):
    if not isinstance(stock, dict): raise ValueError('invalid stock')
    for key,value in stock.items():
        if not isinstance(key,str) or not key or key.strip()!=key or type(value) is not int or value<0:
            raise ValueError('invalid stock')
    return dict(stock)

def normalize_orders(orders):
    if not isinstance(orders,(list,tuple)): raise ValueError('invalid orders')
    result=[]
    for pair in orders:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2: raise ValueError('invalid order')
        sku,qty=pair
        if not isinstance(sku,str) or not sku.strip() or type(qty) is not int or qty<=0:
            raise ValueError('invalid order')
        result.append((sku.strip(),qty))
    return result
