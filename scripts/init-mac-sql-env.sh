#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env.mac-sql}"
if [[ -e "$env_file" ]]; then
  printf '%s\n' "$env_file already exists; refusing to overwrite it."
  exit 0
fi

umask 077
passwords="$({
  python3 - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits
def password():
    return "Ho" + "".join(secrets.choice(alphabet) for _ in range(28)) + "!9"
print(password())
print(password())
PY
})"
sa_password="$(printf '%s\n' "$passwords" | sed -n '1p')"
app_password="$(printf '%s\n' "$passwords" | sed -n '2p')"

cat > "$env_file" <<EOF
# Generated local-only credentials for the temporary emulated SQL Server stack.
COMPOSE_PROJECT_NAME=harvestops-mac-sql
HARVESTOPS_MAC_SQL_APP_PORT=8051
SQL_DATABASE=HarvestOps
MSSQL_SA_PASSWORD=$sa_password
HARVESTOPS_APP_LOGIN=harvestops_app
HARVESTOPS_APP_PASSWORD=$app_password
EOF
chmod 600 "$env_file"
printf 'Created %s with mode 600. Credentials are local-only and are not printed.\n' "$env_file"
