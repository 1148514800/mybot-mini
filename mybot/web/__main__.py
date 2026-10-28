"""Loopback Web project launcher; --check is read-only and never starts a runtime."""
import argparse
import json
from .launch import prepare_launch, LaunchError


def main(argv=None):
    parser = argparse.ArgumentParser(description='mybot-mini 本地项目 Web Chat')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--workspace', help='已存在的 Git 仓库根目录（绝对路径）')
    parser.add_argument('--check', action='store_true', help='只检查配置和项目，不启动服务或请求模型')
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535: parser.error('port must be between 1024 and 65535')
    try:
        config, project, report = prepare_launch(args.workspace)
    except LaunchError as exc:
        print(json.dumps(exc.result, ensure_ascii=False))
        return 2
    if args.check:
        print(json.dumps(report, ensure_ascii=False))
        return 0
    import uvicorn
    from .server import create_app
    uvicorn.run(create_app(config, port=args.port, project=project), host='127.0.0.1', port=args.port,
                access_log=False, timeout_graceful_shutdown=3)
    return 0


if __name__ == '__main__': raise SystemExit(main())
