IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version = 2)
BEGIN
  INSERT dbo.facilities(facility_code, facility_name) VALUES ('SAL','Salinas'),('YUM','Yuma'),('OXN','Oxnard');
  INSERT dbo.customers(customer_code, customer_name) VALUES ('FMNE','FreshMart Northeast'),('HG','Harvest Grocers'),('CM','City Market');
  INSERT dbo.products(sku, product_name, uom) VALUES ('ROM-HEART','Romaine Hearts','case'),('BABY-SP','Baby Spinach','case'),('SPR-MIX','Spring Mix','case'),('ICE-LET','Iceberg Lettuce','case');
  INSERT dbo.carriers(carrier_name) VALUES ('GreenLine'),('Westway'),('NorthStar');
  INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, actual_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
  SELECT 'SHP-1001',c.customer_id,p.product_id,f.facility_id,ca.carrier_id,'D-01','2026-01-05T13:00:00','2026-01-05T15:00:00','2026-01-05T14:00:00',1200,1200,1820,'Delivered' FROM dbo.customers c,dbo.products p,dbo.facilities f,dbo.carriers ca WHERE c.customer_code='FMNE' AND p.sku='ROM-HEART' AND f.facility_code='SAL' AND ca.carrier_name='GreenLine';
  INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
  SELECT 'SHP-1002',c.customer_id,p.product_id,f.facility_id,ca.carrier_id,'D-04','2026-01-08T13:00:00','2026-01-08T15:00:00',900,780,1440,'Exception' FROM dbo.customers c,dbo.products p,dbo.facilities f,dbo.carriers ca WHERE c.customer_code='HG' AND p.sku='BABY-SP' AND f.facility_code='YUM' AND ca.carrier_name='Westway';
  INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
  SELECT 'SHP-1003',c.customer_id,p.product_id,f.facility_id,ca.carrier_id,'D-02','2026-01-12T13:00:00','2026-01-12T15:00:00',1500,1500,2100,'In Transit' FROM dbo.customers c,dbo.products p,dbo.facilities f,dbo.carriers ca WHERE c.customer_code='CM' AND p.sku='SPR-MIX' AND f.facility_code='SAL' AND ca.carrier_name='GreenLine';
  INSERT dbo.schema_migrations(version) VALUES (2);
END;
