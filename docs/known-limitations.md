# Known limitations

The demo store is process-local and intentionally not durable; SQL Server mode is the durable target. The optional Claude adapter is a boundary and local search is the verified no-key path. Dash callbacks use the same service rules, while a production deployment should add CSRF middleware and distributed session storage. SQL migrations use SQL Server-compatible T-SQL and require real SQL Server verification. Azure resources are not provisioned automatically.
