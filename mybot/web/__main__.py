"""uv run python -m mybot.web --port 8765 (loopback only; no access logs)."""
import argparse
import uvicorn
from .server import create_app


def main():
    parser = argparse.ArgumentParser(description='mybot-mini 本地 Web Chat')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('port must be between 1024 and 65535')
    uvicorn.run(create_app(port=args.port), host='127.0.0.1', port=args.port, access_log=False, timeout_graceful_shutdown=3)


if __name__ == '__main__': main()
