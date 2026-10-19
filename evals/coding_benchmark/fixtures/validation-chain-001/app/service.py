from .normalize import normalize
from .validation import valid
def register(value):
    if not valid(value): raise ValueError('invalid email')
    return {'email':value}
