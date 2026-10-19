def save_text(path, value):
    with open(path, 'w', encoding='utf-8') as stream:
        stream.write(value)
