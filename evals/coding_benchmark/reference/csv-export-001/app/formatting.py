import csv
import io
def render_row(row):
    stream = io.StringIO(newline='')
    csv.writer(stream, lineterminator='\r\n').writerow(row)
    return stream.getvalue()[:-2] + '\n'
