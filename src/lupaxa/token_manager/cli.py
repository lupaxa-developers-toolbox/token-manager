"""Command-line interface for lupaxa.token_manager."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import textwrap
import uuid
from collections.abc import Sequence

from lupaxa.token_manager.exceptions import TokenManagerError
from lupaxa.token_manager.models import Token, now_iso
from lupaxa.token_manager.render import parse_columns, render_pretty_table
from lupaxa.token_manager.secrets import resolve_secret
from lupaxa.token_manager.store import DEFAULT_PROFILE, Store
from lupaxa.token_manager.version import __version__


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
    env_var = args.env_var or f"{args.type.upper()}_TOKEN"
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
    print(f"Added token '{args.name}' (id: {token_id}, type: {wanted}, env: {env_var}).")


def cmd_update(store: Store, args: argparse.Namespace) -> None:
    if not args.id and not args.name:
        raise TokenManagerError(
            "update requires --id ID OR (--name NAME --type TYPE)",
            exit_code=2,
        )
    tokens = store.load()
    token = _find_token(tokens, args.id, args.name, args.type)
    if token is None:
        raise TokenManagerError("No matching token found.")
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
    if args.env_var:
        token.env_var = args.env_var
    token.updated_at = now_iso()
    store.save(tokens)
    print("Updated token.")


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
    print(f"Deleted {removed} token(s).")


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


def cmd_set(store: Store, args: argparse.Namespace) -> None:
    if not args.id and not (args.name and args.type):
        raise TokenManagerError(
            "set requires --id ID OR (--name NAME --type TYPE)",
            exit_code=2,
        )
    token = _find_token(store.load(), args.id, args.name, args.type)
    if token is None:
        raise TokenManagerError("Token not found.")
    env_name = args.env_var or token.env_var or f"{(token.type or 'token').upper()}_TOKEN"
    if args.format == "value":
        print(token.value)
    elif args.format == "dotenv":
        print(f"{env_name}={token.value}")
    else:
        print(f"export {env_name}={_shquote(token.value)}")


def cmd_profile_init(store: Store, args: argparse.Namespace) -> None:
    store.init_profile(args.encryption or "none")
    print(f"Profile '{store.profile}' initialized (encryption: {store.config.encryption}).")


def cmd_profile_show(store: Store, args: argparse.Namespace) -> None:
    del args
    print(json.dumps({"profile": store.profile, "encryption": store.config.encryption}, indent=2))


def cmd_profile_set_encryption(store: Store, args: argparse.Namespace) -> None:
    store.set_encryption(args.encryption)
    print(f"Profile '{store.profile}' encryption set to: {store.config.encryption}")


def cmd_migrate(args: argparse.Namespace) -> None:
    if args.from_profile == args.to_profile:
        raise TokenManagerError(
            "Source and destination profiles are the same; nothing to do.",
            exit_code=2,
        )
    source = Store(profile=args.from_profile)
    destination = Store(profile=args.to_profile)
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
            same_key = existing.type == token.type and existing.name == token.name
            if same_key and existing.id != token.id:
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
            print(
                f"Dry run: would migrate {moved} token(s) from '{args.from_profile}' "
                f"to '{args.to_profile}' and remove {moved} from source."
            )
        else:
            print(
                f"Dry run: would migrate {moved} token(s) from '{args.from_profile}' "
                f"to '{args.to_profile}' (source left intact)."
            )
        return

    destination.save(destination_tokens)
    if args.move:
        selected_keys = {(token.type, token.name) for token in selected}
        remaining = [
            token for token in source_tokens if (token.type, token.name) not in selected_keys
        ]
        removed = len(source_tokens) - len(remaining)
        source.save(remaining)
        print(
            f"Migrated {moved} token(s) from '{args.from_profile}' to '{args.to_profile}' "
            f"and removed {removed} from source."
        )
        return
    print(
        f"Migrated {moved} token(s) from '{args.from_profile}' to '{args.to_profile}' "
        "(source left intact)."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tokenctl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        default=DEFAULT_PROFILE,
        help="Profile name (default: default)",
    )

    sub = parser.add_subparsers(dest="cmd")

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

    types_cmd = sub.add_parser("types", help="List unique token types")
    types_cmd.set_defaults(func=cmd_types)

    add_cmd = sub.add_parser("add", help="Add a new token")
    add_cmd.add_argument("--type", required=True, help="Token type (for example github, pypi)")
    add_cmd.add_argument("--name", required=True, help="Unique name within the type")
    add_cmd.add_argument(
        "--value",
        help="Secret value. Omit to prompt, or pass - to read stdin.",
    )
    add_cmd.add_argument("--env-var", help="Environment variable name (default TYPE_TOKEN)")
    add_cmd.set_defaults(func=cmd_add)

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
    update_cmd.add_argument("--env-var", help="New env var name")
    update_cmd.set_defaults(func=cmd_update)

    delete_cmd = sub.add_parser("delete", help="Delete a token")
    delete_cmd.add_argument("--id", help="Token id")
    delete_cmd.add_argument("--name", help="Token name (requires --type if used)")
    delete_cmd.add_argument("--type", help="Token type for lookup when using --name")
    delete_cmd.set_defaults(func=cmd_delete)

    show_cmd = sub.add_parser("show", help="Show token metadata")
    show_cmd.add_argument("--id", help="Token id")
    show_cmd.add_argument("--name", help="Token name (requires --type if used)")
    show_cmd.add_argument("--type", help="Token type for lookup when using --name")
    show_cmd.add_argument("--reveal", action="store_true", help="Include secret value")
    show_cmd.set_defaults(func=cmd_show)

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

    profile_cmd = sub.add_parser("profile", help="Profile management")
    profile_sub = profile_cmd.add_subparsers(dest="pcmd", required=True)

    init_cmd = profile_sub.add_parser("init", help="Create or re-init a profile")
    init_cmd.add_argument("--encryption", choices=["none", "gpg", "openssl"], default="none")
    init_cmd.set_defaults(func=cmd_profile_init)

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
        help="Print what would change without writing either profile",
    )
    migrate_cmd.set_defaults(func=cmd_migrate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.version:
        print(f"tokenctl {__version__}")
        return 0
    if not args.cmd:
        parser.error("a command is required")
    try:
        if args.cmd == "migrate":
            cmd_migrate(args)
        else:
            store = Store(profile=args.profile)
            args.func(store, args)
    except TokenManagerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError:
        return 0
    return 0
