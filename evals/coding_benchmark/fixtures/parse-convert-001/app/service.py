from .parser import parse_record
from .conversion import convert
def load(lines):
    return dict(parse_record(line) for line in lines)
