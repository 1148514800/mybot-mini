"""Offline routing quality, independent of end-to-end task success."""
import argparse
import json
from mybot.evaluation.tool_routing import evaluate

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split',choices=('design','heldout'))
    print(json.dumps(evaluate(parser.parse_args().split),ensure_ascii=False,indent=2))
