IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version = 7)
BEGIN
  -- Keep SQL Server mode aligned with the deterministic demo seed. These two
  -- rows intentionally exercise a late exception and an in-transit departure.
  UPDATE dbo.shipments
    SET actual_departure_utc = CASE shipment_id
      WHEN N'SHP-1002' THEN CAST('2026-01-08T17:00:00' AS datetime2(0))
      WHEN N'SHP-1003' THEN CAST('2026-01-12T14:00:00' AS datetime2(0))
      ELSE actual_departure_utc
    END
  WHERE shipment_id IN (N'SHP-1002', N'SHP-1003')
    AND actual_departure_utc IS NULL;

  INSERT dbo.schema_migrations(version) VALUES (7);
END;
