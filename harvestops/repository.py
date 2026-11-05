from collections.abc import Iterable

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
        with self.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True

    def connect(self):
        import pyodbc

        return pyodbc.connect(self.connection_string())

    @staticmethod
    def rows(cursor) -> list[dict]:
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

    def query(self, sql: str, params: Iterable = ()) -> list[dict]:
        with self.connect() as conn:
            return self.rows(conn.execute(sql, tuple(params)))

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
        return self.query(query, (customer, customer, offset, page_size))

    def shipment_count(self, filters: dict) -> int:
        clauses = ["1=1"]
        params: list = []
        shipment_id = filters.get("shipment_id")
        if shipment_id:
            clauses.append("shipment_id = ?")
            params.append(shipment_id)
        for column, key in (("customer_name", "customer"), ("product_name", "product"), ("facility_name", "facility")):
            value = filters.get(key)
            if value and value != "All":
                clauses.append(f"{column} = ?")
                params.append(value)
        if filters.get("exceptions_only"):
            clauses.append("status = ?")
            params.append("Exception")
        rows = self.query(f"SELECT COUNT_BIG(*) AS total FROM dbo.v_shipment_board WHERE {' AND '.join(clauses)}", params)
        return int(rows[0]["total"])

    def shipment_rows(self, filters: dict, page: int, page_size: int) -> list[dict]:
        clauses = ["1=1"]
        params: list = []
        shipment_id = filters.get("shipment_id")
        if shipment_id:
            clauses.append("shipment_id = ?")
            params.append(shipment_id)
        for column, key in (("customer_name", "customer"), ("product_name", "product"), ("facility_name", "facility")):
            value = filters.get(key)
            if value and value != "All":
                clauses.append(f"{column} = ?")
                params.append(value)
        if filters.get("exceptions_only"):
            clauses.append("status = ?")
            params.append("Exception")
        offset = max(0, page - 1) * page_size
        params.extend([offset, page_size])
        return self.query(
            f"""SELECT shipment_id, customer_name, product_name, facility_name, carrier_name,
                       dock_code, appointment_utc, planned_departure_utc, actual_departure_utc,
                       ordered_qty, shipped_qty, freight_cost, status, row_version
                FROM dbo.v_shipment_board WHERE {' AND '.join(clauses)}
                ORDER BY planned_departure_utc, shipment_id OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
            params,
        )
