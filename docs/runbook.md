# Incident and support runbook

Check /healthz, then /readyz, application logs, Container Apps revisions, database connectivity, and migration history. If a release is unhealthy, route traffic to the prior revision/image digest. Do not run migrations from web workers.

The x86 Compose stack runs migrations as a one-shot `migrations` service after the SQL Server healthcheck and before the app dependency is released. For the Mac external-database stack, apply migrations explicitly with `docker compose -f compose.mac.yml run --rm app python db/run_migrations.py` only after reviewing the target database and connection settings.

Backup/restore exercise: on x86 development, back up the SQL Server database with BACKUP DATABASE HarvestOps TO DISK = '/var/opt/mssql/backup/HarvestOps.bak', copy the backup to durable storage, restore to a new database, apply read-only smoke queries, and record the result in the validation report. The Mac demo store is not durable and is not a production backup.

Data-loss warning: deleting the SQL Server volume destroys local database state; deleting a Codespace destroys its local filesystem. Preserve backups outside the disposable environment.
