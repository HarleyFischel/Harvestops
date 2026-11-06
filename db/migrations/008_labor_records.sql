IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version = 8)
BEGIN
  IF OBJECT_ID(N'dbo.labor_records', N'U') IS NULL
  BEGIN
    CREATE TABLE dbo.labor_records (
      labor_record_id bigint IDENTITY PRIMARY KEY,
      production_run_id bigint NOT NULL REFERENCES dbo.production_runs(production_run_id),
      work_date date NOT NULL,
      labor_group nvarchar(80) NOT NULL,
      labor_hours decimal(18,2) NOT NULL CHECK (labor_hours > 0),
      created_utc datetime2(0) NOT NULL CONSTRAINT df_labor_records_created DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX ix_labor_records_run_date
      ON dbo.labor_records(production_run_id, work_date)
      INCLUDE (labor_hours);
  END;

  INSERT dbo.labor_records(production_run_id, work_date, labor_group, labor_hours)
    SELECT pr.production_run_id, pr.run_date, N'Packing crew', pr.labor_hours
    FROM dbo.production_runs pr
    WHERE NOT EXISTS (
      SELECT 1 FROM dbo.labor_records lr WHERE lr.production_run_id = pr.production_run_id
    );

  INSERT dbo.schema_migrations(version) VALUES (8);
END;
