"""Command-line interface for lupaxa.token_manager."""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import textwrap
import uuid
from collections.abc import Sequence
from contextlib import ExitStack
from typing import Any, NoReturn

from lupaxa.token_manager.crypto import (
    PASSPHRASE_ENV,
    clear_passphrase_cache,
    require_separate_passphrases,
)
from lupaxa.token_manager.exceptions import TokenManagerError
from lupaxa.token_manager.models import Token, now_iso
from lupaxa.token_manager.render import parse_columns, render_pretty_table, render_profile_table
from lupaxa.token_manager.secrets import resolve_secret
from lupaxa.token_manager.store import DEFAULT_PROFILE, Store, list_profiles
from lupaxa.token_manager.style import (
    colour_enabled,
    error,
    info,
    paint,
    paint_syntax,
    success,
    warning,
)
from lupaxa.token_manager.version import __version__

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _find_token(
    tokens: list[Token],
    token_id: str | None,
    name: str | None,
    type_for_name: str | None,
) -> Token | None:
    """Find a token by id, or by name plus type."""
    if token_id:
        for token in tokens:
            if token.id == token_id:
                return token
        return None
    if name:
        if not type_for_name:
            raise TokenManagerError(
                "When using --name, you must also provide --type.",
                exit_code=2,
            )
        wanted = type_for_name.lower()
        for token in tokens:
            if token.name == name and token.type == wanted:
                return token
    return None


def _select_for_migration(
    src_tokens: list[Token],
    type_filter: str | None,
    name_filter: str | None,
) -> list[Token]:
    if name_filter and not type_filter:
        raise TokenManagerError(
            "When using --name for migration, you must also provide --type.",
            exit_code=2,
        )
    selected = src_tokens
    if type_filter:
        wanted = type_filter.lower()
        selected = [token for token in selected if token.type == wanted]
    if name_filter:
        selected = [token for token in selected if token.name == name_filter]
    return selected


def cmd_list(store: Store, args: argparse.Namespace) -> None:
    tokens = store.load()
    if args.type:
        wanted = args.type.lower()
        tokens = [token for token in tokens if token.type == wanted]
    columns = parse_columns(args.columns)
    if args.format == "names":
        for token in tokens:
            print(token.name)
        return
    if args.format == "json":
        if args.reveal:
            payload = [dataclasses.asdict(token) for token in tokens]
        else:
            payload = [token.to_public() for token in tokens]
        print(json.dumps(payload, indent=2))
        return
    sys.stdout.write(
        render_pretty_table(
            tokens,
            store.profile,
            store.config.encryption,
            reveal=args.reveal,
            columns=columns,
            max_width=args.max_width,
        )
    )


def cmd_types(store: Store, args: argparse.Namespace) -> None:
    del args
    types = sorted({token.type for token in store.load() if token.type})
    for token_type in types:
        print(token_type)


def cmd_add(store: Store, args: argparse.Namespace) -> None:
    tokens = store.load()
    wanted = args.type.lower()
    if any(token.name == args.name and token.type == wanted for token in tokens):
        raise TokenManagerError(f"A token named '{args.name}' already exists in type '{wanted}'.")
    token_id = str(uuid.uuid4())
    now = now_iso()
    env_var = _require_env_name(args.env_var or f"{args.type.upper()}_TOKEN")
    secret = resolve_secret(args.value)
    tokens.append(
        Token(
            id=token_id,
            type=wanted,
            name=args.name,
            value=secret,
            env_var=env_var,
            created_at=now,
            updated_at=now,
        )
    )
    store.save(tokens)
    success(f"Added token '{args.name}' (id: {token_id}, type: {wanted}, env: {env_var}).")


def cmd_update(store: Store, args: argparse.Namespace) -> None:
    if not args.id and not args.name:
        raise TokenManagerError(
            "update requires --id ID OR (--name NAME --type TYPE)",
            exit_code=2,
        )
    if (
        args.new_type is None
        and args.new_name is None
        and args.value is None
        and args.env_var is None
    ):
        raise TokenManagerError(
            "update needs --new-type, --new-name, --value, or --env-var.",
            exit_code=2,
        )
    tokens = store.load()
    token = _find_token(tokens, args.id, args.name, args.type)
    if token is None:
        raise TokenManagerError("No matching token found.")
    before = (token.type, token.name, token.value, token.env_var)
    new_name = args.new_name or token.name
    if args.new_type:
        new_type = args.new_type.lower()
        clash = any(
            other.id != token.id and other.name == new_name and other.type == new_type
            for other in tokens
        )
        if clash:
            raise TokenManagerError(
                f"A token named '{new_name}' already exists in type '{new_type}'."
            )
        token.type = new_type
    if args.new_name:
        clash = any(
            other.id != token.id and other.name == args.new_name and other.type == token.type
            for other in tokens
        )
        if clash:
            raise TokenManagerError(
                f"A token named '{args.new_name}' already exists in type '{token.type}'."
            )
        token.name = args.new_name
    if args.value is not None:
        token.value = resolve_secret(args.value)
    if args.env_var is not None:
        token.env_var = "" if args.env_var == "" else _require_env_name(args.env_var)
    if (token.type, token.name, token.value, token.env_var) == before:
        info("Nothing changed.")
        return
    token.updated_at = now_iso()
    store.save(tokens)
    success("Updated token.")


def cmd_delete(store: Store, args: argparse.Namespace) -> None:
    if not args.id and not (args.name and args.type):
        raise TokenManagerError(
            "delete requires --id ID OR (--name NAME --type TYPE)",
            exit_code=2,
        )
    tokens = store.load()
    before = len(tokens)
    if args.id:
        tokens = [token for token in tokens if token.id != args.id]
    else:
        wanted = args.type.lower()
        tokens = [
            token for token in tokens if not (token.name == args.name and token.type == wanted)
        ]
    removed = before - len(tokens)
    if removed == 0:
        raise TokenManagerError("No matching token found to delete.")
    store.save(tokens)
    success(f"Deleted {removed} token(s).")


def cmd_show(store: Store, args: argparse.Namespace) -> None:
    if not args.id and not (args.name and args.type):
        raise TokenManagerError(
            "show requires --id ID OR (--name NAME --type TYPE)",
            exit_code=2,
        )
    token = _find_token(store.load(), args.id, args.name, args.type)
    if token is None:
        raise TokenManagerError("Token not found.")
    payload = dataclasses.asdict(token) if args.reveal else token.to_public()
    print(json.dumps(payload, indent=2))


def _shquote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _require_env_name(name: str) -> str:
    """Reject a variable name that ``source`` would treat as shell code."""
    if not _ENV_NAME.fullmatch(name):
        raise TokenManagerError(
            f"Environment variable name '{name}' is not a shell identifier.",
            exit_code=2,
        )
    return name


def cmd_set(store: Store, args: argparse.Namespace) -> None:
    if not args.id and not (args.name and args.type):
        raise TokenManagerError(
            "set requires --id ID OR (--name NAME --type TYPE)",
            exit_code=2,
        )
    token = _find_token(store.load(), args.id, args.name, args.type)
    if token is None:
        raise TokenManagerError("Token not found.")
    env_name = _require_env_name(
        args.env_var or token.env_var or f"{(token.type or 'token').upper()}_TOKEN"
    )
    if args.format == "value":
        print(token.value)
    elif args.format == "dotenv":
        print(f"{env_name}={_shquote(token.value)}")
    else:
        print(f"export {env_name}={_shquote(token.value)}")


def cmd_profile_init(store: Store, args: argparse.Namespace) -> None:
    store.init_profile(args.encryption or "none")
    success(f"Profile '{store.profile}' initialized (encryption: {store.config.encryption}).")


def cmd_profile_list(args: argparse.Namespace) -> None:
    """Print every profile. Does not create a profile directory."""
    if args.profile is not None:
        raise TokenManagerError(
            "profile list shows every profile. Omit --profile.",
            exit_code=2,
        )
    profiles = list_profiles()
    if args.format == "names":
        for name, _ready, _encryption in profiles:
            print(name)
        return
    if args.format == "json":
        payload = [
            {"profile": name, "initialised": ready, "encryption": encryption}
            for name, ready, encryption in profiles
        ]
        print(json.dumps(payload, indent=2))
        return
    print(render_profile_table(profiles), end="")


def cmd_profile_update(store: Store, args: argparse.Namespace) -> None:
    del args
    if store.update_profile():
        success(f"Profile '{store.profile}' updated (encryption: {store.config.encryption}).")
        return
    info(
        f"Profile '{store.profile}' is already in the current format "
        f"(encryption: {store.config.encryption})."
    )


def cmd_profile_show(store: Store, args: argparse.Namespace) -> None:
    del args
    print(json.dumps({"profile": store.profile, "encryption": store.config.encryption}, indent=2))


def cmd_profile_set_encryption(store: Store, args: argparse.Namespace) -> None:
    store.set_encryption(args.encryption)
    success(f"Profile '{store.profile}' encryption set to: {store.config.encryption}")


def _require_stored(store: Store, expected: list[Token]) -> None:
    """Raise when ``expected`` tokens are not readable from ``store``."""
    found = {
        (token.type, token.name, token.id, token.value, token.env_var) for token in store.load()
    }
    missing = [
        token
        for token in expected
        if (token.type, token.name, token.id, token.value, token.env_var) not in found
    ]
    if missing:
        raise TokenManagerError(
            "Destination did not store every migrated token. The source profile was left unchanged."
        )


def cmd_migrate(args: argparse.Namespace) -> None:
    if args.from_profile == args.to_profile:
        raise TokenManagerError(
            "Source and destination profiles are the same; nothing to do.",
            exit_code=2,
        )
    source = Store(profile=args.from_profile)
    destination = Store(profile=args.to_profile)
    with ExitStack() as stack:
        ordered = sorted((source, destination), key=lambda item: str(item.profile_dir))
        for store in ordered:
            stack.enter_context(store.exclusive())
        _migrate_locked(source, destination, args)


def _migrate_locked(source: Store, destination: Store, args: argparse.Namespace) -> None:
    both_encrypted = source.config.encryption != "none" and destination.config.encryption != "none"
    if both_encrypted and require_separate_passphrases():
        warning(f"{PASSPHRASE_ENV} is ignored because both profiles are encrypted.")
    reads_encrypted = source.config.encryption != "none" or destination.config.encryption != "none"
    if args.dry_run and reads_encrypted:
        info("Dry run reads both profiles. An encrypted profile still asks for its passphrase.")
    source_tokens = source.load()
    if not source_tokens:
        raise TokenManagerError(f"No tokens in source profile '{args.from_profile}'.")
    selected = _select_for_migration(source_tokens, args.type, args.name)
    if not selected:
        if args.name:
            scope = f"type='{args.type}' and name='{args.name}'"
        elif args.type:
            scope = f"type='{args.type}'"
        else:
            scope = "all"
        raise TokenManagerError(
            f"No tokens matched selection ({scope}) in profile '{args.from_profile}'."
        )

    destination_tokens = destination.load()
    conflicts: list[tuple[str, str]] = []
    for token in selected:
        for existing in destination_tokens:
            same_id = existing.id == token.id
            same_key = existing.type == token.type and existing.name == token.name
            changed = (
                existing.type != token.type
                or existing.name != token.name
                or existing.value != token.value
                or existing.env_var != token.env_var
            )
            if (same_id and changed) or (same_key and not same_id):
                conflicts.append((token.type, token.name))
                break
    if conflicts and not args.overwrite:
        pretty = ", ".join(f"{token_type}:{name}" for token_type, name in conflicts)
        raise TokenManagerError(
            f"Conflicts in destination profile '{args.to_profile}' for: {pretty}. "
            "Use --overwrite to replace destination tokens with the source versions."
        )
    if args.overwrite:
        remove_keys = set(conflicts)
        destination_tokens = [
            existing
            for existing in destination_tokens
            if (existing.type, existing.name) not in remove_keys
        ]

    existing_ids = {existing.id for existing in destination_tokens}
    to_add: list[Token] = []
    for token in selected:
        if token.id in existing_ids:
            for index, existing in enumerate(destination_tokens):
                if existing.id == token.id:
                    destination_tokens[index] = token
                    break
        else:
            to_add.append(token)
    destination_tokens.extend(to_add)

    moved = len(selected)
    if args.dry_run:
        if args.move:
            info(
                f"Dry run: would migrate {moved} token(s) from '{args.from_profile}' "
                f"to '{args.to_profile}' and remove {moved} from source."
            )
        else:
            info(
                f"Dry run: would migrate {moved} token(s) from '{args.from_profile}' "
                f"to '{args.to_profile}' (source left intact)."
            )
        return

    destination.save(destination_tokens)
    _require_stored(destination, selected)
    if args.move:
        selected_keys = {(token.type, token.name) for token in selected}
        remaining = [
            token for token in source_tokens if (token.type, token.name) not in selected_keys
        ]
        removed = len(source_tokens) - len(remaining)
        source.save(remaining)
        success(
            f"Migrated {moved} token(s) from '{args.from_profile}' to '{args.to_profile}' "
            f"and removed {removed} from source."
        )
        return
    success(
        f"Migrated {moved} token(s) from '{args.from_profile}' to '{args.to_profile}' "
        "(source left intact)."
    )


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Help formatter that colours command names, flags, and metavars."""

    def start_section(self, heading: str | None) -> None:
        if heading and colour_enabled(sys.stdout):
            heading = paint(heading, "yellow", stream=sys.stdout)
        super().start_section(heading)

    def _format_usage(self, usage, actions, groups, prefix):  # type: ignore[no-untyped-def]
        text = super()._format_usage(usage, actions, groups, prefix)
        if not colour_enabled(sys.stdout) or not text.startswith("usage:"):
            return text
        return paint("usage:", "yellow", stream=sys.stdout) + paint_syntax(text[len("usage:") :])

    def _format_action(self, action: argparse.Action) -> str:
        help_position = min(self._action_max_length + 2, self._max_help_position)
        help_width = max(self._width - help_position, 11)
        action_width = help_position - self._current_indent - 2
        invocation = self._format_action_invocation(action)
        shown = paint_syntax(invocation)
        indent_first = 0

        if not action.help:
            action_header = f"{'':{self._current_indent}}{shown}\n"
        elif len(invocation) <= action_width:
            pad = action_width - len(invocation)
            action_header = f"{'':{self._current_indent}}{shown}{'':{pad}}  "
        else:
            action_header = f"{'':{self._current_indent}}{shown}\n"
            indent_first = help_position

        parts = [action_header]
        if action.help and action.help.strip():
            help_text = self._expand_help(action)
            if help_text:
                help_lines = self._split_lines(help_text, help_width)
                parts.append(f"{'':{indent_first}}{help_lines[0]}\n")
                for line in help_lines[1:]:
                    parts.append(f"{'':{help_position}}{line}\n")
        elif not action_header.endswith("\n"):
            parts.append("\n")

        for subaction in self._iter_indented_subactions(action):
            parts.append(self._format_action(subaction))
        return self._join_parts(parts)


class _Parser(argparse.ArgumentParser):
    """Argument parser that prints usage errors in red and colours help."""

    command_parsers: dict[str, argparse.ArgumentParser]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("formatter_class", _HelpFormatter)
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        error(f"error: {message}")
        self.exit(2)


def build_parser() -> _Parser:
    parser = _Parser(
        prog="tokenctl",
        formatter_class=_HelpFormatter,
        description=textwrap.dedent(
            """\
            Manage API tokens in named profiles, with optional encryption.

            Names are unique within a type. Selecting by --name also needs --type.
            """
        ),
    )
    parser.add_argument("--version", action="store_true", help="Show version information and exit.")
    parser.add_argument(
        "--profile",
        default=None,
        help="Profile name (default: default). Not used with profile list.",
    )

    sub = parser.add_subparsers(dest="cmd", parser_class=_Parser)
    command_parsers: dict[str, argparse.ArgumentParser] = {}

    list_cmd = sub.add_parser("list", help="List tokens (pretty, json, or names)")
    list_cmd.add_argument("--type", help="Filter by type (for example github, pypi)")
    list_cmd.add_argument(
        "--format",
        choices=["pretty", "json", "names"],
        default="pretty",
        help="Output format",
    )
    list_cmd.add_argument(
        "--reveal",
        action="store_true",
        help="Show secret values in the table and in JSON",
    )
    list_cmd.add_argument(
        "--columns",
        help="Comma-separated columns: name, env_var, id, updated, created, value, type",
    )
    list_cmd.add_argument(
        "--max-width",
        type=int,
        help="Wrap the table to this many characters",
    )
    list_cmd.set_defaults(func=cmd_list)
    command_parsers["list"] = list_cmd

    types_cmd = sub.add_parser("types", help="List unique token types")
    types_cmd.set_defaults(func=cmd_types)
    command_parsers["types"] = types_cmd

    add_cmd = sub.add_parser("add", help="Add a new token")
    add_cmd.add_argument("--type", required=True, help="Token type (for example github, pypi)")
    add_cmd.add_argument("--name", required=True, help="Unique name within the type")
    add_cmd.add_argument(
        "--value",
        help="Secret value. Omit to prompt, or pass - to read stdin.",
    )
    add_cmd.add_argument("--env-var", help="Environment variable name (default TYPE_TOKEN)")
    add_cmd.set_defaults(func=cmd_add)
    command_parsers["add"] = add_cmd

    update_cmd = sub.add_parser("update", help="Update an existing token")
    update_cmd.add_argument("--id", help="Token id")
    update_cmd.add_argument("--name", help="Token name (requires --type if used)")
    update_cmd.add_argument("--type", help="Token type for lookup when using --name")
    update_cmd.add_argument("--new-type", help="Change token type to NEW_TYPE")
    update_cmd.add_argument("--new-name", help="Rename token to NEW_NAME")
    update_cmd.add_argument(
        "--value",
        help="New secret value. Pass - to read stdin.",
    )
    update_cmd.add_argument(
        "--env-var",
        help="New env var name. An empty string clears it.",
    )
    update_cmd.set_defaults(func=cmd_update)
    command_parsers["update"] = update_cmd

    delete_cmd = sub.add_parser("delete", help="Delete a token")
    delete_cmd.add_argument("--id", help="Token id")
    delete_cmd.add_argument("--name", help="Token name (requires --type if used)")
    delete_cmd.add_argument("--type", help="Token type for lookup when using --name")
    delete_cmd.set_defaults(func=cmd_delete)
    command_parsers["delete"] = delete_cmd

    show_cmd = sub.add_parser("show", help="Show token metadata")
    show_cmd.add_argument("--id", help="Token id")
    show_cmd.add_argument("--name", help="Token name (requires --type if used)")
    show_cmd.add_argument("--type", help="Token type for lookup when using --name")
    show_cmd.add_argument("--reveal", action="store_true", help="Include secret value")
    show_cmd.set_defaults(func=cmd_show)
    command_parsers["show"] = show_cmd

    set_cmd = sub.add_parser("set", help="Emit shell-friendly output for the token")
    set_cmd.add_argument("--id", help="Token id")
    set_cmd.add_argument("--name", help="Token name (requires --type if used)")
    set_cmd.add_argument("--type", help="Token type for lookup when using --name")
    set_cmd.add_argument("--env-var", help="Override env var name")
    set_cmd.add_argument(
        "--format",
        choices=["export", "dotenv", "value"],
        default="export",
        help="Output format (default: export)",
    )
    set_cmd.set_defaults(func=cmd_set)
    command_parsers["set"] = set_cmd

    profile_cmd = sub.add_parser("profile", help="Profile management")
    command_parsers["profile"] = profile_cmd
    profile_sub = profile_cmd.add_subparsers(dest="pcmd", required=True, parser_class=_Parser)

    init_cmd = profile_sub.add_parser("init", help="Create a profile")
    init_cmd.add_argument("--encryption", choices=["none", "gpg", "openssl"], default="none")
    init_cmd.set_defaults(func=cmd_profile_init)

    profile_update = profile_sub.add_parser("update", help="Write config.json for a legacy profile")
    profile_update.set_defaults(func=cmd_profile_update)

    profile_list = profile_sub.add_parser("list", help="List every profile")
    profile_list.add_argument(
        "--format",
        choices=["pretty", "json", "names"],
        default="pretty",
        help="Output format",
    )
    profile_list.set_defaults(func=cmd_profile_list)

    profile_show = profile_sub.add_parser("show", help="Show profile config")
    profile_show.set_defaults(func=cmd_profile_show)

    enc_cmd = profile_sub.add_parser("set-encryption", help="Change profile encryption mode")
    enc_cmd.add_argument("--encryption", required=True, choices=["none", "gpg", "openssl"])
    enc_cmd.set_defaults(func=cmd_profile_set_encryption)

    migrate_cmd = sub.add_parser("migrate", help="Copy or move tokens between profiles")
    migrate_cmd.add_argument("--from-profile", required=True, help="Source profile")
    migrate_cmd.add_argument("--to-profile", required=True, help="Destination profile")
    migrate_cmd.add_argument("--type", help="Filter: migrate only this type")
    migrate_cmd.add_argument("--name", help="Filter: migrate only this name (requires --type)")
    migrate_cmd.add_argument("--move", action="store_true", help="Delete from source after copy")
    migrate_cmd.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite destination tokens that share type and name",
    )
    migrate_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the change without writing. Encrypted profiles are still read.",
    )
    migrate_cmd.set_defaults(func=cmd_migrate)
    command_parsers["migrate"] = migrate_cmd

    help_cmd = sub.add_parser("help", help="Show help for a command")
    help_cmd.add_argument("topic", nargs="?", help="Command to describe")
    command_parsers["help"] = help_cmd
    parser.command_parsers = command_parsers

    return parser


def cmd_help(parser: _Parser, topic: str | None) -> int:
    """Print top-level help, or help for one command."""
    if not topic:
        parser.print_help()
        return 0
    target = parser.command_parsers.get(topic)
    if target is None:
        error(f"error: unknown command '{topic}'.")
        return 2
    target.print_help()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    clear_passphrase_cache()
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.version:
        info(f"tokenctl {__version__}")
        return 0
    if not args.cmd:
        parser.error("a command is required")
    if args.cmd == "help":
        return cmd_help(parser, args.topic)
    try:
        if args.cmd == "migrate":
            cmd_migrate(args)
        elif args.cmd == "profile" and args.pcmd == "list":
            cmd_profile_list(args)
        else:
            creating = args.cmd == "profile" and args.pcmd == "init"
            store = Store(profile=args.profile or DEFAULT_PROFILE, create=creating)
            with store.exclusive():
                args.func(store, args)
    except TokenManagerError as exc:
        error(f"error: {exc}")
        return exc.exit_code
    except BrokenPipeError:
        return 0
    return 0
