import argparse
def parse(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--retries', type=int, default=3)
    parser.add_argument('--verbose', action='store_true')
    return parser.parse_args(argv)
