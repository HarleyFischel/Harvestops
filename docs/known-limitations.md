# Known limitations

The demo store is process-local and intentionally not durable; SQL Server mode is the durable target. The optional Claude adapter is a boundary and local search is the verified no-key path. The import API has a session-bound CSRF token check; a production deployment should extend the same protection to every state-changing browser callback and use distributed session storage. SQL migrations use SQL Server-compatible T-SQL and require real SQL Server verification. Azure resources are not provisioned automatically.
