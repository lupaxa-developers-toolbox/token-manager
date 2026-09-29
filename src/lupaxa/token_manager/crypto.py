"""Optional gpg and openssl envelopes for a token list."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from lupaxa.token_manager.exceptions import TokenManagerError
from lupaxa.token_manager.io import chmod_600
from lupaxa.token_manager.models import require_encryption

PASSPHRASE_ENV = "TOKENCTL_PASSPHRASE"


def get_passphrase() -> str:
    """Return the passphrase from the environment or a TTY prompt."""
    import getpass
    import sys

    env = os.environ.get(PASSPHRASE_ENV)
    if env:
        return env
    if not sys.stdin.isatty():
        raise TokenManagerError(f"{PASSPHRASE_ENV} not set and no TTY for passphrase prompt.")
    return getpass.getpass("Passphrase: ")


def _run_with_passphrase(
    cmd: list[str],
    passphrase: str,
    *,
    stdin: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run ``cmd``, substituting ``{fd}`` with a pipe that holds the passphrase.

    The passphrase never shares stdin with the payload, and it is not written
    back into the process environment.
    """
    read_fd, write_fd = os.pipe()
    try:
        payload = memoryview(passphrase.encode() + b"\n")
        while payload:
            written = os.write(write_fd, payload)
            payload = payload[written:]
    finally:
        os.close(write_fd)
    try:
        rendered = [part.replace("{fd}", str(read_fd)) for part in cmd]
        return subprocess.run(
            rendered,
            input=stdin,
            capture_output=True,
            check=True,
            pass_fds=(read_fd,),
        )
    finally:
        os.close(read_fd)


def _decode_rows(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TokenManagerError("Decrypted data is not valid JSON.") from exc
    if not isinstance(data, list):
        return []
    return data


def read_gpg(path: Path) -> list[dict[str, Any]]:
    """Decrypt a gpg symmetric file."""
    require_encryption("gpg")
    cmd = [
        "gpg",
        "--batch",
        "--yes",
        "--pinentry-mode",
        "loopback",
        "--passphrase-fd",
        "{fd}",
        "--decrypt",
        str(path),
    ]
    try:
        proc = _run_with_passphrase(cmd, get_passphrase())
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="ignore").strip()
        raise TokenManagerError(f"gpg decrypt failed: {detail}") from exc
    return _decode_rows(proc.stdout.decode("utf-8"))


def write_gpg(path: Path, rows: list[dict[str, Any]]) -> None:
    """Encrypt rows with gpg symmetric AES256."""
    require_encryption("gpg")
    data = (json.dumps(rows, indent=2) + "\n").encode()
    cmd = [
        "gpg",
        "--symmetric",
        "--cipher-algo",
        "AES256",
        "--batch",
        "--yes",
        "--pinentry-mode",
        "loopback",
        "--passphrase-fd",
        "{fd}",
        "-o",
        str(path),
    ]
    try:
        _run_with_passphrase(cmd, get_passphrase(), stdin=data)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="ignore").strip()
        raise TokenManagerError(f"gpg encrypt failed: {detail}") from exc
    chmod_600(path)


def read_openssl(path: Path) -> list[dict[str, Any]]:
    """Decrypt an openssl AES-256-CBC file."""
    require_encryption("openssl")
    cmd = [
        "openssl",
        "enc",
        "-aes-256-cbc",
        "-d",
        "-salt",
        "-in",
        str(path),
        "-pass",
        "fd:{fd}",
    ]
    try:
        proc = _run_with_passphrase(cmd, get_passphrase())
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="ignore").strip()
        raise TokenManagerError(f"openssl decrypt failed: {detail}") from exc
    return _decode_rows(proc.stdout.decode("utf-8"))


def write_openssl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Encrypt rows with openssl AES-256-CBC."""
    require_encryption("openssl")
    data = (json.dumps(rows, indent=2) + "\n").encode()
    cmd = [
        "openssl",
        "enc",
        "-aes-256-cbc",
        "-salt",
        "-out",
        str(path),
        "-pass",
        "fd:{fd}",
    ]
    try:
        _run_with_passphrase(cmd, get_passphrase(), stdin=data)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="ignore").strip()
        raise TokenManagerError(f"openssl encrypt failed: {detail}") from exc
    chmod_600(path)
