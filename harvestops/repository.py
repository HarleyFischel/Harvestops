from collections.abc import Iterable

from .config import Settings


class SqlServerRepository:
    """Small parameterized SQL Server adapter; the demo store is a separate explicit mode."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def _odbc_value(value: object) -> str:
        """Quote an ODBC value so env-configured punctuation cannot break parsing."""
        return "{" + str(value).replace("}", "}}") + "}"

    def connection_string(self) -> str:
        trust = "yes" if self.settings.sql_trust_server_certificate else "no"
        encrypt = "yes" if self.settings.sql_encrypt else "no"
        connection = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={self._odbc_value(self.settings.sql_server)};"
            f"DATABASE={self._odbc_value(self.settings.sql_database)};"
            f"Encrypt={encrypt};TrustServerCertificate={trust};"
            f"Connection Timeout={self.settings.sql_connection_timeout};"
        )
        if self.settings.sql_auth_mode == "sql_login":
            connection += (
                f"UID={self._odbc_value(self.settings.sql_user)};"
                f"PWD={self._odbc_value(self.settings.sql_password)};"
            )
        return connection

    def ping(self) -> bool:
        with self.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True

    def connect(self):
        import pyodbc

        if self.settings.sql_auth_mode == "azure_identity":
            import struct

            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential(
                managed_identity_client_id=self.settings.azure_client_id or None
            )
            token = credential.get_token("https://database.windows.net/.default").token
            token_bytes = token.encode("utf-16-le")
            access_token = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
            return pyodbc.connect(self.connection_string(), attrs_before={1256: access_token})
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
        where, params = self._shipment_filter(filters)
        rows = self.query(
            f"SELECT COUNT_BIG(*) AS total FROM dbo.v_shipment_board WHERE {where}", params
        )
        return int(rows[0]["total"])

    def shipment_rows(self, filters: dict, page: int, page_size: int) -> list[dict]:
        where, params = self._shipment_filter(filters)
        offset = max(0, page - 1) * page_size
        params.extend([offset, page_size])
        return self.query(
            f"""SELECT shipment_id, customer_name, product_name, facility_name, carrier_name,
                       dock_code, appointment_utc, planned_departure_utc, actual_departure_utc,
                       ordered_qty, shipped_qty, freight_cost, status, row_version
                FROM dbo.v_shipment_board WHERE {where}
                ORDER BY planned_departure_utc, shipment_id OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
            params,
        )

    def shipment_by_id(self, shipment_id: str) -> dict | None:
        rows = self.shipment_rows({"shipment_id": shipment_id}, 1, 1)
        return rows[0] if rows else None

    @staticmethod
    def _shipment_filter(filters: dict) -> tuple[str, list]:
        clauses = ["1=1"]
        params: list = []
        shipment_id = filters.get("shipment_id")
        if shipment_id:
            clauses.append("shipment_id = ?")
            params.append(shipment_id)
        for column, key in (
            ("customer_name", "customer"),
            ("product_name", "product"),
            ("facility_name", "facility"),
        ):
            value = filters.get(key)
            if value and value != "All":
                clauses.append(f"{column} = ?")
                params.append(value)
        if filters.get("start_date"):
            clauses.append("planned_departure_utc >= CAST(? AS date)")
            params.append(filters["start_date"])
        if filters.get("end_date"):
            clauses.append("planned_departure_utc < DATEADD(day, 1, CAST(? AS date))")
            params.append(filters["end_date"])
        if filters.get("exceptions_only"):
            clauses.append("status = ?")
            params.append("Exception")
        return " AND ".join(clauses), params

    def shipment_kpis(self, filters: dict) -> dict:
        where, params = self._shipment_filter(filters)
        rows = self.query(
            f"""SELECT COUNT_BIG(*) AS shipment_volume,
                       COALESCE(SUM(ordered_qty), 0) AS ordered_qty,
                       COALESCE(SUM(shipped_qty), 0) AS shipped_qty,
                       COALESCE(SUM(freight_cost), 0) AS freight_cost,
                       COALESCE(SUM(CASE WHEN actual_departure_utc IS NOT NULL AND status <> 'Cancelled' THEN 1 ELSE 0 END), 0) AS closed_count,
                       COALESCE(SUM(CASE WHEN actual_departure_utc IS NOT NULL AND status <> 'Cancelled' AND actual_departure_utc <= planned_departure_utc THEN 1 ELSE 0 END), 0) AS on_time_count
                FROM dbo.v_shipment_board WHERE {where}""",
            params,
        )
        return rows[0]

    def production_kpis(self, filters: dict) -> dict:
        clauses = ["1=1"]
        params: list = []
        for column, key in (("f.facility_name", "facility"), ("p.product_name", "product")):
            value = filters.get(key)
            if value and value != "All":
                clauses.append(f"{column} = ?")
                params.append(value)
        if filters.get("start_date"):
            clauses.append("pr.run_date >= CAST(? AS date)")
            params.append(filters["start_date"])
        if filters.get("end_date"):
            clauses.append("pr.run_date <= CAST(? AS date)")
            params.append(filters["end_date"])
        customer = filters.get("customer")
        if customer and customer != "All":
            customer_scope = [
                "sx.facility_id = pr.facility_id",
                "sx.product_id = pr.product_id",
                "cx.customer_name = ?",
            ]
            customer_params = [customer]
            if filters.get("start_date"):
                customer_scope.append("sx.planned_departure_utc >= CAST(? AS date)")
                customer_params.append(filters["start_date"])
            if filters.get("end_date"):
                customer_scope.append("sx.planned_departure_utc < DATEADD(day, 1, CAST(? AS date))")
                customer_params.append(filters["end_date"])
            clauses.append(
                "EXISTS (SELECT 1 FROM dbo.shipments sx "
                "JOIN dbo.customers cx ON cx.customer_id = sx.customer_id WHERE "
                + " AND ".join(customer_scope)
                + ")"
            )
            params.extend(customer_params)
        rows = self.query(
            f"""SELECT COALESCE(SUM(pr.output_qty), 0) AS production_output,
                       COALESCE(SUM(pr.labor_hours), 0) AS labor_hours
                FROM dbo.production_runs pr
                JOIN dbo.facilities f ON f.facility_id = pr.facility_id
                JOIN dbo.products p ON p.product_id = pr.product_id
                WHERE {' AND '.join(clauses)}""",
            params,
        )
        return rows[0]

    def dashboard_volume(self, filters: dict) -> list[dict]:
        where, params = self._shipment_filter(filters)
        return self.query(
            f"""SELECT facility_name AS label, COALESCE(SUM(shipped_qty), 0) AS shipped_qty
                FROM dbo.v_shipment_board
                WHERE {where}
                GROUP BY facility_name
                ORDER BY facility_name""",
            params,
        )

    def dashboard_service(self, filters: dict) -> dict:
        where, params = self._shipment_filter(filters)
        rows = self.query(
            f"""SELECT COUNT_BIG(*) AS shipment_count,
                       COALESCE(SUM(CASE WHEN actual_departure_utc IS NOT NULL
                                           AND status <> 'Cancelled'
                                           AND actual_departure_utc <= planned_departure_utc
                                        THEN 1 ELSE 0 END), 0) AS on_time
                FROM dbo.v_shipment_board
                WHERE {where}""",
            params,
        )
        row = rows[0]
        return {
            "on_time": int(row["on_time"]),
            "late_open": int(row["shipment_count"]) - int(row["on_time"]),
        }

    def shipment_exceptions(self, filters: dict, limit: int = 50) -> list[dict]:
        where, params = self._shipment_filter(filters)
        limit = max(1, min(int(limit), 100))
        params.append(limit)
        return self.query(
            f"""SELECT shipment_id, customer_name, product_name, facility_name, carrier_name,
                       dock_code, appointment_utc, planned_departure_utc, actual_departure_utc,
                       ordered_qty, shipped_qty, freight_cost, status, row_version
                FROM dbo.v_shipment_board
                WHERE {where}
                  AND (status = 'Exception'
                       OR (actual_departure_utc IS NOT NULL AND actual_departure_utc > planned_departure_utc)
                       OR (ordered_qty > 0 AND shipped_qty / ordered_qty < CAST(0.95 AS decimal(3,2))))
                ORDER BY planned_departure_utc, shipment_id
                OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY""",
            params,
        )
