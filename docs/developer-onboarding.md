# Developer onboarding

1. Use Python 3.12, run `./scripts/init-env.sh` to create an ignored `.env` with a generated local `SECRET_KEY`, create a virtual environment, and run `pip install -e '.[dev]'`. Codespaces also installs the Docker-in-Docker feature; verify it with `docker version` before using Compose.
2. Start the demo with `./scripts/start-demo.sh`; run `PYTHON_BIN=.venv312/bin/python ./scripts/verify-local.sh`.
3. Use `demo.viewer`, `demo.operator`, `demo.approver`, and `demo.admin` only in development demo mode.
4. For SQL work, use `compose.x86.yml` on an x86-64 host or configure the Mac app for an external SQL Server. Apply migrations explicitly.
5. Before a commit run Ruff, pytest, and `git diff --check`. For UI changes run the browser smoke test.

Do not delete Codespaces or the SQL Server volume casually: those actions remove local files or database state. Keep secrets in environment configuration and use the tracked checklist for handoff evidence.
