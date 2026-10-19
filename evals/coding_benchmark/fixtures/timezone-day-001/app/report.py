from .parsing import parse_stamp
def utc_day(value):
    return parse_stamp(value).date().isoformat()
