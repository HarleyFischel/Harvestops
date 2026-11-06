#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f .env ]]; then
  echo "Missing .env. Run ./scripts/init-env.sh before validating Compose configuration." >&2
  exit 2
fi

python_bin="${PYTHON_BIN:-}"
if [[ -z "$python_bin" ]]; then
  for candidate in .venv/bin/python .venv312/bin/python; do
    if [[ -x "$candidate" ]]; then python_bin="$candidate"; break; fi
  done
fi
python_bin="${python_bin:-$(command -v python3)}"

for required in Dockerfile Dockerfile.dev compose.mac.yml compose.x86.yml docker-compose.yml infra/main.bicep \
  adf/pipeline-shipment-import.json adf/trigger-shipment-import.json; do
  [[ -f "$required" ]] || { echo "Missing required infrastructure file: $required" >&2; exit 1; }
done

"$python_bin" - <<'PY'
import json
from pathlib import Path

paths = [
    *sorted(Path("infra").glob("parameters.*.json")),
    Path("adf/pipeline-shipment-import.json"),
    Path("adf/trigger-shipment-import.json"),
]
for path in paths:
    json.loads(path.read_text())
    print(f"valid JSON: {path}")
PY

bash -n scripts/*.sh

compose_password='validation-only-Compose-123!'
MSSQL_SA_PASSWORD="$compose_password" docker compose --project-directory "$repo_root" --env-file "$repo_root/.env" -f compose.mac.yml config -q
MSSQL_SA_PASSWORD="$compose_password" docker compose --project-directory "$repo_root" --env-file "$repo_root/.env" -f compose.x86.yml config -q
MSSQL_SA_PASSWORD="$compose_password" docker compose --project-directory "$repo_root" --env-file "$repo_root/.env" -f docker-compose.yml config -q
echo 'Compose configuration rendered successfully.'

docker run --platform linux/amd64 --rm \
  -v "$repo_root:/work" \
  mcr.microsoft.com/azure-cli:2.67.0 \
  az bicep build --file /work/infra/main.bicep --stdout >/dev/null
echo 'Bicep compilation passed with Azure CLI 2.67.0.'

echo 'Infrastructure configuration verification passed. No Azure authentication or resource provisioning was performed.'
