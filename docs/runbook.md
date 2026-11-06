# Incident and support runbook

Check /healthz, then /readyz, application logs, Container Apps revisions, database connectivity, and migration history. If a release is unhealthy, route traffic to the prior revision/image digest. Do not run migrations from web workers.

The x86 Compose stack runs a one-shot `database-init` service after the SQL Server healthcheck, then a one-shot `migrations` service before the app dependency is released. The bootstrap creates `HarvestOps` on a fresh volume, and both services use the application’s escaped ODBC settings. For the Mac external-database stack, apply migrations explicitly with `docker compose -f compose.mac.yml run --rm app python db/run_migrations.py` only after reviewing the target database and connection settings; the script reads the app's SQL settings from `.env`. CI may continue to provide `SQLSERVER_MIGRATION_CONNECTION` directly.

For an external SQL preflight from the Mac, use `./scripts/verify-external-sql.sh`. It builds/runs only the ARM64 app image, validates the configured SQL settings and TLS policy, performs a read-only connectivity query, and does not launch the x86 SQL Server image. Set `RUN_MIGRATIONS=true` only for an intentional migration run.

Backup/restore exercise: on x86 development, run `MSSQL_SA_PASSWORD='...' ./scripts/backup-restore-x86.sh`. The script uses `BACKUP DATABASE`, copies a timestamped `.bak` to `./backups`, restores into the disposable `HarvestOps_restore` database using the backup's logical file list, and runs read-only shipment/migration smoke queries. Copy the resulting backup to separately protected durable storage and record the result in the validation report. The Mac demo store is not durable and is not a production backup.

Data-loss warning: deleting the SQL Server volume destroys local database state; deleting a Codespace destroys its local filesystem. Preserve backups outside the disposable environment.
