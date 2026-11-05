# Architecture and decisions

The application has four boundaries: harvestops/web.py owns Dash/Flask presentation and thin callbacks; harvestops/services.py owns business rules and an explicit deterministic demo store; harvestops/repository.py owns parameterized pyodbc access; and db/ owns versioned T-SQL. This separation keeps workflow rules testable without a browser.

The Mac uses ARM64 Python/application containers and connects to an external x86-64 Linux/Proxmox SQL Server or Azure SQL. SQL Server Developer edition is supported for nonproduction development under its license. SQLite is not a fallback and is not used.

All timestamps are stored in UTC. The UI labels the display policy and uses DISPLAY_TIMEZONE; timezone conversion belongs in the presentation adapter. Synthetic data is visibly labeled.
