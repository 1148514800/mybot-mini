import csv

def parse_row(text):
    if not isinstance(text, str) or '\r' in text or '\n' in text:
        raise ValueError('invalid row')
    if not text: return []
    try:
        return next(csv.reader([text], delimiter=';', quotechar='"', doublequote=True, strict=True, skipinitialspace=False))
    except csv.Error as exc:
        raise ValueError('invalid row') from exc
