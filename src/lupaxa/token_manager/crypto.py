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
_prompted_passphrases: dict[str, str] = {}
_allow_env = True
_passphrase_slot = ""


def clear_passphrase_cache() -> None:
    """Forget passphrases typed at the prompt."""
    global _allow_env, _passphrase_slot
    _prompted_passphrases.clear()
    _allow_env = True
    _passphrase_slot = ""


def use_passphrase_slot(slot: str) -> None:
    """Choose which passphrase a profile prompts for.

    An empty slot is the normal prompt. ``current`` and ``new`` are the two
    passphrases used when one profile changes from one encrypted mode to another.
    """
    global _passphrase_slot
    _passphrase_slot = slot


def require_separate_passphrases() -> bool:
    """Stop using ``TOKENCTL_PASSPHRASE`` for this command.

    Returns whether that variable is set.
    """
    global _allow_env
    _allow_env = False
    return bool(os.environ.get(PASSPHRASE_ENV))


def get_passphrase(profile: str) -> str:
    """Return the passphrase for ``profile``.

    ``TOKENCTL_PASSPHRASE`` is used only when this command needs one passphrase.
    Otherwise each profile is prompted once and remembered until
    ``clear_passphrase_cache`` runs. The value is not stored in the environment.
    """
    import getpass
    import sys

    env = os.environ.get(PASSPHRASE_ENV)
    if env and _allow_env:
        return env
    key = f"{profile}:{_passphrase_slot}" if _passphrase_slot else profile
    cached = _prompted_passphrases.get(key)
    if cached is not None:
        return cached
    if not sys.stdin.isatty():
        if not _allow_env:
            raise TokenManagerError(
                f"Type the passphrase for '{profile}' on a terminal. "
                f"{PASSPHRASE_ENV} is only used when one passphrase is required."
            )
        raise TokenManagerError(f"{PASSPHRASE_ENV} not set and no TTY for passphrase prompt.")
    if _passphrase_slot == "current":
        prompt = f"Current passphrase for '{profile}': "
    elif _passphrase_slot == "new":
        prompt = f"New passphrase for '{profile}': "
    else:
        prompt = f"Passphrase for '{profile}': "
    prompted = getpass.getpass(prompt)
    _prompted_passphrases[key] = prompted
    return prompted


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
        previous_umask = os.umask(0o077)
        try:
            return subprocess.run(
                rendered,
                input=stdin,
                capture_output=True,
                check=True,
                pass_fds=(read_fd,),
            )
        finally:
            os.umask(previous_umask)
    finally:
        os.close(read_fd)


def _decode_rows(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TokenManagerError("Decrypted data is not valid JSON.") from exc
    if not isinstance(data, list):
        raise TokenManagerError("Decrypted data is not a list of tokens. Refusing to continue.")
    return data


def read_gpg(path: Path, *, profile: str) -> list[dict[str, Any]]:
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
        proc = _run_with_passphrase(cmd, get_passphrase(profile))
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="ignore").strip()
        raise TokenManagerError(f"gpg decrypt failed: {detail}") from exc
    return _decode_rows(proc.stdout.decode("utf-8"))


def write_gpg(path: Path, rows: list[dict[str, Any]], *, profile: str) -> None:
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
        _run_with_passphrase(cmd, get_passphrase(profile), stdin=data)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="ignore").strip()
        raise TokenManagerError(f"gpg encrypt failed: {detail}") from exc
    chmod_600(path)


def read_openssl(path: Path, *, profile: str) -> list[dict[str, Any]]:
    """Decrypt an openssl AES-256-CBC file."""
    require_encryption("openssl")
    cmd = [
        "openssl",
        "enc",
        "-aes-256-cbc",
        "-d",
        "-pbkdf2",
        "-salt",
        "-in",
        str(path),
        "-pass",
        "fd:{fd}",
    ]
    try:
        proc = _run_with_passphrase(cmd, get_passphrase(profile))
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="ignore").strip()
        raise TokenManagerError(f"openssl decrypt failed: {detail}") from exc
    return _decode_rows(proc.stdout.decode("utf-8"))


def write_openssl(path: Path, rows: list[dict[str, Any]], *, profile: str) -> None:
    """Encrypt rows with openssl AES-256-CBC."""
    require_encryption("openssl")
    data = (json.dumps(rows, indent=2) + "\n").encode()
    cmd = [
        "openssl",
        "enc",
        "-aes-256-cbc",
        "-pbkdf2",
        "-salt",
        "-out",
        str(path),
        "-pass",
        "fd:{fd}",
    ]
    try:
        _run_with_passphrase(cmd, get_passphrase(profile), stdin=data)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="ignore").strip()
        raise TokenManagerError(f"openssl encrypt failed: {detail}") from exc
    chmod_600(path)
