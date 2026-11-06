# Known limitations

The demo store is process-local and intentionally not durable; SQL Server mode is the durable target. Production sessions require the configured shared Redis endpoint; the demo's signed-cookie session is not a multi-replica durability guarantee. The optional Claude adapter is bounded and local search is the verified no-key path. SQL migrations use SQL Server-compatible T-SQL and require real SQL Server verification. Azure resources are not provisioned automatically.
