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

`export` is the default. Values are single-quoted for the shell.

## Profiles

```bash
tokenctl profile init
tokenctl --profile ci profile init --encryption openssl
tokenctl --profile ci profile show
tokenctl --profile ci profile set-encryption gpg
```

`set-encryption` rewrites the tokens in the new mode and removes the
previous token file, so a switch to encryption does not leave plaintext
behind.

For `gpg` and `openssl`, set `TOKENCTL_PASSPHRASE` or type the passphrase
at the prompt. A non-interactive shell must set the variable. A prompted
passphrase is given to the encryption tool on a separate pipe and is not
stored in the environment.

## Migrate

```bash
tokenctl migrate --from-profile default --to-profile ci --dry-run
tokenctl migrate --from-profile default --to-profile ci --type github
tokenctl migrate --from-profile default --to-profile ci --type github --name main --move
tokenctl migrate --from-profile default --to-profile ci --overwrite
```

`--dry-run` prints the migration and does not write either profile.
Without `--move`, the source profile is left as it is. `--overwrite`
replaces a destination token that already uses the same type and name.
A name conflict is still an error when `--overwrite` is absent, including
during a dry run.
