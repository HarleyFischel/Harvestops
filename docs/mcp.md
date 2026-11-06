# MCP example

HarvestOps includes a small read-only MCP server using the official Python SDK. Local stdio mode is intended for development:

```bash
python -m harvestops.mcp_server
```

Run the bounded local protocol smoke test with:

```bash
./scripts/test-mcp-stdio.sh
```

It performs an `initialize`, `tools/list`, and authenticated demo-mode `tools/call`
for `SHP-1004`. It does not claim a remote MCP deployment.

The tools are `lookup_shipment`, `list_shipment_exceptions`, and `approved_kpi_definitions`. Each local call requires a known demo principal, validates bounded inputs, reuses the service-layer shipment and knowledge objects, and applies a result limit. The local tests cover successful lookup, exception limits, input validation, and unknown-principal rejection.

The server selects `InMemoryStore` for the explicit demo mode and `SqlServerStore` when `STORAGE_MODE=sqlserver`, so exposed deployments use the same parameterized SQL adapter as the Dash application. Apply migrations separately before starting the MCP process.

For an exposed deployment, set `MCP_EXPOSED=true`, `MCP_AUTH_PUBLIC_KEY`, `MCP_AUTH_ISSUER`, and `MCP_AUTH_AUDIENCE`. Tool calls must include an RS256 token whose verified subject matches `principal`, with `iss`, `aud`, `iat`, `nbf`, `exp`, and a recognized role claim. Missing or invalid configuration fails closed. Do not treat a caller-supplied principal string as authentication.

The exposed transport/gateway and remote deployment are not verified in this repository. Put the MCP server behind an authenticated MCP gateway or equivalent private network boundary, keep the public key in secret/configuration management, rotate signing keys by publishing the new public key before retiring the old one, and never log bearer tokens.
