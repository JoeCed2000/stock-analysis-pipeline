"""Typed errors for earnings call deep-dive generation."""


class EarningsDeepDiveError(Exception):
    """Base error for earnings call deep-dive generation."""


class TranscriptMissingError(EarningsDeepDiveError):
    """Raised when no usable transcript text is available."""


class KimiFailureError(EarningsDeepDiveError):
    """Raised when Kimi does not return a usable section."""


class ValidationError(EarningsDeepDiveError):
    """Raised when a generated section fails deterministic validation."""
