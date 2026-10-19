from .formatting import render_row
def export(rows):
    return ''.join(render_row(row) for row in rows)
