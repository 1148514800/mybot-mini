import re
def convert(value):
    return int(value) if re.fullmatch(r'[+-]?[0-9]+', value) else value
