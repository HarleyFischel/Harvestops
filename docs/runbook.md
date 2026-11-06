# Incident and support runbook

Check /healthz, then /readyz, application logs, Container Apps revisions, database connectivity, and migration history. If a release is unhealthy, route traffic to the prior revision/image digest. Do not run migrations from web workers.

The x86 Compose stack runs migrations as a one-shot `migrations` service after the SQL Server healthcheck and before the app dependency is released. For the Mac external-database stack, apply migrations explicitly with `docker compose -f compose.mac.yml run --rm app python db/run_migrations.py` only after reviewing the target database and connection settings; the script reads the app's SQL settings from `.env`. CI may continue to provide `SQLSERVER_MIGRATION_CONNECTION` directly.

Backup/restore exercise: on x86 development, run `MSSQL_SA_PASSWORD='...' ./scripts/backup-restore-x86.sh`. The script uses `BACKUP DATABASE`, copies a timestamped `.bak` to `./backups`, restores into the disposable `HarvestOps_restore` database using the backup's logical file list, and runs read-only shipment/migration smoke queries. Copy the resulting backup to separately protected durable storage and record the result in the validation report. The Mac demo store is not durable and is not a production backup.

Data-loss warning: deleting the SQL Server volume destroys local database state; deleting a Codespace destroys its local filesystem. Preserve backups outside the disposable environment.
