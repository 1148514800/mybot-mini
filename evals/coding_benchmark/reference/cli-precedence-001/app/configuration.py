def merge(config, args):
    return {'retries':args.retries if args.retries is not None else config.get('retries',3),
            'verbose':args.verbose if args.verbose is not None else config.get('verbose',False)}
