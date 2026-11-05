import pyodbc

from .config import Settings


class SqlServerRepository:
    """Small parameterized SQL Server adapter; the demo store is a separate explicit mode."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def connection_string(self) -> str:
        trust = "yes" if self.settings.sql_trust_server_certificate else "no"
        encrypt = "yes" if self.settings.sql_encrypt else "no"
        return (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={self.settings.sql_server};DATABASE={self.settings.sql_database};"
            f"UID={self.settings.sql_user};PWD={self.settings.sql_password};"
            f"Encrypt={encrypt};TrustServerCertificate={trust};"
            f"Connection Timeout={self.settings.sql_connection_timeout};"
        )

    def ping(self) -> bool:
        with pyodbc.connect(self.connection_string()) as conn:
            conn.execute("SELECT 1").fetchone()
        return True

    def shipment_page(self, page: int, page_size: int, customer: str | None = None) -> list[dict]:
        offset = max(0, page - 1) * page_size
        query = """
        SELECT shipment_id, customer_name, product_name, facility_name, carrier_name,
               dock_code, planned_departure_utc, actual_departure_utc, ordered_qty,
               shipped_qty, freight_cost, status, row_version
        FROM dbo.v_shipment_board
        WHERE (? IS NULL OR customer_name = ?)
        ORDER BY planned_departure_utc OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
        """
        with pyodbc.connect(self.connection_string()) as conn:
            return [dict(zip([c[0] for c in cur.description], row, strict=False)) for cur in [conn.execute(query, customer, customer, offset, page_size)] for row in cur]
