# Getting Started

## Requirements

- Python 3.10 or newer
- `gpg` only if a profile uses gpg encryption
- `openssl` only if a profile uses openssl encryption

## Install

```bash
python3 -m pip install lupaxa-token-manager
```

The PyPI name is `lupaxa-token-manager`. The import path is
`lupaxa.token_manager`. The console scripts are `tokenctl` and
`token-manager`. `lupaxa` is a namespace package — there is no
`lupaxa/__init__.py`.

### From Source (Development)

```bash
make init
make python-install-dev
```

Site Markdown lives in `mkdocs/` (not GitHub’s special `docs/` directory).
After makefile-skills are installed:

```bash
make mkdocs-serve
```

## First Profile

```bash
tokenctl profile init
tokenctl add --type github --name main --env-var GITHUB_TOKEN
tokenctl list
```

`add` prompts for the secret when you omit `--value`. Pipe it instead
with `--value -` when the shell is not a terminal.

Tokens are stored under `$XDG_CONFIG_HOME/tokenctl` (or `~/.config/tokenctl`
when `XDG_CONFIG_HOME` is unset). Each profile is a directory:

```text
profiles/<profile>/config.json
profiles/<profile>/tokens.json
```

`config.json` records the encryption mode: `none`, `gpg`, or `openssl`.
Encrypted profiles use `tokens.json.gpg` or `tokens.json.enc` instead of
plaintext `tokens.json`.

## Use a Token in the Current Shell

A child process cannot change the parent environment. Source the export:

```bash
source <(tokenctl set --type github --name main --format export)
```

Pass `--profile` before the subcommand when the token is not in `default`:

```bash
source <(tokenctl --profile ci set --type github --name main --format export)
```
