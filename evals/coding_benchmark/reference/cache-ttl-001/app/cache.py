class Cache:
    def __init__(self): self.items = {}
    def put(self, key, value, now, ttl):
        if ttl < 0: raise ValueError("negative ttl")
        self.items[key] = (value, now + ttl)
    def get(self, key, now):
        if key not in self.items: return None
        value, expires = self.items[key]
        return None if now >= expires else value
