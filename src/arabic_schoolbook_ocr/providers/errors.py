class ProviderUnavailableError(RuntimeError):
    """The selected provider cannot run in the current environment."""


class ProviderResponseError(RuntimeError):
    """A provider returned a result that cannot be mapped safely."""
