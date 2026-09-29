<p align="center">
  <a href="https://github.com/lupaxa-developers-toolbox">
    <img src="https://raw.githubusercontent.com/the-lupaxa-project/brand-assets/master/logos/organisations/developers-toolbox/readme-logo.png" alt="Developers Toolbox" />
  </a>
</p>

<h1 align="center">Token Manager</h1>

Store API tokens in named profiles and print them as shell exports.
Each profile can keep tokens as plaintext JSON, or encrypt them with
`gpg` or `openssl`.

The PyPI name is `lupaxa-token-manager`. The import path is
`lupaxa.token_manager`. The console scripts are `tokenctl` and
`token-manager`.

## Install

```bash
pip install lupaxa-token-manager
```

Requires Python 3.10 or newer. Encryption modes need the `gpg` or
`openssl` binary on `PATH`. Plaintext profiles do not.

## Quick Start

```bash
tokenctl profile init
tokenctl add --type github --name main --value 'ghp_xxx' --env-var GITHUB_TOKEN
tokenctl list
source <(tokenctl set --type github --name main --format export)
```

A child process cannot change the parent shell, so source the `export`
line. Status text is coloured on a terminal: green for success, red for
errors, yellow for a plaintext profile, and cyan for information.
`tokenctl help` and `tokenctl help list` colour the command and option
names. `export`,
`dotenv`, `value`, JSON, and name lists stay plain so they can be sourced
or parsed. Set `NO_COLOR` to turn colour off. `--profile` goes before the
subcommand and defaults to `default`:

```bash
source <(tokenctl --profile ci set --type github --name main --format export)
```

Names are unique within a type, so `main` can exist for both `github`
and `aws`. Selecting by `--name` also needs `--type`. `--id` selects a
token on its own. `--env-var` defaults to `TYPE_TOKEN` (for example
`GITHUB_TOKEN`).

## Command Reference

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

### List and Show

```bash
tokenctl list
tokenctl list --type github --format names
tokenctl list --format json
tokenctl list --format json --reveal
tokenctl list --columns name,env_var,value --max-width 100
tokenctl types
tokenctl show --type github --name main
tokenctl show --type github --name main --reveal
```

The default list is a grouped text table. The table and JSON both hide
secret values unless you pass `--reveal`. `show` does the same.

`--columns` picks and orders columns. The names are `name`, `env_var`,
`id`, `updated`, `created`, `value`, and `type`. `--max-width` wraps the
table to that many characters.

### Add, Update, and Delete

```bash
tokenctl add --type pypi --name publish
printf '%s' 'pypi-secret' | tokenctl add --type pypi --name publish --value -
tokenctl update --type github --name main --new-name prod --value 'ghp_new'
tokenctl delete --type pypi --name publish
```

Omit `--value` on `add` and the tool prompts without echoing. `--value -`
reads the secret from stdin, which keeps it out of shell history and the
process list. On `update`, omit `--value` to leave the secret unchanged,
or pass `--value -` to replace it from stdin.

### Set

```bash
tokenctl set --type github --name prod --format export
tokenctl set --type pypi --name publish --format dotenv
tokenctl set --type github --name prod --format value
```

`export` is the default. `export` and `dotenv` both single-quote the value.
The variable name must be a shell identifier.

### Profiles

```bash
tokenctl profile list
tokenctl profile init
tokenctl profile update
tokenctl --profile ci profile init --encryption openssl
tokenctl --profile ci profile show
tokenctl --profile ci profile set-encryption gpg
```

`profile list` prints every profile directory. The columns are name,
whether it is initialised, and encryption. A directory with no config and
no token file is listed as not initialised, with a blank encryption. Do
not pass `--profile` to it. `--format names` prints the names
only. `profile init` creates a profile. A profile is also available when
it already has a token file and no `config.json`: that is a legacy
profile, and its encryption is taken from the file. Commands do not create
a directory for a name that has neither. A second init stops and leaves an
existing profile unchanged. `profile update` writes `config.json` for a
legacy profile and does not rewrite its token file. `set-encryption`
writes and checks the new token file before it updates `config.json`,
then removes the previous file. If that write fails, the existing profile
is left as it is.

### Migrate

```bash
tokenctl migrate --from-profile default --to-profile ci --dry-run
tokenctl migrate --from-profile default --to-profile ci --type github --name prod --move --overwrite
```

`--dry-run` prints the change and writes nothing. It still reads both
profiles, so an encrypted profile asks for its passphrase. The destination
must already exist. Without `--move`, the source profile is left as it is.
`--move` changes the source only after
the destination reads back every migrated token. `--overwrite` replaces a destination token that already uses the same
type and name, or the same id with different contents. A conflict without
`--overwrite` is still an error during a dry run. Copying the same token
again is allowed when the destination copy is unchanged. A migrate asks
once when one profile is encrypted, and twice when both are.
`TOKENCTL_PASSPHRASE` is used only when one passphrase is required.
Changing a profile between `gpg` and `openssl` asks for the current
passphrase and the new one. `update --env-var ''` clears a stored
variable name.

## Storage and Encryption

Tokens live under `$XDG_CONFIG_HOME/tokenctl` (or `~/.config/tokenctl`).
Each profile is `profiles/<profile>/` with a `config.json` encryption
mode of `none`, `gpg`, or `openssl`.

| Mode      | File              | Tool                                 |
| --------- | ----------------- | ------------------------------------ |
| `none`    | `tokens.json`     | Plaintext JSON, mode `0600`          |
| `gpg`     | `tokens.json.gpg` | `gpg --symmetric` AES256             |
| `openssl` | `tokens.json.enc` | `openssl enc -aes-256-cbc -pbkdf2`   |

Profile names use letters, digits, `.`, `_`, and `-`. Profile directories
are mode `0700`. Set `TOKENCTL_PASSPHRASE` for a non-interactive shell
when the command needs one passphrase. A migrate between two encrypted
profiles ignores it and asks for each passphrase on a terminal. That
passphrase is passed to `gpg` or `openssl` on its own pipe. It is not
written into the environment. Each write uses a private temporary file,
is read back, and then replaces the live file. A profile lock is held for
the whole command. A token file that is missing, unreadable, or not a list
of tokens stops
the command and is left in place. `config.json` must name `none`, `gpg`,
or `openssl`; any other value stops the command.

Each token stores `id`, `type`, `name`, `value`, `env_var`, `created_at`,
and `updated_at`. Timestamps are UTC in `YYYY-MM-DDTHH:MM:SSZ` form.

Exit `0` is success. Exit `1` is a runtime failure (missing token,
conflict, or crypto error). Exit `2` is a usage error, such as `--name`
without `--type`.

## Library

```python
from lupaxa.token_manager import Store

store = Store(profile="default")
for token in store.load():
    print(token.name, token.type)
```

`Store(profile, config_dir=...)` overrides the config root. Hold
`store.exclusive()` across a load, change, and save so another process
cannot write the profile in between.

## Documentation

Site pages live in `mkdocs/` and publish to
<https://token-manager.thelupaxaproject.org/>.

```bash
make init
make python-install-dev
make mkdocs-serve
```

<a href="https://github.com/the-lupaxa-project">
    <img src="https://raw.githubusercontent.com/the-lupaxa-project/brand-assets/master/logos/components/footer-for-child-orgs.svg" alt="The Lupaxa Project Footer" width="100%" />
</a>
