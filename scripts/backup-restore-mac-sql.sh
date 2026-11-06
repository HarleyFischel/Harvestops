#!/usr/bin/env bash
set -euo pipefail

# Development-only backup/restore exercise for compose.mac-sql-emulated.yml.
# The SQL service has no published host port; all SQL commands run through
# docker compose exec on the private Compose network.
env_file="${1:-.env.mac-sql}"
compose_file="compose.mac-sql-emulated.yml"
database="${HARVESTOPS_DB_NAME:-HarvestOps}"
backup_dir="${BACKUP_OUTPUT_DIR:-./backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_name="${database}-${timestamp}.bak"
restore_database="${database}_restore_${timestamp//[^A-Za-z0-9]/}"

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file. Run ./scripts/init-mac-sql-env.sh first." >&2
  exit 2
fi
for name in "$database" "$restore_database"; do
  if [[ ! "$name" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "Database names may contain only letters, numbers, and underscores." >&2
    exit 2
  fi
done

compose=(docker compose --env-file "$env_file" -f "$compose_file")
container_id="$("${compose[@]}" ps -q sqlserver)"
if [[ -z "$container_id" ]]; then
  echo "The sqlserver service is not running. Start the Mac SQL profile first." >&2
  exit 1
fi
sa_password="$(awk -F= '$1 == "MSSQL_SA_PASSWORD" {sub(/^[^=]*=/, ""); print; exit}' "$env_file")"
if [[ -z "$sa_password" ]]; then
  echo "MSSQL_SA_PASSWORD is missing from $env_file." >&2
  exit 2
fi

sqlcmd() {
  "${compose[@]}" exec -T sqlserver \
    /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$sa_password" -b "$@"
}

"${compose[@]}" exec -T sqlserver sh -lc 'mkdir -p /var/opt/mssql/backup'
backup_path="/var/opt/mssql/backup/${backup_name}"
sqlcmd -Q "BACKUP DATABASE [$database] TO DISK = N'$backup_path' WITH INIT, COPY_ONLY, CHECKSUM"

mkdir -p "$backup_dir"
host_backup="${backup_dir%/}/${backup_name}"
docker cp "${container_id}:${backup_path}" "$host_backup"

restore_sql="
DECLARE @files TABLE (
  LogicalName nvarchar(128), PhysicalName nvarchar(260), [Type] char(1),
  FileGroupName nvarchar(128), Size numeric(20,0), MaxSize numeric(20,0),
  FileId bigint, CreateLSN numeric(25,0), DropLSN numeric(25,0),
  UniqueId uniqueidentifier, ReadOnlyLSN numeric(25,0), ReadWriteLSN numeric(25,0),
  BackupSizeInBytes bigint, SourceBlockSize int, FileGroupId int, LogGroupGUID uniqueidentifier,
  DifferentialBaseLSN numeric(25,0), DifferentialBaseGUID uniqueidentifier,
  IsReadOnly bit, IsPresent bit, TDEThumbprint varbinary(32), SnapshotURL nvarchar(360)
);
INSERT @files EXEC(N'RESTORE FILELISTONLY FROM DISK = N''$backup_path''');
DECLARE @moves nvarchar(max);
WITH numbered AS (
  SELECT LogicalName, [Type], ROW_NUMBER() OVER (PARTITION BY [Type] ORDER BY LogicalName) AS n
  FROM @files
)
SELECT @moves = STRING_AGG(
  N'MOVE N''' + REPLACE(LogicalName, '''', '''''') + N''' TO N''/var/opt/mssql/data/$restore_database' +
  CASE WHEN [Type] = 'L' THEN N'_log' ELSE CASE WHEN n = 1 THEN N'' ELSE N'_' + CONVERT(nvarchar(10), n) END END +
  CASE WHEN [Type] = 'L' THEN N'.ldf' ELSE CASE WHEN n = 1 THEN N'.mdf' ELSE N'.ndf' END END + N'''',
  N', '
)
FROM numbered;
DECLARE @restore nvarchar(max) = N'RESTORE DATABASE [$restore_database] FROM DISK = N''$backup_path'' WITH ' + @moves + N', RECOVERY';
EXEC sys.sp_executesql @restore;
"
sqlcmd -Q "$restore_sql"
sqlcmd -d "$restore_database" -Q "SELECT DB_NAME() AS restored_database; SELECT COUNT_BIG(*) AS shipment_count FROM dbo.shipments; SELECT COUNT_BIG(*) AS migration_count FROM dbo.schema_migrations;"

echo "Backup copied to $host_backup"
echo "Restore smoke test completed for $restore_database; it is disposable and was not used by the application."
