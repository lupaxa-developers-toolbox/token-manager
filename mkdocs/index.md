# Token Manager

Store API tokens in named profiles and print them as shell exports.
A profile is a directory of JSON. It can stay plaintext, or be encrypted
with `gpg` or `openssl`.

Install the **`lupaxa-token-manager`** package and import the
`lupaxa.token_manager` namespace. Use it from Python or from the
`tokenctl` CLI.

```bash
pip install lupaxa-token-manager
```

```bash
tokenctl profile init
tokenctl add --type github --name main --value 'ghp_xxx' --env-var GITHUB_TOKEN
tokenctl list
source <(tokenctl set --type github --name main --format export)
```

## What You Get

- Named profiles under `$XDG_CONFIG_HOME/tokenctl/profiles/`
- Names that are unique within a token type
- Optional `gpg` or `openssl` encryption per profile
- `list`, `show`, `add`, `update`, and `delete`
- Shell output as `export`, dotenv, or the raw value
- Secrets read from a prompt or from stdin
- Copy or move tokens between profiles, with a dry run

`tokenctl` and `token-manager` are the same console script.
