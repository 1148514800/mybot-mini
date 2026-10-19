def parse_record(line):
    key, value = line.split(':', 1)
    if not key.strip(): raise ValueError('empty key')
    return key.strip(), value.strip()
