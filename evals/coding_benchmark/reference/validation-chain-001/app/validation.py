import re
def valid(value):
    return re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value) is not None
