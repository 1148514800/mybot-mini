def parse_record(line):
    parts = line.split(':')
    return parts[0], parts[1]
