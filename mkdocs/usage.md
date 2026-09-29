# Usage

`--profile` selects the profile. It defaults to `default`. Put it before
the subcommand:

```bash
tokenctl --profile ci list
```

## Add, Update, and Delete

```bash
tokenctl add --type github --name main --env-var GITHUB_TOKEN
printf '%s' 'ghp_xxx' | tokenctl add --type github --name main --value -
tokenctl update --type github --name main --new-name prod --value 'ghp_new'
tokenctl delete --type github --name prod
```

Omit `--value` on `add` to prompt without echo. `--value -` reads stdin
so the secret is not in the shell history or the process list. On
`update`, omit `--value` to keep the current secret.

`--env-var` defaults to `TYPE_TOKEN` (for example `GITHUB_TOKEN`).
Names are unique within a type, so `main` can exist for both `github`
and `aws`. Commands that select by `--name` also need `--type`.
`--id` selects a token without a type.

## List and Show

```bash
tokenctl list
tokenctl list --type github
tokenctl list --format names
tokenctl list --format json
tokenctl list --format json --reveal
tokenctl list --columns name,env_var,value --max-width 100
tokenctl types
tokenctl show --type github --name main
tokenctl show --type github --name main --reveal
```

The default list is a grouped text table. The table, JSON, and `show`
hide secret values unless you pass `--reveal`.

`--columns` accepts `name`, `env_var`, `id`, `updated`, `created`,
`value`, and `type`, in the order you write them. `--max-width` wraps
the table to that width.

## Set

```bash
tokenctl set --type github --name main --format export
tokenctl set --type github --name main --format dotenv
tokenctl set --type github --name main --format value
```

`export` is the default. `export` and `dotenv` both single-quote the value.
The variable name must be a shell identifier. Those formats, JSON, and
name lists are never coloured. On a terminal, success lines are green,
errors are red, a plaintext profile label is yellow, and dry-run text is
cyan. `tokenctl help` and `tokenctl help list` colour command and option
names the same way. `NO_COLOR` turns colour off.

## Profiles

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
only. `profile init` creates a profile. A directory that already has a
token file and no `config.json` is still a profile: encryption is taken
from that file. Commands do not create a directory for a name that has
neither. If that profile already has a config or token file, init stops
and leaves it unchanged. `profile update` writes `config.json` for a
legacy profile and does not rewrite its token file. `set-encryption`
writes and checks the new token file before it updates `config.json`,
then removes the previous file. Changing between `gpg` and
`openssl` asks for the current passphrase and the new one. If that write
fails, the existing profile is left as it is.

For `gpg` and `openssl`, set `TOKENCTL_PASSPHRASE` or type the passphrase
at the prompt. A migrate asks once when one profile is encrypted, and
twice when both are. `TOKENCTL_PASSPHRASE` is used only when one
passphrase is required. A migrate between two encrypted profiles ignores
it and asks for each passphrase on a terminal. A prompted passphrase is
given to the encryption tool on a separate pipe and is not stored in the
environment. OpenSSL files use PBKDF2. `update --env-var ''` clears a
stored variable name.

## Migrate

```bash
tokenctl migrate --from-profile default --to-profile ci --dry-run
tokenctl migrate --from-profile default --to-profile ci --type github
tokenctl migrate --from-profile default --to-profile ci --type github --name main --move
tokenctl migrate --from-profile default --to-profile ci --overwrite
```

`--dry-run` prints the migration and does not write either profile. It
still reads both profiles, so an encrypted profile asks for its
passphrase. The destination must already exist. Without `--move`, the
source profile is left as it is. `--move` changes
the source only after the destination reads back every migrated token.
`--overwrite` replaces a destination token that already uses the same
type and name, or the same id with different contents. A conflict is
still an error when `--overwrite` is absent, including during a dry run.
Copying the same token again is allowed when the destination copy is
unchanged. A migrate asks once when one profile is encrypted, and twice
when both are. `TOKENCTL_PASSPHRASE` is used only when one passphrase is
required.
