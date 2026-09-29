"""Errors raised by the token manager library."""

from __future__ import annotations


class TokenManagerError(Exception):
    """Base error for token storage and command failures.

    ``exit_code`` is ``2`` for usage mistakes and ``1`` for runtime failures.
    """

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code
