IF NOT EXISTS (SELECT 1 FROM dbo.schema_migrations WHERE version = 6)
BEGIN
  IF NOT EXISTS (SELECT 1 FROM dbo.purchase_requests WHERE request_id = N'PR-1002')
  BEGIN
    INSERT dbo.purchase_requests(request_id, requester, facility_id, status, version_no)
      SELECT N'PR-1002', N'demo.operator', facility_id, N'Pending', 2
      FROM dbo.facilities WHERE facility_code = N'YUM';
    INSERT dbo.purchase_request_lines(request_id, product_id, quantity, unit_cost)
      SELECT N'PR-1002', product_id, 80, 1.8500 FROM dbo.products WHERE sku = N'BABY-SP';
  END;

  IF NOT EXISTS (SELECT 1 FROM dbo.audit_events WHERE action_name = N'purchase.submitted' AND entity_id = N'PR-1002')
  BEGIN
    INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json)
      VALUES (N'demo.operator', N'purchase.created', N'purchase_request', N'PR-1002', N'{"total":"148.00"}'),
             (N'demo.operator', N'purchase.submitted', N'purchase_request', N'PR-1002', N'{}');
  END;

  IF NOT EXISTS (SELECT 1 FROM dbo.knowledge_documents WHERE title = N'Shipment exception handling')
  BEGIN
    INSERT dbo.knowledge_documents(title, body, sensitivity)
      VALUES (N'Shipment exception handling', N'Repeated shipment imports are idempotent by external shipment reference. Invalid rows are rejected into the import error report and do not overwrite the accepted shipment record.', N'internal');
    INSERT dbo.knowledge_document_roles(document_id, role_name)
      SELECT document_id, N'viewer' FROM dbo.knowledge_documents WHERE title = N'Shipment exception handling';
  END;

  INSERT dbo.schema_migrations(version) VALUES (6);
END;
