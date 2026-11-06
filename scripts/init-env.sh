#!/usr/bin/env bash
set -euo pipefail

if [[ -e .env ]]; then
  printf '%s\n' '.env already exists; refusing to overwrite it.'
  exit 0
fi

umask 077
cp .env.example .env
secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
SECRET_KEY_VALUE="$secret" python3 - <<'PY'
from pathlib import Path
import os

path = Path('.env')
text = path.read_text()
path.write_text(text.replace('SECRET_KEY=generate-a-long-random-value', f"SECRET_KEY={os.environ['SECRET_KEY_VALUE']}"))
PY
chmod 600 .env
printf '%s\n' 'Created .env with a generated local SECRET_KEY (SQL and provider credentials remain unconfigured).'
