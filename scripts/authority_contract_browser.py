"""Explicit local SYNTHETIC browser fixture. Never creates a model SDK client."""
import argparse
from pathlib import Path
import tempfile
import uvicorn
from mybot.web.server import create_app
from scripts.authority_contract_fixtures import configuration,prepare,SyntheticClient


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scenario',choices=['A','B','C'],required=True)
    parser.add_argument('--port',type=int,default=8884);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mybot-contract-browser-') as folder:
        root=Path(folder).resolve();prepare(root,args.scenario)
        app=create_app(configuration(root,args.scenario),port=args.port,
            client_factory=lambda cfg:SyntheticClient(args.scenario),approval_timeout=240)
        uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,timeout_graceful_shutdown=3)

if __name__=='__main__':main()
