import argparse
def parse(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--retries', type=int, default=None)
    parser.add_argument('--verbose', action='store_true', default=None)
    return parser.parse_args(argv)
