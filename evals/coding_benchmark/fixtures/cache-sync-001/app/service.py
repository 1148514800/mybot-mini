from .store import Store
from .cache import Cache
class API:
    def __init__(self):
        self.store = Store(); self.cache = Cache(self.store)
    def read(self, key): return self.cache.get(key)
    def write(self, key, value):
        self.store.set(key, value)
        self.cache.invalidate('fixed')
