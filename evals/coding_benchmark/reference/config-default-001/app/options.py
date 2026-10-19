def enabled(config, key, default=False):
    value = config.get(key, default)
    if type(value) is not bool:
        raise ValueError('expected boolean')
    return value
