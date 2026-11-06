#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PYTHON_BIN:-}" ]]; then
  for candidate in .venv/bin/python .venv312/bin/python; do
    if [[ -x "$candidate" ]]; then PYTHON_BIN="$candidate"; break; fi
  done
fi
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || command -v python || command -v python3)}"

response="$({
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"harvestops-check","version":"1.0"}}}'
  printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
  printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
  printf '%s\n' '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"lookup_shipment","arguments":{"shipment_id":"SHP-1004","principal":"demo.operator"}}}'
  # Keep stdin open long enough for a cold CI runner to flush the async stdio response.
  sleep 2
} | APP_ENV=development DEMO_MODE=true IDENTITY_MODE=demo STORAGE_MODE=demo SECRET_KEY=local-validation "$PYTHON_BIN" -m harvestops.mcp_server 2>/dev/null)"

grep -q '"protocolVersion":"2025-06-18"' <<<"$response"
grep -q '"name":"lookup_shipment"' <<<"$response"
grep -q '"name":"list_shipment_exceptions"' <<<"$response"
grep -q '"name":"approved_kpi_definitions"' <<<"$response"
# The tool result is JSON-encoded inside the MCP text content, so assert its stable ID.
grep -q 'SHP-1004' <<<"$response"
printf 'MCP stdio verification passed.\n'
