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
| `profile show`           | Print the profile name and encryption   |
| `profile set-encryption` | Rewrite tokens in a new encryption mode |
| `migrate`                | Copy or move tokens between profiles    |

`list --columns` takes a comma-separated list of `name`, `env_var`,
`id`, `updated`, `created`, `value`, and `type`. `list --max-width N`
wraps that table. `list --reveal` includes secrets in the table and in
JSON. Without it, both hide `value`.

`add` prompts for the secret when `--value` is omitted. `--value -` on
`add` or `update` reads the secret from stdin. An empty secret is a
usage error.

`migrate --dry-run` reports the copy or move and leaves both profiles
unchanged.

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

## Library

```python
from lupaxa.token_manager import Store, Token

store = Store(profile="default")
tokens: list[Token] = store.load()
```

`Store(profile, config_dir=...)` overrides the config root. When
`config_dir` is omitted, the root is `$XDG_CONFIG_HOME/tokenctl`.

## Encryption

| Mode      | File              | Tool                        |
| --------- | ----------------- | --------------------------- |
| `none`    | `tokens.json`     | Plaintext JSON, mode `0600` |
| `gpg`     | `tokens.json.gpg` | `gpg --symmetric` AES256    |
| `openssl` | `tokens.json.enc` | `openssl enc -aes-256-cbc`  |

The passphrase is `TOKENCTL_PASSPHRASE`, or a prompt on a terminal. It is
passed to `gpg` and `openssl` on a dedicated pipe, separate from the
token JSON. Files are written to a temporary path and then replaced.
