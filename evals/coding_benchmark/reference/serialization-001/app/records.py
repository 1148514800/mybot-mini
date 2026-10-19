from dataclasses import dataclass, asdict
@dataclass
class Record:
    name: str
    active: bool = False
    count: int = 0
    tag: str | None = None
def to_record(record):
    return {key:value for key,value in asdict(record).items() if value is not None}
