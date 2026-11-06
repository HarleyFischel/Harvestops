#!/usr/bin/env bash
set -euo pipefail

# Run this on an x86-64 Linux host with compose.x86.yml running. The restore
# database is intentionally disposable and is replaced on each exercise.
compose_file="${COMPOSE_FILE:-compose.x86.yml}"
database="${HARVESTOPS_DB_NAME:-HarvestOps}"
restore_database="${HARVESTOPS_RESTORE_DB_NAME:-HarvestOps_restore}"
backup_dir="${BACKUP_OUTPUT_DIR:-./backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_name="${database}-${timestamp}.bak"
container_id=""

for name in "$database" "$restore_database"; do
  if [[ ! "$name" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "Database names may contain only letters, numbers, and underscores." >&2
    exit 2
  fi
done

: "${MSSQL_SA_PASSWORD:?Set MSSQL_SA_PASSWORD to the SQL Server SA password.}"

container_id="$(docker compose -f "$compose_file" ps -q sqlserver)"
if [[ -z "$container_id" ]]; then
  echo "The sqlserver service is not running. Start compose.x86.yml first." >&2
  exit 1
fi

sqlcmd() {
  docker compose -f "$compose_file" exec -T sqlserver \
    /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -b "$@"
}

docker compose -f "$compose_file" exec -T sqlserver sh -lc \
  'mkdir -p /var/opt/mssql/backup'

backup_path="/var/opt/mssql/backup/${database}.bak"
sqlcmd -Q "BACKUP DATABASE [$database] TO DISK = N'$backup_path' WITH INIT, COPY_ONLY, CHECKSUM"

mkdir -p "$backup_dir"
host_backup="${backup_dir%/}/${backup_name}"
docker cp "${container_id}:${backup_path}" "$host_backup"

sqlcmd -Q "
IF DB_ID(N'$restore_database') IS NOT NULL
BEGIN
  ALTER DATABASE [$restore_database] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
  DROP DATABASE [$restore_database];
END;

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

DECLARE @restore nvarchar(max) = N'RESTORE DATABASE [$restore_database] FROM DISK = N''$backup_path'' WITH ' + @moves + N', RECOVERY, REPLACE';
EXEC sys.sp_executesql @restore;
"

sqlcmd -d "$restore_database" -Q "
SELECT DB_NAME() AS restored_database;
SELECT COUNT_BIG(*) AS shipment_count FROM dbo.shipments;
SELECT COUNT_BIG(*) AS migration_count FROM dbo.schema_migrations;
"

echo "Backup copied to ${host_backup}"
echo "Restore smoke test completed for ${restore_database}; drop that disposable database when no longer needed."
