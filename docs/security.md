# Security checklist and threat model

Implemented: parameterized SQL; explicit roles in every state-changing service; server-side demo identity; fail-closed production demo bypass; secure/HTTP-only/SameSite cookies; short session lifetime; Redis-backed server-side sessions when `SESSION_REDIS_URL` is configured; session-bound CSRF tokens for state-changing Dash callbacks and the import API, with a SameSite double-submit cookie fallback for Dash transport; formula-injection prefixing in CSV; redacted readiness errors; Dash-compatible CSP and security headers; bounded MCP inputs; asymmetric JWT validation with issuer/audience/expiry/not-before/algorithm/kid/replay checks; audit events; cross-user purchase-read scoping.

Verified by tests: unauthorized export, unauthorized workflow change, stale update, self-approval, production demo rejection, and idempotent import.

Proposed hardening before production: CSRF coverage for any future write forms, Entra group/app-role mapping review, Key Vault references, WAF/rate limiting, full browser authorization tests, and security review of the portal trust model. The CI workflow now contains blocking dependency and secret scanning steps, but hosted execution still requires repository checks to run. The portal example is not an implementation of Pero Central.

Threats considered: over-privileged operators, stale writes, CSV formula execution, token replay/tampering, prompt/context leakage, unsafe remote MCP exposure, and database credential leakage. External knowledge providers receive only permission-filtered context and must be explicitly configured.
