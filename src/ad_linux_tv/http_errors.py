"""HTTP request boundary errors."""


class BodyTimeout(Exception):
    """Request body was not delivered within the socket read timeout."""
