"""Domain errors."""

from __future__ import annotations


class BhatiError(Exception):
    """Base error."""

    status_code = 500


class ConfigurationError(BhatiError):
    status_code = 500


class ProviderError(BhatiError):
    status_code = 502


class ToolError(BhatiError):
    status_code = 400


class PermissionDenied(BhatiError):
    status_code = 403


class NotFound(BhatiError):
    status_code = 404


class BudgetExceeded(BhatiError):
    status_code = 429
