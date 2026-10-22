def bucket(value, thresholds):
    if type(value) is not int or not isinstance(thresholds, (list, tuple)):
        raise ValueError('invalid input')
    if any(type(x) is not int for x in thresholds) or any(a >= b for a,b in zip(thresholds, thresholds[1:])):
        raise ValueError('invalid thresholds')
    return sum(limit <= value for limit in thresholds)
