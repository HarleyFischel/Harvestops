# Incident and support runbook

Check /healthz, then /readyz, application logs, Container Apps revisions, database connectivity, and migration history. If a release is unhealthy, route traffic to the prior revision/image digest. Do not run migrations from web workers.

Backup/restore exercise: on x86 development, back up the SQL Server database with BACKUP DATABASE HarvestOps TO DISK = '/var/opt/mssql/backup/HarvestOps.bak', copy the backup to durable storage, restore to a new database, apply read-only smoke queries, and record the result in the validation report. The Mac demo store is not durable and is not a production backup.

Data-loss warning: deleting the SQL Server volume destroys local database state; deleting a Codespace destroys its local filesystem. Preserve backups outside the disposable environment.
