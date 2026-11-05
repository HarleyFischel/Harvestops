# Architecture and decisions

The application has four boundaries: harvestops/web.py owns Dash/Flask presentation and thin callbacks; harvestops/services.py and harvestops/sql_store.py own business rules over demo or SQL persistence; harvestops/repository.py owns parameterized pyodbc access; and db/ owns versioned T-SQL. Knowledge, identity, token exchange, and MCP are separate adapters. This separation keeps workflow rules testable without a browser.

The Mac uses ARM64 Python/application containers and connects to an external x86-64 Linux/Proxmox SQL Server or Azure SQL. SQL Server Developer edition is supported for nonproduction development under its license. SQLite is not a fallback and is not used.

All timestamps are stored in UTC. The UI labels the display policy and uses DISPLAY_TIMEZONE; timezone conversion belongs in the presentation adapter. Synthetic data is visibly labeled.
