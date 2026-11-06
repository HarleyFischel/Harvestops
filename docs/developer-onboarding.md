# Developer onboarding

1. Use Python 3.12, run `./scripts/init-env.sh` to create an ignored `.env` with a generated local `SECRET_KEY`, create a virtual environment, and run `pip install -e '.[dev]'`. Codespaces also installs the Docker-in-Docker feature; verify it with `docker version` before using Compose.
2. Start the demo with `./scripts/start-demo.sh`; run `./scripts/verify-local.sh`. Repository scripts prefer the refreshed `.venv` and fall back to `.venv312` when explicitly retained.
3. Use `demo.viewer`, `demo.operator`, `demo.approver`, and `demo.admin` only in development demo mode.
4. For SQL work, use `compose.x86.yml` on an x86-64 host or configure the Mac app for an external SQL Server. Apply migrations explicitly.
5. Before a commit run Ruff, pytest, and `git diff --check`. For UI changes run the browser smoke test.

For Compose, stop services with `docker compose -f compose.x86.yml stop`, restart them with `docker compose -f compose.x86.yml start`, and use `down` only when removing containers. Do not use `down -v` unless the SQL Server volume is intentionally disposable or backed up. Do not delete Codespaces or the SQL Server volume casually: those actions remove local files or database state. Keep secrets in environment configuration and use the tracked checklist for handoff evidence.
