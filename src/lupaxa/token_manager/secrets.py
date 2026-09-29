"""Read a secret from an argument, stdin, or a hidden prompt."""

from __future__ import annotations

from lupaxa.token_manager.exceptions import TokenManagerError


def resolve_secret(value: str | None) -> str:
    """Return a secret from ``value``.

    ``None`` and ``-`` read stdin. A terminal uses a hidden prompt. An empty
    secret is a usage error.
    """
    if value is None or value == "-":
        return _read_secret()
    if value == "":
        raise TokenManagerError("Secret value is empty.", exit_code=2)
    return value


def _read_secret() -> str:
    import getpass
    import sys

    if sys.stdin.isatty():
        secret = getpass.getpass("Value: ")
    else:
        secret = sys.stdin.read()
        if secret.endswith("\r\n"):
            secret = secret[:-2]
        elif secret.endswith("\n"):
            secret = secret[:-1]
    if secret == "":
        raise TokenManagerError("Secret value is empty.", exit_code=2)
    return secret
