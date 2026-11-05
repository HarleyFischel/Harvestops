# Coding standards

- Python 3.11–3.13, four-space indentation, type hints at service boundaries, and Ruff before commit.
- Keep Dash callbacks thin; put validation, authorization, transactions, and state transitions in services/repositories.
- Use parameterized SQL only. Store UTC timestamps and use `Decimal` for quantities and currency.
- Prefer small pure functions and deterministic fixtures. Add a negative test for every authorization or transition rule.
- Never log secrets, prompts, connection strings, or raw tokens. Do not commit `.env` files or fixed credentials.
- Name migrations monotonically, make them backward-compatible where practical, and never run migrations from web workers.
