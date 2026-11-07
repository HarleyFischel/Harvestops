# Delivery & Quality dashboard

HarvestOps includes a read-only Delivery & Quality page at `/?page=delivery`. It is a portfolio evidence view, not a project-management or deployment control plane. GitHub remains authoritative for commits, issues, pull requests, workflow runs, and artifacts.

## Evidence modes

The default mode reads `evidence/snapshot.json`, a versioned and schema-validated sanitized snapshot. It works without credentials and labels its collection time, source commit, scope, and stale/error state. The page never treats the newest GitHub commit as the deployed revision: runtime identity comes from `HARVESTOPS_*` build metadata, while CI evidence is matched by commit when possible.

If `GITHUB_EVIDENCE_TOKEN` is configured outside source control, the server can use the optional read-only GitHub adapter. It is limited to `GITHUB_REPOSITORY`, caches results for `EVIDENCE_CACHE_SECONDS`, applies request timeouts, and keeps the last valid snapshot when refresh fails. The token is never sent to the browser or rendered in the page. The adapter intentionally summarizes workflow runs and does not publish private PR bodies, logs, security findings, or repository documents to the portfolio view.

## Refreshing structured evidence

Generate JUnit results locally, then refresh the snapshot explicitly:

```bash
mkdir -p artifacts
./.venv/bin/python -m pytest --junitxml=artifacts/pytest.xml
./.venv/bin/python -m pytest tests/browser -q --junitxml=artifacts/browser.xml
./scripts/refresh-evidence-snapshot.py --results-dir artifacts
```

The refresh command records missing or malformed artifacts as `unknown`; it never converts them into zero failures or a pass. For a recorded hosted run, provide its exact URL and commit through `--ci-run-id` and `--ci-run-url`. Do not commit a new snapshot after every report-only change; refresh it at an intentional evidence checkpoint.

CI uploads the Python/browser and SQL integration JUnit files as short-retention artifacts. Artifact absence is unknown, and suite totals are not summed because suites can overlap.

## Interview walkthrough

Trace `OPS-002` from the searchable requirements table to `harvestops/services.py` and `harvestops/sql_store.py`, then open its service/browser tests. Show the exact hosted CI run and the local SQL-backed validation report. Explain that the running commit and latest default-branch commit are displayed separately, and that the empty release section is intentional because no formal production deployment record exists.
