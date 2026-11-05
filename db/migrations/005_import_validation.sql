IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version = 5)
BEGIN
  EXEC(N'
  CREATE OR ALTER PROCEDURE dbo.usp_apply_shipment_import
    @import_run_id bigint
  AS
  BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @applied_count int = 0;

    BEGIN TRANSACTION;

    ;WITH duplicate_rows AS (
      SELECT shipment_id, source_row_no,
             ROW_NUMBER() OVER (PARTITION BY shipment_id ORDER BY source_row_no) AS duplicate_rank
      FROM staging.shipment_updates
      WHERE import_run_id = @import_run_id AND shipment_id IS NOT NULL
    )
    UPDATE u
      SET validation_error = COALESCE(u.validation_error, N''duplicate shipment_id'')
    FROM staging.shipment_updates u
    JOIN duplicate_rows d ON d.shipment_id = u.shipment_id AND d.source_row_no = u.source_row_no
    WHERE u.import_run_id = @import_run_id AND d.duplicate_rank > 1 AND u.validation_error IS NULL;

    UPDATE u
      SET validation_error = COALESCE(u.validation_error,
        CASE
          WHEN u.shipment_id IS NULL OR LTRIM(RTRIM(u.shipment_id)) = N'''' THEN N''missing shipment_id''
          WHEN u.customer_name IS NULL OR LTRIM(RTRIM(u.customer_name)) = N'''' THEN N''missing customer''
          WHEN u.product_name IS NULL OR LTRIM(RTRIM(u.product_name)) = N'''' THEN N''missing product''
          WHEN u.facility_name IS NULL OR LTRIM(RTRIM(u.facility_name)) = N'''' THEN N''missing facility''
          WHEN u.carrier_name IS NULL OR LTRIM(RTRIM(u.carrier_name)) = N'''' THEN N''missing carrier''
          WHEN u.planned_departure_utc IS NULL THEN N''missing planned departure''
          WHEN u.ordered_qty IS NULL OR u.ordered_qty <= 0 THEN N''ordered quantity must be positive''
          WHEN u.shipped_qty IS NULL OR u.shipped_qty < 0 OR u.shipped_qty > u.ordered_qty THEN N''shipped quantity is invalid''
          WHEN u.freight_cost IS NULL OR u.freight_cost < 0 THEN N''freight cost is invalid''
          WHEN u.status IS NULL OR u.status NOT IN (N''Scheduled'', N''In Transit'', N''Delivered'', N''Exception'', N''Cancelled'') THEN N''shipment status is invalid''
        END)
    FROM staging.shipment_updates u
    WHERE u.import_run_id = @import_run_id AND u.validation_error IS NULL;

    UPDATE u
      SET validation_error = N''unknown customer, product, facility, or carrier''
    FROM staging.shipment_updates u
    WHERE u.import_run_id = @import_run_id
      AND u.validation_error IS NULL
      AND NOT EXISTS (
        SELECT 1
        FROM dbo.customers c
        CROSS JOIN dbo.products p
        CROSS JOIN dbo.facilities f
        CROSS JOIN dbo.carriers ca
        WHERE c.customer_name = u.customer_name
          AND p.product_name = u.product_name
          AND f.facility_name = u.facility_name
          AND ca.carrier_name = u.carrier_name
      );

    INSERT dbo.import_errors(import_run_id, source_row_no, error_message, raw_json)
      SELECT @import_run_id, source_row_no, validation_error,
             CONCAT(N''{""shipment_id"":""'', STRING_ESCAPE(ISNULL(shipment_id, N''''), N''json''), N''""}'')
      FROM staging.shipment_updates
      WHERE import_run_id = @import_run_id AND validation_error IS NOT NULL;

    INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code,
                         appointment_utc, planned_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
      SELECT u.shipment_id, c.customer_id, p.product_id, f.facility_id, ca.carrier_id, u.dock_code,
             DATEADD(hour, -2, u.planned_departure_utc), u.planned_departure_utc,
             u.ordered_qty, u.shipped_qty, u.freight_cost, u.status
      FROM staging.shipment_updates u
      JOIN dbo.customers c ON c.customer_name = u.customer_name
      JOIN dbo.products p ON p.product_name = u.product_name
      JOIN dbo.facilities f ON f.facility_name = u.facility_name
      JOIN dbo.carriers ca ON ca.carrier_name = u.carrier_name
      WHERE u.import_run_id = @import_run_id
        AND u.validation_error IS NULL
        AND NOT EXISTS (SELECT 1 FROM dbo.shipments s WHERE s.shipment_id = u.shipment_id);
    SET @applied_count = @@ROWCOUNT;

    UPDATE dbo.import_runs
      SET completed_utc = SYSUTCDATETIME(),
          applied_count = @applied_count,
          rejected_count = (SELECT COUNT(*) FROM staging.shipment_updates WHERE import_run_id = @import_run_id AND validation_error IS NOT NULL),
          status = N''Completed''
      WHERE import_run_id = @import_run_id;

    DELETE FROM staging.shipment_updates WHERE import_run_id = @import_run_id;
    COMMIT TRANSACTION;
  END');
  INSERT dbo.schema_migrations(version) VALUES (5);
END;
