from .validation import validate_stock, normalize_orders

def reserve(stock, orders):
    result=dict(stock)
    for sku,qty in orders: result[sku]-=qty
    return result
