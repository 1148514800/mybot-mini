"""mybot package. Keep diagnostics usable before configuration is imported."""
__all__ = ['run_gateway']


def __getattr__(name):
    if name == 'run_gateway':
        from .app import run_gateway
        return run_gateway
    raise AttributeError(name)
