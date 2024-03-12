class PandoraOnlineException(Exception):
    """Base class for Pandora Car Alarm System exceptions"""


class MalformedResponseError(PandoraOnlineException, ValueError):
    """Response does not match expected format."""


class AuthenticationError(PandoraOnlineException):
    """Authentication-related exception"""


class SessionExpiredError(AuthenticationError):
    """When access token deemed expired or not authenticated"""


class InvalidAccessTokenError(AuthenticationError):
    """When access token is deemed malformed."""


class MissingAccessTokenError(InvalidAccessTokenError):
    """When access token is missing on object"""
