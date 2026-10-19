import os
from pathlib import Path
import tempfile
def save_text(path, value):
    if not isinstance(value, str): raise TypeError('text required')
    data = value.encode('utf-8')
    path = Path(path)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            name = stream.name
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if name is not None and os.path.exists(name): os.unlink(name)
