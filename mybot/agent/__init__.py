"""Public agent classes, loaded on demand to avoid configuration/import cycles."""
__all__ = ['AgentLoop', 'ContextBuilder', 'Session']


def __getattr__(name):
    from importlib import import_module
    modules = {'AgentLoop': '.loop', 'ContextBuilder': '.context', 'Session': '.session'}
    if name not in modules: raise AttributeError(name)
    return getattr(import_module(modules[name], __name__), name)
