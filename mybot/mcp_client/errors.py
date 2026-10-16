"""Fixed transport failure categories; never include wire data."""


class HTTPTransportError(RuntimeError):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)
