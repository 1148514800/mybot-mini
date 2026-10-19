def attempts(retries):
    if type(retries) is not int or retries < 0: raise ValueError('nonnegative integer required')
    return range(retries + 1)
