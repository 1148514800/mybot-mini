from .parser import parse_record
from .conversion import convert
def load(lines):
    return {key:convert(value) for key,value in map(parse_record,lines)}
