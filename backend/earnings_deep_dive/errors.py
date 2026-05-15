"""Typed errors for earnings call deep-dive generation."""


class EarningsDeepDiveError(Exception):
    """Base error for earnings call deep-dive generation."""


class TranscriptMissingError(EarningsDeepDiveError):
    """Raised when no usable transcript text is available."""


class KimiFailureError(EarningsDeepDiveError):
    """Raised when Kimi does not return a usable section."""


class ValidationError(EarningsDeepDiveError):
    """Raised when a generated section fails deterministic validation.

    Attributes:
        ticker: The ticker symbol that failed validation.
        errors: List of ValidationWarning objects (from pre_render_validator).
        message: Human-readable error summary.
    """

    def __init__(self, *args, ticker: str = "", errors=None, message: str = ""):
        self.ticker = ticker
        self.errors = errors or []
        self._message = message
        if message:
            super().__init__(message)
        else:
            super().__init__(*args)

    def __str__(self) -> str:
        return self._message or super().__str__()
