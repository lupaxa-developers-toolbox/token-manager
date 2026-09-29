"""Encryption envelopes when the host tools are installed."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
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


def test_prompted_passphrase_is_read_once_per_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TOKENCTL_PASSPHRASE", raising=False)

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    calls = {"count": 0}

    def _getpass(prompt: str = "") -> str:
        del prompt
        calls["count"] += 1
        return "prompted-pass"

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("getpass.getpass", _getpass)
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert calls["count"] == 1
    calls["count"] = 0
    assert main(["add", "--type", "github", "--name", "ci", "--value", "secret"]) == 0
    assert calls["count"] == 1


def test_migrate_prompts_for_each_encrypted_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TOKENCTL_PASSPHRASE", raising=False)

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    prompts: list[str] = []

    def _getpass(prompt: str = "") -> str:
        prompts.append(prompt)
        if prompt == "Passphrase for 'default': ":
            return "source-pass"
        if prompt == "Passphrase for 'archive': ":
            return "dest-pass"
        raise AssertionError(prompt)

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("getpass.getpass", _getpass)
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    assert main(["--profile", "archive", "profile", "init", "--encryption", "openssl"]) == 0
    prompts.clear()
    assert main(["migrate", "--from-profile", "default", "--to-profile", "archive"]) == 0
    assert prompts == [
        "Passphrase for 'default': ",
        "Passphrase for 'archive': ",
    ]
    monkeypatch.setenv("TOKENCTL_PASSPHRASE", "dest-pass")
    capsys.readouterr()
    assert (
        main(
            [
                "--profile",
                "archive",
                "set",
                "--type",
                "github",
                "--name",
                "main",
                "--format",
                "value",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.strip() == "secret"
    monkeypatch.setenv("TOKENCTL_PASSPHRASE", "source-pass")
    assert main(["set", "--type", "github", "--name", "main", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "secret"


def test_migrate_prompts_once_when_one_side_is_encrypted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TOKENCTL_PASSPHRASE", raising=False)

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    prompts: list[str] = []

    def _getpass(prompt: str = "") -> str:
        prompts.append(prompt)
        if prompt == "Passphrase for 'default': ":
            return "source-pass"
        if prompt == "Passphrase for 'archive': ":
            return "dest-pass"
        raise AssertionError(prompt)

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("getpass.getpass", _getpass)
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    assert main(["--profile", "open", "profile", "init"]) == 0
    prompts.clear()
    assert (
        main(
            [
                "migrate",
                "--from-profile",
                "default",
                "--to-profile",
                "open",
                "--move",
            ]
        )
        == 0
    )
    assert prompts == ["Passphrase for 'default': "]
    opened = tmp_path / "tokenctl" / "profiles" / "open" / "tokens.json"
    assert json.loads(opened.read_text(encoding="utf-8"))[0]["value"] == "secret"

    assert main(["--profile", "plain", "profile", "init"]) == 0
    assert (
        main(
            [
                "--profile",
                "plain",
                "add",
                "--type",
                "github",
                "--name",
                "main",
                "--value",
                "other",
            ]
        )
        == 0
    )
    assert main(["--profile", "archive", "profile", "init", "--encryption", "openssl"]) == 0
    prompts.clear()
    assert main(["migrate", "--from-profile", "plain", "--to-profile", "archive"]) == 0
    assert prompts == ["Passphrase for 'archive': "]


def test_shared_passphrase_env_is_ignored_when_both_profiles_are_encrypted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TOKENCTL_PASSPHRASE", raising=False)

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    prompts: list[str] = []

    def _getpass(prompt: str = "") -> str:
        prompts.append(prompt)
        if prompt == "Passphrase for 'default': ":
            return "source-pass"
        if prompt == "Passphrase for 'archive': ":
            return "dest-pass"
        raise AssertionError(prompt)

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("getpass.getpass", _getpass)
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    assert main(["--profile", "archive", "profile", "init", "--encryption", "openssl"]) == 0
    prompts.clear()
    monkeypatch.setenv("TOKENCTL_PASSPHRASE", "not-either-passphrase")
    assert main(["migrate", "--from-profile", "default", "--to-profile", "archive"]) == 0
    assert prompts == [
        "Passphrase for 'default': ",
        "Passphrase for 'archive': ",
    ]
    assert "TOKENCTL_PASSPHRASE is ignored" in capsys.readouterr().err


def test_shared_passphrase_env_covers_one_encrypted_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("TOKENCTL_PASSPHRASE", "source-pass")

    def _getpass(prompt: str = "") -> str:
        raise AssertionError(prompt)

    monkeypatch.setattr("getpass.getpass", _getpass)
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    assert main(["--profile", "open", "profile", "init"]) == 0
    assert main(["migrate", "--from-profile", "default", "--to-profile", "open"]) == 0
    opened = tmp_path / "tokenctl" / "profiles" / "open" / "tokens.json"
    assert json.loads(opened.read_text(encoding="utf-8"))[0]["value"] == "secret"


def test_two_encrypted_profiles_require_a_terminal_without_shared_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TOKENCTL_PASSPHRASE", raising=False)

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    def _getpass(prompt: str = "") -> str:
        if prompt == "Passphrase for 'default': ":
            return "same-pass"
        if prompt == "Passphrase for 'archive': ":
            return "same-pass"
        raise AssertionError(prompt)

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("getpass.getpass", _getpass)
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    assert main(["--profile", "archive", "profile", "init", "--encryption", "openssl"]) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    monkeypatch.setenv("TOKENCTL_PASSPHRASE", "same-pass")

    def _refuse(prompt: str = "") -> str:
        raise AssertionError(prompt)

    monkeypatch.setattr("getpass.getpass", _refuse)
    assert main(["migrate", "--from-profile", "default", "--to-profile", "archive"]) == 1
    assert "only used when one passphrase is required" in capsys.readouterr().err


def test_rewrap_asks_for_the_current_and_new_passphrase(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("openssl") is None or shutil.which("gpg") is None:
        pytest.skip("openssl and gpg are required")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TOKENCTL_PASSPHRASE", raising=False)

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    prompts: list[str] = []

    def _getpass(prompt: str = "") -> str:
        prompts.append(prompt)
        if prompt in {"Passphrase for 'default': ", "Current passphrase for 'default': "}:
            return "current-pass"
        if prompt == "New passphrase for 'default': ":
            return "new-pass"
        raise AssertionError(prompt)

    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("getpass.getpass", _getpass)
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    prompts.clear()
    monkeypatch.setenv("TOKENCTL_PASSPHRASE", "current-pass")
    assert main(["profile", "set-encryption", "--encryption", "gpg"]) == 0
    assert prompts == [
        "Current passphrase for 'default': ",
        "New passphrase for 'default': ",
    ]
    assert "TOKENCTL_PASSPHRASE is ignored" in capsys.readouterr().err
    profile = tmp_path / "tokenctl" / "profiles" / "default"
    assert not (profile / "tokens.json.enc").exists()
    assert (profile / "tokens.json.gpg").is_file()
    monkeypatch.setenv("TOKENCTL_PASSPHRASE", "new-pass")
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "main", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "secret"


def test_openssl_file_uses_pbkdf2(config_home: Path) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    assert main(["profile", "init", "--encryption", "openssl"]) == 0
    assert main(["add", "--type", "github", "--name", "ci", "--value", "secret"]) == 0
    enc = config_home / "tokenctl" / "profiles" / "default" / "tokens.json.enc"
    proc = subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-d",
            "-pbkdf2",
            "-in",
            str(enc),
            "-pass",
            "pass:test-passphrase",
        ],
        check=False,
        capture_output=True,
    )
    assert proc.returncode == 0
    assert b"secret" in proc.stdout


def test_set_encryption_keeps_new_file_when_config_lands(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    monkeypatch.setenv("TOKENCTL_PASSPHRASE", "test-passphrase")
    assert main(["profile", "init"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "keep-me"]) == 0
    from lupaxa.token_manager.models import ProfileConfig

    real_save = ProfileConfig.save

    def _save_then_fail(self: ProfileConfig, profile_dir: Path) -> None:
        real_save(self, profile_dir)
        raise OSError("directory fsync failed")

    monkeypatch.setattr(ProfileConfig, "save", _save_then_fail)
    assert main(["profile", "set-encryption", "--encryption", "openssl"]) == 0
    capsys.readouterr()
    profile = config_home / "tokenctl" / "profiles" / "default"
    saved = json.loads((profile / "config.json").read_text(encoding="utf-8"))
    assert saved["encryption"] == "openssl"
    assert (profile / "tokens.json.enc").is_file()
    assert not (profile / "tokens.json").exists()
    assert main(["set", "--type", "github", "--name", "main", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "keep-me"
