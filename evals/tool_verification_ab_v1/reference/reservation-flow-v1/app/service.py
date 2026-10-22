from .validation import validate_stock, normalize_orders

def reserve(stock, orders):
    result=validate_stock(stock); totals={}
    for sku,qty in normalize_orders(orders): totals[sku]=totals.get(sku,0)+qty
    for sku,qty in totals.items():
        if sku not in result or qty>result[sku]: raise ValueError('unavailable stock')
    for sku,qty in totals.items(): result[sku]-=qty
    return result
