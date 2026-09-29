"""Encryption envelopes when the host tools are installed."""

from __future__ import annotations

import io
import os
import shutil
import sys
from pathlib import Path

import pytest

from lupaxa.token_manager.cli import main
from lupaxa.token_manager.store import Store


@pytest.fixture
def config_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("TOKENCTL_PASSPHRASE", "test-passphrase")
    return tmp_path


def test_openssl_roundtrip(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert main(["add", "--type", "github", "--name", "ci", "--value", "secret"]) == 0
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "ci", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "secret"
    profile = config_home / "tokenctl" / "profiles" / "default"
    assert (profile / "tokens.json.enc").is_file()
    assert not (profile / "tokens.json").exists()


def test_gpg_roundtrip(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    if shutil.which("gpg") is None:
        pytest.skip("gpg is not installed")
    assert main(["--profile", "locked", "profile", "init", "--encryption", "gpg"]) == 0
    assert (
        main(
            [
                "--profile",
                "locked",
                "add",
                "--type",
                "github",
                "--name",
                "ci",
                "--value",
                "secret",
            ]
        )
        == 0
    )
    capsys.readouterr()
    store = Store(profile="locked", config_dir=config_home / "tokenctl")
    assert store.load()[0].value == "secret"
    assert (config_home / "tokenctl" / "profiles" / "locked" / "tokens.json.gpg").is_file()


def test_prompted_openssl_passphrase_is_not_stored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TOKENCTL_PASSPHRASE", raising=False)

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "prompted-pass")
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert main(["add", "--type", "github", "--name", "ci", "--value", "secret"]) == 0
    assert "TOKENCTL_PASSPHRASE" not in os.environ
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "ci", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "secret"
