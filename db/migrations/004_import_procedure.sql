IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version = 4)
BEGIN
  IF SCHEMA_ID(N'staging') IS NULL EXEC(N'CREATE SCHEMA staging');
  IF OBJECT_ID(N'staging.shipment_updates', N'U') IS NULL
    CREATE TABLE staging.shipment_updates (
      import_run_id bigint NOT NULL,
      source_row_no int NOT NULL,
      shipment_id nvarchar(30) NULL,
      customer_name nvarchar(120) NULL,
      product_name nvarchar(120) NULL,
      facility_name nvarchar(120) NULL,
      carrier_name nvarchar(120) NULL,
      dock_code nvarchar(20) NULL,
      planned_departure_utc datetime2(0) NULL,
      ordered_qty decimal(18,3) NULL,
      shipped_qty decimal(18,3) NULL,
      freight_cost decimal(18,2) NULL,
      status nvarchar(30) NULL,
      validation_error nvarchar(500) NULL
    );
  EXEC(N'
  CREATE OR ALTER PROCEDURE dbo.usp_apply_shipment_import
    @import_run_id bigint
  AS
  BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRANSACTION;
    INSERT dbo.import_errors(import_run_id, source_row_no, error_message, raw_json)
      SELECT @import_run_id, source_row_no, validation_error, CONCAT(''{"shipment_id":"'', ISNULL(shipment_id, ''''), ''"}'')
      FROM staging.shipment_updates WHERE import_run_id = @import_run_id AND validation_error IS NOT NULL;
    INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
      SELECT u.shipment_id, c.customer_id, p.product_id, f.facility_id, ca.carrier_id, u.dock_code, DATEADD(hour, -2, u.planned_departure_utc), u.planned_departure_utc, u.ordered_qty, u.shipped_qty, u.freight_cost, u.status
      FROM staging.shipment_updates u
      JOIN dbo.customers c ON c.customer_name = u.customer_name
      JOIN dbo.products p ON p.product_name = u.product_name
      JOIN dbo.facilities f ON f.facility_name = u.facility_name
      JOIN dbo.carriers ca ON ca.carrier_name = u.carrier_name
      WHERE u.import_run_id = @import_run_id AND u.validation_error IS NULL
        AND NOT EXISTS (SELECT 1 FROM dbo.shipments s WHERE s.shipment_id = u.shipment_id);
    UPDATE dbo.import_runs SET completed_utc = SYSUTCDATETIME(), applied_count = (SELECT COUNT(*) FROM staging.shipment_updates u WHERE u.import_run_id=@import_run_id AND u.validation_error IS NULL AND EXISTS (SELECT 1 FROM dbo.shipments s WHERE s.shipment_id=u.shipment_id)), rejected_count = (SELECT COUNT(*) FROM staging.shipment_updates WHERE import_run_id=@import_run_id AND validation_error IS NOT NULL), status = ''Completed'' WHERE import_run_id = @import_run_id;
    DELETE FROM staging.shipment_updates WHERE import_run_id = @import_run_id;
    COMMIT TRANSACTION;
  END');
  INSERT dbo.schema_migrations(version) VALUES (4);
END;
