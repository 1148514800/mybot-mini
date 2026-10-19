def send(operation):
    try: return operation()
    except Exception: return None
