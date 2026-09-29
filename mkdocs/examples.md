# Examples

## GitHub Token in the Current Shell

```bash
printf '%s' "$GITHUB_TOKEN" | tokenctl add --type github --name main --env-var GITHUB_TOKEN --value -
source <(tokenctl set --type github --name main)
```

Omit `--value` instead when you are at a terminal and want a hidden prompt.

## Dotenv for Another Tool

```bash
tokenctl set --type pypi --name publish --format dotenv
```

That prints a single `PYPI_TOKEN=...` line. The default env var is
`TYPE_TOKEN` when you omit `--env-var`.

## Encrypted CI Profile

```bash
export TOKENCTL_PASSPHRASE='from-your-secret-store'
tokenctl --profile ci profile init --encryption openssl
tokenctl --profile ci add --type github --name actions --value 'ghp_xxx'
tokenctl --profile ci set --type github --name actions --format value
```

## Narrow List

```bash
tokenctl list --columns name,env_var,value --max-width 100
tokenctl list --columns type,name,updated --type github
```

## Move One Token

```bash
tokenctl migrate \
  --from-profile default \
  --to-profile ci \
  --type github \
  --name main \
  --move \
  --overwrite \
  --dry-run
```

Drop `--dry-run` when the preview is the move you want.

## Helper Function

```bash
tokenuse() {
  local ty="$1" nm="$2" prof="${3:-default}"
  source <(tokenctl --profile "$prof" set --type "$ty" --name "$nm" --format export)
}

tokenuse github main
tokenuse aws prod aws-prod
```

## Python

```python
from lupaxa.token_manager import Store

store = Store(profile="ci")
match = next(token for token in store.load() if token.type == "github" and token.name == "actions")
print(match.env_var)
```
