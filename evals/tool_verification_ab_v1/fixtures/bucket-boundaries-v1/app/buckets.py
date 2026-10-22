def bucket(value, thresholds):
    return sum(value > limit for limit in thresholds)
