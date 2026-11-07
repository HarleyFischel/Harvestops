# Known limitations

The demo store is process-local and intentionally not durable; SQL Server mode is the durable target. The M2 emulated SQL profile has verified versioned migrations 001–009, SQL integration tests, restart persistence, and a copy-only backup/restore smoke test against the preserved named volume. That evidence is local development evidence, not a production backup policy.

Production sessions require the configured shared Redis endpoint; the demo's signed-cookie session is not a multi-replica durability guarantee. The optional Claude adapter is bounded and local search is the verified no-key path. The SQL migrations are compatible with SQL Server/Azure SQL, but deployment to an external Proxmox host and Azure SQL remains environment-dependent and unverified here. Azure resources are not provisioned automatically.
