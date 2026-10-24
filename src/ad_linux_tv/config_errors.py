"""User-safe configuration validation errors."""


class ConfigurationError(ValueError):
    """Expected validation error without embedding user-provided values."""
