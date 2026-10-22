修复reserve(stock, orders)完整调用链。stock必须dict，键为非空且已strip的str，库存为非负真正int（bool无效）。orders仅list/tuple，每项为长度2的list/tuple，sku为strip后非空str，数量为正真正int。按strip后的sku合并重复订单；未知sku或合并数量超过库存抛ValueError。成功返回扣减后的新dict；成功或失败均不得改变stock或orders。validate_stock及normalize_orders应各实现其公开同名校验契约，reserve必须使用它们的校验与归一化结果。其他非法输入抛ValueError。

python -m unittest discover -s tests -v
