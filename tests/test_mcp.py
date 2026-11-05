import pytest

from harvestops.mcp_server import (
    approved_kpi_definitions,
    list_shipment_exceptions,
    lookup_shipment,
)


def test_mcp_tools_require_principal_and_limit_results():
    result = lookup_shipment("SHP-1001", "demo.viewer")
    assert result["found"] is True
    assert approved_kpi_definitions("demo.viewer")
    assert len(list_shipment_exceptions("demo.viewer", 100)) <= 20
    with pytest.raises(PermissionError):
        lookup_shipment("SHP-1001", "unknown")
