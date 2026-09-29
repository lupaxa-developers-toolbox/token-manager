# Reference

## Commands

| Command                  | Purpose                                 |
| ------------------------ | --------------------------------------- |
| `list`                   | Print tokens as a table, JSON, or names |
| `types`                  | Print the token types in the profile    |
| `add`                    | Store a new token                       |
| `update`                 | Change type, name, value, or env var    |
| `delete`                 | Remove a token                          |
| `show`                   | Print metadata, or the value if asked   |
| `set`                    | Print export, dotenv, or the raw value  |
| `profile init`           | Create a profile and encryption mode    |
| `profile update`         | Write config.json for a legacy profile  |
| `profile list`           | List every profile directory            |
| `profile show`           | Print the profile name and encryption   |
| `profile set-encryption` | Rewrite tokens in a new encryption mode |
| `migrate`                | Copy or move tokens between profiles    |
| `help`                   | Show help for every command, or one     |

`list --columns` takes a comma-separated list of `name`, `env_var`,
`id`, `updated`, `created`, `value`, and `type`. `list --max-width N`
wraps that table. `list --reveal` includes secrets in the table and in
JSON. Without it, both hide `value`.

`add` prompts for the secret when `--value` is omitted. `--value -` on
`add` or `update` reads the secret from stdin. An empty secret is a
usage error.

`migrate --dry-run` reports the copy or move and leaves both profiles
unchanged. It still reads both profiles, so an encrypted profile asks for
its passphrase. Both profiles must already exist. `migrate --move` updates
the source only after the destination reads back every migrated token,
including its env var. `--overwrite` is required when the destination
already has the same type and name, or the same id with different contents.

`profile init` refuses to run again once the profile has a config or a
token file. A token file without `config.json` is still a profile. `profile update`
writes that config and does not rewrite the token file.
`profile list` shows every profile directory, with an Initialised column
between the name and the encryption. `--profile` is not accepted there.
Other commands refuse a name that has neither a config nor a token file.
`profile set-encryption` switches mode only after the new token file has
been written and read back. Changing between `gpg` and `openssl` asks for
the current passphrase and the new one. `update --env-var ''` clears a
stored variable name.

## Token Fields

| Field        | Meaning                                      |
| ------------ | -------------------------------------------- |
| `id`         | UUID assigned when the token is added        |
| `type`       | Lowercase type, such as `github` or `pypi`   |
| `name`       | Name, unique together with `type`            |
| `value`      | Secret                                       |
| `env_var`    | Variable name used by `set`                  |
| `created_at` | UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ`        |
| `updated_at` | UTC timestamp, updated on each change        |

## Exit Codes

| Code | Meaning                                                    |
| ---- | ---------------------------------------------------------- |
| 0    | Success, including a closed output pipe                    |
| 1    | Runtime failure: missing token, conflict, or crypto error  |
| 2    | Usage error, such as `--name` without `--type`             |

Status text is coloured when stdout or stderr is a terminal. `NO_COLOR`
disables it. `CLICOLOR_FORCE` enables it even when the stream is a pipe.
`export`, `dotenv`, `value`, JSON, and name lists stay plain.

## Library

```python
from lupaxa.token_manager import Store, Token

store = Store(profile="default")
tokens: list[Token] = store.load()
```

`Store(profile, config_dir=...)` overrides the config root. When
`config_dir` is omitted, the root is `$XDG_CONFIG_HOME/tokenctl`. Hold
`store.exclusive()` across a load, change, and save.

## Encryption

| Mode      | File              | Tool                                 |
| --------- | ----------------- | ------------------------------------ |
| `none`    | `tokens.json`     | Plaintext JSON, mode `0600`          |
| `gpg`     | `tokens.json.gpg` | `gpg --symmetric` AES256             |
| `openssl` | `tokens.json.enc` | `openssl enc -aes-256-cbc -pbkdf2`   |

Profile directories are mode `0700`. The passphrase is
`TOKENCTL_PASSPHRASE` when one passphrase is required, or one prompt per
encrypted profile on a terminal. A migrate asks once when one profile is
encrypted, and twice when both are. The shared variable is ignored when
both profiles are encrypted. The passphrase is
passed to `gpg` and `openssl` on a dedicated pipe, separate from the
token JSON, and it is not stored in the environment. Each write uses a
private temporary file, is read back, and then replaces the live file. A
profile lock covers the whole command. A token file that is missing,
unreadable, or not a list of tokens stops the command and is left in
place. `config.json` must name `none`, `gpg`, or `openssl`.
