"""CLI behaviour for plaintext profiles."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from lupaxa.token_manager.cli import main


@pytest.fixture
def config_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("tokenctl ")


def test_add_list_and_set(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    assert (
        main(
            [
                "add",
                "--type",
                "github",
                "--name",
                "main",
                "--value",
                "ghp_secret",
                "--env-var",
                "GITHUB_TOKEN",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["list", "--format", "names"]) == 0
    assert capsys.readouterr().out.strip() == "main"
    assert main(["set", "--type", "github", "--name", "main", "--format", "export"]) == 0
    assert capsys.readouterr().out.strip() == "export GITHUB_TOKEN='ghp_secret'"


def test_same_name_allowed_in_another_type(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    assert main(["add", "--type", "github", "--name", "main", "--value", "a"]) == 0
    assert main(["add", "--type", "aws", "--name", "main", "--value", "b"]) == 0
    capsys.readouterr()
    assert main(["types"]) == 0
    assert capsys.readouterr().out.split() == ["aws", "github"]


def test_duplicate_name_in_type(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    assert main(["add", "--type", "github", "--name", "main", "--value", "a"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "b"]) == 1
    err = capsys.readouterr().err
    assert "already exists" in err


def test_show_hides_value_unless_reveal(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    assert main(["add", "--type", "pypi", "--name", "publish", "--value", "secret"]) == 0
    capsys.readouterr()
    assert main(["show", "--type", "pypi", "--name", "publish"]) == 0
    hidden = json.loads(capsys.readouterr().out)
    assert "value" not in hidden
    assert main(["show", "--type", "pypi", "--name", "publish", "--reveal"]) == 0
    revealed = json.loads(capsys.readouterr().out)
    assert revealed["value"] == "secret"


def test_name_without_type_is_usage_error(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    assert main(["add", "--type", "github", "--name", "main", "--value", "a"]) == 0
    capsys.readouterr()
    assert main(["show", "--name", "main"]) == 2


def test_delete_and_update(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    assert main(["add", "--type", "github", "--name", "main", "--value", "old"]) == 0
    assert (
        main(
            [
                "update",
                "--type",
                "github",
                "--name",
                "main",
                "--value",
                "new",
                "--new-name",
                "prod",
            ]
        )
        == 0
    )
    assert main(["delete", "--type", "github", "--name", "prod"]) == 0
    capsys.readouterr()
    assert main(["list", "--format", "names"]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_migrate_copy_and_move(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    assert (
        main(
            [
                "--profile",
                "default",
                "add",
                "--type",
                "github",
                "--name",
                "main",
                "--value",
                "v",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "migrate",
                "--from-profile",
                "default",
                "--to-profile",
                "secure",
                "--type",
                "github",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["--profile", "default", "list", "--format", "names"]) == 0
    assert capsys.readouterr().out.strip() == "main"
    assert main(["--profile", "secure", "list", "--format", "names"]) == 0
    assert capsys.readouterr().out.strip() == "main"
    assert (
        main(
            [
                "migrate",
                "--from-profile",
                "default",
                "--to-profile",
                "secure",
                "--type",
                "github",
                "--name",
                "main",
                "--move",
                "--overwrite",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["--profile", "default", "list", "--format", "names"]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_quotes_export_value(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    assert main(["add", "--type", "github", "--name", "main", "--value", "a'b"]) == 0
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "main", "--format", "export"]) == 0
    assert capsys.readouterr().out.strip() == """export GITHUB_TOKEN='a'"'"'b'"""


def test_json_hides_value_unless_reveal(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    capsys.readouterr()
    assert main(["list", "--format", "json"]) == 0
    hidden = json.loads(capsys.readouterr().out)
    assert "value" not in hidden[0]
    assert main(["list", "--format", "json", "--reveal"]) == 0
    revealed = json.loads(capsys.readouterr().out)
    assert revealed[0]["value"] == "secret"


def test_add_value_from_stdin(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    monkeypatch.setattr("sys.stdin", io.StringIO("piped-secret\n"))
    assert main(["add", "--type", "github", "--name", "main", "--value", "-"]) == 0
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "main", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "piped-secret"


def test_add_prompts_when_value_omitted(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("sys.stdin", _Tty())
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "prompted-secret")
    assert main(["add", "--type", "github", "--name", "main"]) == 0
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "main", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "prompted-secret"


def test_empty_stdin_value_is_usage_error(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del config_home
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    assert main(["add", "--type", "github", "--name", "main", "--value", "-"]) == 2


def test_list_columns_and_max_width(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    secret = "abcdefghij" * 5
    assert main(["add", "--type", "github", "--name", "main", "--value", secret]) == 0
    capsys.readouterr()
    assert main(["list", "--columns", "name,env_var"]) == 0
    table = capsys.readouterr().out
    assert "Name" in table
    assert "Env var" in table
    assert "Updated" not in table
    assert main(["list", "--columns", "value", "--max-width", "24", "--reveal"]) == 0
    wrapped = capsys.readouterr().out
    assert secret not in wrapped.splitlines()
    assert "abcdefghij" in wrapped


def test_unknown_column_is_usage_error(config_home: Path) -> None:
    del config_home
    assert main(["add", "--type", "github", "--name", "main", "--value", "a"]) == 0
    assert main(["list", "--columns", "nope"]) == 2


def test_migrate_dry_run_writes_nothing(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    assert main(["add", "--type", "github", "--name", "main", "--value", "v"]) == 0
    assert (
        main(
            [
                "migrate",
                "--from-profile",
                "default",
                "--to-profile",
                "secure",
                "--dry-run",
                "--move",
            ]
        )
        == 0
    )
    message = capsys.readouterr().out
    assert "Dry run" in message
    assert main(["--profile", "default", "list", "--format", "names"]) == 0
    assert capsys.readouterr().out.strip() == "main"
    assert main(["--profile", "secure", "list", "--format", "names"]) == 0
    assert capsys.readouterr().out.strip() == ""
