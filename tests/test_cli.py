"""CLI behaviour for plaintext profiles."""

from __future__ import annotations

import io
import json
import os
import re
import time
from multiprocessing import Process
from pathlib import Path

import pytest

from lupaxa.token_manager.cli import main
from lupaxa.token_manager.exceptions import TokenManagerError
from lupaxa.token_manager.store import _same_rows


def _init(*profiles: str) -> None:
    """Create plaintext profiles so later commands have somewhere to write."""
    for name in profiles or ("default",):
        args = ["profile", "init"] if name == "default" else ["--profile", name, "profile", "init"]
        assert main(args) == 0


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
    _init()
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
    _init()
    assert main(["add", "--type", "github", "--name", "main", "--value", "a"]) == 0
    assert main(["add", "--type", "aws", "--name", "main", "--value", "b"]) == 0
    capsys.readouterr()
    assert main(["types"]) == 0
    assert capsys.readouterr().out.split() == ["aws", "github"]


def test_duplicate_name_in_type(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    _init()
    assert main(["add", "--type", "github", "--name", "main", "--value", "a"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "b"]) == 1
    err = capsys.readouterr().err
    assert "already exists" in err


def test_show_hides_value_unless_reveal(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init()
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
    _init()
    assert main(["add", "--type", "github", "--name", "main", "--value", "a"]) == 0
    capsys.readouterr()
    assert main(["show", "--name", "main"]) == 2


def test_delete_and_update(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    _init()
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
    _init("default", "secure")
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
    _init()
    assert main(["add", "--type", "github", "--name", "main", "--value", "a'b"]) == 0
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "main", "--format", "export"]) == 0
    assert capsys.readouterr().out.strip() == """export GITHUB_TOKEN='a'"'"'b'"""


def test_json_hides_value_unless_reveal(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init()
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
    _init()
    monkeypatch.setattr("sys.stdin", io.StringIO("piped-secret\n"))
    assert main(["add", "--type", "github", "--name", "main", "--value", "-"]) == 0
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "main", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "piped-secret"


def test_add_prompts_when_value_omitted(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init()

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
    _init()
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    assert main(["add", "--type", "github", "--name", "main", "--value", "-"]) == 2


def test_list_centers_profile_on_the_top_line(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init()
    assert main(["add", "--type", "pypi", "--name", "publish", "--value", "pypi-secret"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "gh-secret"]) == 0
    capsys.readouterr()
    profile = config_home / "tokenctl" / "profiles" / "default" / "tokens.json"
    rows = json.loads(profile.read_text(encoding="utf-8"))
    for row in rows:
        if row["name"] == "main":
            row["env_var"] = ""
    profile.write_text(json.dumps(rows), encoding="utf-8")
    assert main(["list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    label = " Profile: default (enc: none) "
    tops = [line for line in lines if label in line]
    assert len(tops) == 1
    left, _, right = tops[0].partition(label)
    assert left == "-" * len(left)
    assert right == "-" * len(right)
    assert abs(len(left) - len(right)) <= 1
    type_lines = [line for line in lines if "Token type:" in line]
    assert [line.strip() for line in type_lines] == ["Token type: github", "Token type: pypi"]
    for line in type_lines:
        assert abs(len(line) - len(line.lstrip()) - (len(line) - len(line.rstrip()))) <= 1
    github_at = next(index for index, line in enumerate(lines) if "Token type: github" in line)
    pypi_at = next(index for index, line in enumerate(lines) if "Token type: pypi" in line)
    assert github_at < pypi_at
    assert set(lines[github_at + 1]) == {"-"}
    assert lines[github_at + 2].startswith("Name")
    assert set(lines[github_at + 3]) == {"-"}
    assert set(lines[pypi_at - 1]) == {"-"}
    assert set(lines[pypi_at + 1]) == {"-"}
    assert lines[pypi_at + 2].startswith("Name")
    assert set(lines[pypi_at + 3]) == {"-"}
    main_line = next(line for line in lines if line.startswith("main"))
    publish_line = next(line for line in lines if line.startswith("publish"))
    assert lines.index(main_line) > github_at
    assert lines.index(publish_line) > pypi_at
    assert main_line.index("|") == publish_line.index("|")
    assert [cell.strip() for cell in main_line.split(" | ")][1] == ""
    assert [cell.strip() for cell in publish_line.split(" | ")][1] == "PYPI_TOKEN"


def test_list_columns_and_max_width(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    _init()
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
    _init()
    assert main(["add", "--type", "github", "--name", "main", "--value", "a"]) == 0
    assert main(["list", "--columns", "nope"]) == 2


def test_profile_list_shows_every_profile(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["profile", "list"]) == 0
    assert capsys.readouterr().out.strip() == "No profiles."
    assert not (config_home / "tokenctl").exists()
    assert main(["profile", "init"]) == 0
    assert main(["--profile", "secure", "profile", "init"]) == 0
    config = config_home / "tokenctl" / "profiles" / "secure" / "config.json"
    config.write_text('{"encryption": "gpg"}\n', encoding="utf-8")
    capsys.readouterr()
    assert main(["profile", "list", "--format", "names"]) == 0
    assert capsys.readouterr().out.splitlines() == ["default", "secure"]
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    assert main(["profile", "list"]) == 0
    listed = capsys.readouterr().out
    lines = listed.splitlines()
    plain = [re.sub(r"\033\[[0-9;]*m", "", line) for line in lines]
    assert set(plain[0]) == {"-"}
    assert plain[1].startswith("Name")
    assert plain[1].index("Name") < plain[1].index("Initialised") < plain[1].index("Encryption")
    assert " | " in plain[1]
    assert set(plain[2]) == {"-"}
    assert plain[3].startswith("default") and "yes" in plain[3] and "none" in plain[3]
    assert plain[4].startswith("secure") and "yes" in plain[4] and "gpg" in plain[4]
    assert set(plain[-1]) == {"-"}
    assert "\033[36mName" in lines[1]
    assert "\033[36mInitialised" in lines[1]
    assert "\033[36mEncryption" in lines[1]
    assert "\033[32myes" in lines[3]
    assert "\033[2m | \033[0m" in lines[1]
    assert "\033[33mnone" in lines[3]
    assert "\033[36mgpg" in lines[4]


def test_profile_init_refuses_existing_profile(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    assert main(["profile", "init"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "keep-me"]) == 0
    assert main(["profile", "init", "--encryption", "openssl"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert main(["set", "--type", "github", "--name", "main", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "keep-me"


def test_corrupt_token_file_is_not_replaced(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["profile", "init"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "keep-me"]) == 0
    capsys.readouterr()
    token_file = config_home / "tokenctl" / "profiles" / "default" / "tokens.json"
    token_file.write_text("{}\n", encoding="utf-8")
    assert main(["add", "--type", "github", "--name", "other", "--value", "new"]) == 1
    assert "not a list" in capsys.readouterr().err
    assert token_file.read_text(encoding="utf-8") == "{}\n"


def test_set_encryption_failure_keeps_existing_tokens(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    assert main(["profile", "init"]) == 0
    assert main(["add", "--type", "github", "--name", "main", "--value", "keep-me"]) == 0
    monkeypatch.setattr("lupaxa.token_manager.models.require_encryption", lambda _mode: None)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise TokenManagerError("gpg encrypt failed: boom")

    monkeypatch.setattr("lupaxa.token_manager.crypto.write_gpg", _boom)
    assert main(["profile", "set-encryption", "--encryption", "gpg"]) == 1
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "main", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "keep-me"


def test_move_keeps_source_when_destination_check_fails(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init("default", "secure")
    assert main(["add", "--type", "github", "--name", "main", "--value", "keep-me"]) == 0

    def _reject(_store: object, _expected: object) -> None:
        raise TokenManagerError("destination unreadable")

    monkeypatch.setattr("lupaxa.token_manager.cli._require_stored", _reject)
    assert (
        main(
            [
                "migrate",
                "--from-profile",
                "default",
                "--to-profile",
                "secure",
                "--move",
            ]
        )
        == 1
    )
    capsys.readouterr()
    assert main(["--profile", "default", "list", "--format", "names"]) == 0
    assert capsys.readouterr().out.strip() == "main"


def test_dotenv_quotes_values(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    _init()
    assert main(["add", "--type", "pypi", "--name", "main", "--value", "a b#c"]) == 0
    capsys.readouterr()
    assert main(["set", "--type", "pypi", "--name", "main", "--format", "dotenv"]) == 0
    assert capsys.readouterr().out.strip() == "PYPI_TOKEN='a b#c'"


def test_rejects_unsafe_env_var(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    _init()
    assert (
        main(
            [
                "add",
                "--type",
                "github",
                "--name",
                "main",
                "--value",
                "secret",
                "--env-var",
                "FOO;echo",
            ]
        )
        == 2
    )
    assert "shell identifier" in capsys.readouterr().err


def test_set_refuses_unsafe_stored_env_var(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init()
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    capsys.readouterr()
    token_file = config_home / "tokenctl" / "profiles" / "default" / "tokens.json"
    rows = json.loads(token_file.read_text(encoding="utf-8"))
    rows[0]["env_var"] = "FOO;echo"
    token_file.write_text(json.dumps(rows), encoding="utf-8")
    assert main(["set", "--type", "github", "--name", "main"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "shell identifier" in captured.err


def test_token_files_and_directories_are_private(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init()
    monkeypatch.setattr("lupaxa.token_manager.io.chmod_600", lambda _path: None)
    previous = os.umask(0)
    try:
        assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    finally:
        os.umask(previous)
    root = config_home / "tokenctl"
    profile = root / "profiles" / "default"
    assert root.stat().st_mode & 0o777 == 0o700
    assert profile.parent.stat().st_mode & 0o777 == 0o700
    assert profile.stat().st_mode & 0o777 == 0o700
    assert (profile / "tokens.json").stat().st_mode & 0o777 == 0o600


def test_profile_name_cannot_escape_config_dir(config_home: Path) -> None:
    assert main(["--profile", "../escape", "list"]) == 2
    assert not (config_home / "tokenctl" / "escape").exists()
    assert not (config_home / "escape").exists()


def test_unknown_encryption_mode_is_refused(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init()
    assert main(["add", "--type", "github", "--name", "main", "--value", "keep-me"]) == 0
    profile = config_home / "tokenctl" / "profiles" / "default"
    token_file = profile / "tokens.json"
    before = token_file.read_bytes()
    (profile / "config.json").write_text('{"encryption": "nope"}\n', encoding="utf-8")
    assert main(["list", "--format", "names"]) == 1
    assert "unknown encryption" in capsys.readouterr().err
    assert token_file.read_bytes() == before


def test_invalid_config_json_is_an_error(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["profile", "init"]) == 0
    config = config_home / "tokenctl" / "profiles" / "default" / "config.json"
    config.write_text("{", encoding="utf-8")
    assert main(["list"]) == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_migrate_same_id_refuses_changed_destination(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init("default", "secure")
    assert main(["add", "--type", "github", "--name", "main", "--value", "source-secret"]) == 0
    assert main(["migrate", "--from-profile", "default", "--to-profile", "secure"]) == 0
    assert (
        main(
            [
                "--profile",
                "secure",
                "update",
                "--type",
                "github",
                "--name",
                "main",
                "--value",
                "dest-secret",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["migrate", "--from-profile", "default", "--to-profile", "secure"]) == 1
    assert "overwrite" in capsys.readouterr().err
    assert (
        main(
            [
                "--profile",
                "secure",
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
    assert capsys.readouterr().out.strip() == "dest-secret"


def _lock_child(config_dir: str, flag: str) -> None:
    from lupaxa.token_manager.store import Store

    store = Store(config_dir=Path(config_dir))
    with store.exclusive():
        Path(flag).write_text("in", encoding="utf-8")


def test_profile_lock_blocks_other_process(config_home: Path) -> None:
    from lupaxa.token_manager.store import Store

    assert main(["profile", "init"]) == 0
    root = config_home / "tokenctl"
    store = Store(config_dir=root)
    flag = config_home / "lock-flag"
    with store.exclusive():
        process = Process(target=_lock_child, args=(str(root), str(flag)))
        process.start()
        time.sleep(0.3)
        assert not flag.exists()
    process.join(timeout=2)
    assert process.exitcode == 0
    assert flag.read_text(encoding="utf-8") == "in"


def test_status_lines_are_coloured_on_a_terminal(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    added = capsys.readouterr().out
    assert "\033[32m" in added
    assert "Added token" in added
    assert main(["delete", "--id", "missing"]) == 1
    error = capsys.readouterr().err
    assert error.startswith("\033[31m")
    assert "error:" in error


def test_colour_is_omitted_for_scripts(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    assert main(["add", "--type", "github", "--name", "main", "--value", "a b"]) == 0
    capsys.readouterr()
    assert main(["set", "--type", "github", "--name", "main", "--format", "export"]) == 0
    exported = capsys.readouterr().out
    assert exported.strip() == "export GITHUB_TOKEN='a b'"
    assert "\033" not in exported
    assert main(["list", "--format", "json"]) == 0
    assert "\033" not in capsys.readouterr().out


def test_no_color_disables_status_colour(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init()
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    monkeypatch.setenv("NO_COLOR", "1")
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    assert "\033" not in capsys.readouterr().out


def test_list_uses_info_and_plaintext_warning(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    capsys.readouterr()
    assert main(["list"]) == 0
    table = capsys.readouterr().out
    assert "\033[97mProfile:" in table
    assert "\033[97mToken type:" in table
    assert "\033[36mName" in table
    assert "\033[2m | \033[0m" in table
    assert "\033[33m" in table
    assert "enc: none" in table
    assert "secret" not in table


def test_dry_run_is_info(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init("default", "secure")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    assert main(["add", "--type", "github", "--name", "main", "--value", "v"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "migrate",
                "--from-profile",
                "default",
                "--to-profile",
                "secure",
                "--dry-run",
            ]
        )
        == 0
    )
    message = capsys.readouterr().out
    assert "\033[36m" in message
    assert "Dry run" in message


def test_help_colours_command_names(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    assert main(["help"]) == 0
    text = capsys.readouterr().out
    assert "\033[36mlist\033[0m" in text
    assert "\033[36mtypes\033[0m" in text
    assert "\033[36madd\033[0m" in text
    assert not (config_home / "tokenctl").exists()


def test_help_for_a_command_colours_its_options(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    assert main(["help", "list"]) == 0
    text = capsys.readouterr().out
    assert "\033[36m--format\033[0m" in text
    assert "\033[36m--reveal\033[0m" in text
    assert "Output format" in text


def test_help_stays_plain_when_colour_is_disabled(
    config_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    monkeypatch.setenv("NO_COLOR", "1")
    assert main(["help"]) == 0
    text = capsys.readouterr().out
    assert "list" in text
    assert "\033" not in text


def test_update_without_a_change_does_not_rewrite(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init()
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    token_file = config_home / "tokenctl" / "profiles" / "default" / "tokens.json"
    before = token_file.read_bytes()
    capsys.readouterr()
    assert main(["update", "--type", "github", "--name", "main"]) == 2
    assert "needs" in capsys.readouterr().err
    assert token_file.read_bytes() == before
    assert main(["update", "--type", "github", "--name", "main", "--new-name", "main"]) == 0
    assert "Nothing changed." in capsys.readouterr().out
    assert token_file.read_bytes() == before


def test_profile_list_rejects_a_selected_profile(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--profile", "secure", "profile", "list"]) == 2
    assert "Omit --profile" in capsys.readouterr().err
    assert not (config_home / "tokenctl").exists()


def test_legacy_profile_without_config_stays_available(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = config_home / "tokenctl" / "profiles" / "default"
    profile.mkdir(parents=True)
    profile.joinpath("tokens.json").write_text(
        json.dumps(
            [
                {
                    "id": "1",
                    "type": "github",
                    "name": "main",
                    "value": "secret",
                    "env_var": "GITHUB_TOKEN",
                    "created_at": "2020-01-01T00:00:00Z",
                    "updated_at": "2020-01-01T00:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )
    assert main(["profile", "list", "--format", "names"]) == 0
    assert capsys.readouterr().out.strip() == "default"
    assert main(["set", "--type", "github", "--name", "main", "--format", "value"]) == 0
    assert capsys.readouterr().out.strip() == "secret"
    assert not (profile / "config.json").exists()
    assert main(["profile", "init"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert main(["update", "--type", "github", "--name", "main", "--new-name", "prod"]) == 0
    saved = json.loads((profile / "config.json").read_text(encoding="utf-8"))
    assert saved["encryption"] == "none"


def test_profile_update_writes_config_for_a_legacy_profile(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = config_home / "tokenctl" / "profiles" / "default"
    profile.mkdir(parents=True)
    token_file = profile / "tokens.json"
    token_file.write_text("[]\n", encoding="utf-8")
    before = token_file.read_bytes()
    assert main(["profile", "update"]) == 0
    assert "updated" in capsys.readouterr().out
    assert token_file.read_bytes() == before
    saved = json.loads((profile / "config.json").read_text(encoding="utf-8"))
    assert saved == {"encryption": "none"}
    config_before = (profile / "config.json").read_bytes()
    assert main(["profile", "update"]) == 0
    assert "already in the current format" in capsys.readouterr().out
    assert (profile / "config.json").read_bytes() == config_before
    assert token_file.read_bytes() == before

    locked = config_home / "tokenctl" / "profiles" / "locked"
    locked.mkdir()
    envelope = locked / "tokens.json.gpg"
    envelope.write_bytes(b"envelope")
    assert main(["--profile", "locked", "profile", "update"]) == 0
    locked_config = json.loads((locked / "config.json").read_text(encoding="utf-8"))
    assert locked_config == {"encryption": "gpg"}
    assert envelope.read_bytes() == b"envelope"

    assert main(["--profile", "missing", "profile", "update"]) == 2
    assert "does not exist" in capsys.readouterr().err
    assert not (config_home / "tokenctl" / "profiles" / "missing").exists()


def test_legacy_encryption_is_taken_from_the_token_file(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = config_home / "tokenctl" / "profiles" / "locked"
    profile.mkdir(parents=True)
    (profile / "tokens.json.gpg").write_bytes(b"envelope")
    assert main(["profile", "list", "--format", "json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed == [{"profile": "locked", "initialised": True, "encryption": "gpg"}]
    assert not (profile / "config.json").exists()


def test_missing_profile_is_not_created(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--profile", "typo", "list"]) == 2
    assert "does not exist" in capsys.readouterr().err
    assert not (config_home / "tokenctl").exists()
    assert main(["migrate", "--from-profile", "default", "--to-profile", "archive"]) == 2
    assert not (config_home / "tokenctl" / "profiles" / "archive").exists()


def test_profile_list_shows_uninitialized_directories(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init()
    capsys.readouterr()
    stray = config_home / "tokenctl" / "profiles" / "scratch"
    stray.mkdir()
    assert main(["profile", "list", "--format", "names"]) == 0
    assert capsys.readouterr().out.splitlines() == ["default", "scratch"]
    assert main(["profile", "list"]) == 0
    plain = [re.sub(r"\033\[[0-9;]*m", "", line) for line in capsys.readouterr().out.splitlines()]
    scratch = next(line for line in plain if line.startswith("scratch"))
    cells = [cell.strip() for cell in scratch.split(" | ")]
    assert cells[1] == "no"
    assert cells[2] == ""


def test_update_can_clear_env_var(config_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    del config_home
    _init()
    assert main(["add", "--type", "github", "--name", "main", "--value", "secret"]) == 0
    assert main(["update", "--type", "github", "--name", "main", "--env-var", ""]) == 0
    capsys.readouterr()
    assert main(["list", "--columns", "name,env_var"]) == 0
    table = capsys.readouterr().out
    main_line = next(line for line in table.splitlines() if line.startswith("main"))
    assert [cell.strip() for cell in main_line.split(" | ")][1] == ""


def test_read_back_checks_env_var() -> None:
    row = {
        "id": "1",
        "type": "github",
        "name": "main",
        "value": "secret",
        "env_var": "GITHUB_TOKEN",
    }
    changed = dict(row, env_var="")
    assert _same_rows([row], [row])
    assert not _same_rows([row], [changed])


def test_help_unknown_command_is_an_error(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    assert main(["help", "nope"]) == 2
    assert "unknown command" in capsys.readouterr().err


def test_migrate_dry_run_writes_nothing(
    config_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del config_home
    _init("default", "secure")
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
