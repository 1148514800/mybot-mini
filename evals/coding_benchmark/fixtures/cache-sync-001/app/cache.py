class Cache:
    def __init__(self, store): self.store, self.values = store, {}
    def get(self, key):
        if key not in self.values: self.values[key] = self.store.get(key)
        return self.values[key]
    def invalidate(self, key):
        return None
