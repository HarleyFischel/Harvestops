IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version = 3)
BEGIN
  EXEC(N'
  CREATE OR ALTER PROCEDURE dbo.usp_change_shipment_status
    @shipment_id nvarchar(30),
    @new_status nvarchar(30),
    @expected_row_version binary(8),
    @actor nvarchar(200)
  AS
  BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRANSACTION;
    DECLARE @old_status nvarchar(30);
    SELECT @old_status = status FROM dbo.shipments WITH (UPDLOCK, ROWLOCK) WHERE shipment_id = @shipment_id AND row_version = @expected_row_version;
    IF @old_status IS NULL THROW 51001, ''Shipment is missing or stale'', 1;
    IF NOT ((@old_status = ''Scheduled'' AND @new_status IN (''In Transit'', ''Cancelled'', ''Exception'')) OR (@old_status = ''In Transit'' AND @new_status IN (''Delivered'', ''Exception'')) OR (@old_status = ''Exception'' AND @new_status IN (''In Transit'', ''Cancelled'')))
      THROW 51002, ''Invalid shipment status transition'', 1;
    UPDATE dbo.shipments SET status = @new_status, actual_departure_utc = CASE WHEN @new_status IN (''In Transit'', ''Delivered'') AND actual_departure_utc IS NULL THEN SYSUTCDATETIME() ELSE actual_departure_utc END WHERE shipment_id = @shipment_id AND row_version = @expected_row_version;
    INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json) VALUES (@actor, ''shipment.status_changed'', ''shipment'', @shipment_id, CONCAT(''{"from":"'', @old_status, ''","to":"'', @new_status, ''"}''));
    COMMIT TRANSACTION;
  END');
  INSERT dbo.schema_migrations(version) VALUES (3);
END;
