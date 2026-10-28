class ProviderError(Exception):
    failover = False


class TransientError(ProviderError):
    pass  # retry later, may fail over


class PermanentError(ProviderError):  # never retry
    def __init__(self, message: str, failover: bool = False):
        super().__init__(message)
        self.failover = failover
