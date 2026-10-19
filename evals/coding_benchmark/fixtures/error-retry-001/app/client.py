from .policy import attempts
from .transport import send
def execute(operation, retries=2):
    last = None
    for _ in attempts(retries):
        try: return send(operation)
        except Exception as error: last = error
    raise last
