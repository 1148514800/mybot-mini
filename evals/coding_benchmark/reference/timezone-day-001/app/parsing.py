from datetime import datetime,timezone
def parse_stamp(value):
    stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
