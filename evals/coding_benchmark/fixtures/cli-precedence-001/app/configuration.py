def merge(config, args):
    return {'retries':args.retries or config.get('retries') or 3,
            'verbose':args.verbose or config.get('verbose',False)}
