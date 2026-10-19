def enabled(config, key, default=False):
    return bool(config.get(key) or default)
