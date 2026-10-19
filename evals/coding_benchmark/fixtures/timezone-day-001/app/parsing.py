from datetime import datetime,timezone
def parse_stamp(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).replace(tzinfo=timezone.utc)
