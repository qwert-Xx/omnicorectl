"""Stable errors shared by the protocol and CLI layers."""


class OmnicoreError(Exception):
    """Base class for expected omnicorectl failures."""


class ConfigurationError(OmnicoreError):
    """The command is missing or has invalid local configuration."""


class NetworkError(OmnicoreError):
    """The controller could not be reached in time."""


class AuthenticationError(OmnicoreError):
    """The controller rejected the supplied credentials."""


class AuthorizationError(OmnicoreError):
    """The authenticated user lacks the required controller grant."""


class ProtocolError(OmnicoreError):
    """The controller returned an invalid or unexpected RWS representation."""


class RwsHttpError(OmnicoreError):
    """RWS returned an unsuccessful HTTP response."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code

