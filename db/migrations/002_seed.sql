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
  INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, actual_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
  SELECT 'SHP-1004',c.customer_id,p.product_id,f.facility_id,ca.carrier_id,'D-03','2026-01-26T13:00:00','2026-01-26T15:00:00',NULL,1100,1100,1750,'Scheduled' FROM dbo.customers c,dbo.products p,dbo.facilities f,dbo.carriers ca WHERE c.customer_code='FMNE' AND p.sku='ICE-LET' AND f.facility_code='OXN' AND ca.carrier_name='NorthStar';
  INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
  SELECT 'SHP-1005',c.customer_id,p.product_id,f.facility_id,ca.carrier_id,'D-05','2026-02-09T13:00:00','2026-02-09T15:00:00',800,800,1290,'Delivered' FROM dbo.customers c,dbo.products p,dbo.facilities f,dbo.carriers ca WHERE c.customer_code='HG' AND p.sku='ROM-HEART' AND f.facility_code='SAL' AND ca.carrier_name='Westway';
  INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, actual_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
  SELECT 'SHP-1006',c.customer_id,p.product_id,f.facility_id,ca.carrier_id,'D-01','2026-02-12T13:00:00','2026-02-12T15:00:00','2026-02-12T17:00:00',1000,920,1605,'Exception' FROM dbo.customers c,dbo.products p,dbo.facilities f,dbo.carriers ca WHERE c.customer_code='CM' AND p.sku='BABY-SP' AND f.facility_code='YUM' AND ca.carrier_name='NorthStar';
  INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, actual_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
  SELECT 'SHP-1007',c.customer_id,p.product_id,f.facility_id,ca.carrier_id,'D-02','2026-02-16T13:00:00','2026-02-16T15:00:00','2026-02-16T14:00:00',1300,1300,1980,'Delivered' FROM dbo.customers c,dbo.products p,dbo.facilities f,dbo.carriers ca WHERE c.customer_code='FMNE' AND p.sku='SPR-MIX' AND f.facility_code='OXN' AND ca.carrier_name='GreenLine';
  INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, ordered_qty, shipped_qty, freight_cost, status)
  SELECT 'SHP-1008',c.customer_id,p.product_id,f.facility_id,ca.carrier_id,'D-06','2026-03-02T13:00:00','2026-03-02T15:00:00',700,700,1180,'Cancelled' FROM dbo.customers c,dbo.products p,dbo.facilities f,dbo.carriers ca WHERE c.customer_code='HG' AND p.sku='ICE-LET' AND f.facility_code='SAL' AND ca.carrier_name='Westway';
  INSERT dbo.shipment_lines(shipment_id, product_id, ordered_qty, shipped_qty)
  SELECT s.shipment_id, s.product_id, s.ordered_qty, s.shipped_qty FROM dbo.shipments s;
  INSERT dbo.dock_appointments(shipment_id, dock_code, appointment_utc, status)
  SELECT shipment_id, dock_code, appointment_utc, status FROM dbo.shipments;
  INSERT dbo.production_runs(facility_id, product_id, run_date, output_qty, labor_hours)
  SELECT f.facility_id, p.product_id, d.run_date, 1800 + (p.product_id * 25), 42.5
  FROM dbo.facilities f CROSS JOIN dbo.products p CROSS JOIN (VALUES (CAST('2026-01-15' AS date)), (CAST('2026-02-15' AS date)), (CAST('2026-03-15' AS date))) d(run_date);
  INSERT dbo.vendors(vendor_name) VALUES ('Valley Packaging Co'), ('CoolChain Supplies');
  INSERT dbo.identity_roles(principal, role_name) VALUES ('demo.viewer','viewer'),('demo.operator','operator'),('demo.approver','approver'),('demo.admin','admin');
  INSERT dbo.purchase_requests(request_id, requester, facility_id, status, comment)
  SELECT 'PR-1001','demo.operator',facility_id,'Rejected','Synthetic seed: price exceeded budget' FROM dbo.facilities WHERE facility_code='SAL';
  INSERT dbo.purchase_request_lines(request_id, product_id, quantity, unit_cost)
  SELECT 'PR-1001', product_id, 40, 2.3500 FROM dbo.products WHERE sku='ROM-HEART';
  INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json)
  VALUES ('demo.approver','purchase.rejected','purchase_request','PR-1001','{"comment":"Synthetic seed: price exceeded budget"}');
  INSERT dbo.import_runs(source_name, completed_utc, applied_count, rejected_count, status)
  VALUES ('seed-invalid-shipment.csv', SYSUTCDATETIME(), 0, 1, 'Completed');
  INSERT dbo.knowledge_documents(title, body, sensitivity)
  VALUES ('KPI definitions','Fill rate is shipped quantity divided by ordered quantity. On-time rate is on-time departures divided by closed shipments.','internal'),
         ('Dock exception playbook','Confirm appointment, carrier arrival, and quantity before changing status or escalating.','internal'),
         ('Purchasing controls','A requester cannot approve their own purchase request.','restricted');
  INSERT dbo.knowledge_document_roles(document_id, role_name)
  SELECT document_id, CASE WHEN title='Purchasing controls' THEN 'approver' ELSE 'viewer' END FROM dbo.knowledge_documents;
  INSERT dbo.schema_migrations(version) VALUES (2);
END;
