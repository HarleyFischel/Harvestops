IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version = 9)
BEGIN
  -- Align the SQL seed with the deterministic in-memory demo. The predicate
  -- limits this repair to the untouched synthetic row from migration 2.
  UPDATE dbo.shipments
    SET actual_departure_utc = NULL,
        status = N'Scheduled'
  WHERE shipment_id = N'SHP-1004'
    AND status = N'Delivered'
    AND actual_departure_utc = CAST('2026-01-26T14:00:00' AS datetime2(0));

  INSERT dbo.schema_migrations(version) VALUES (9);
END;
