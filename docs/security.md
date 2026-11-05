# Security checklist and threat model

Implemented: parameterized SQL; explicit roles in every state-changing service; server-side demo identity; fail-closed production demo bypass; secure/HTTP-only/SameSite cookies; short session lifetime; formula-injection prefixing in CSV; redacted readiness errors; bounded MCP inputs; asymmetric JWT validation with issuer/audience/expiry/not-before/algorithm/kid/replay checks; audit events.

Verified by tests: unauthorized export, unauthorized workflow change, stale update, self-approval, production demo rejection, and idempotent import.

Proposed hardening before production: central distributed session storage, CSRF middleware for all non-Dash write forms, Entra group/app-role mapping, Key Vault references, WAF/rate limiting, dependency and secret scanner enforcement, full browser authorization tests, and security review of the portal trust model. The portal example is not an implementation of Pero Central.

Threats considered: over-privileged operators, stale writes, CSV formula execution, token replay/tampering, prompt/context leakage, unsafe remote MCP exposure, and database credential leakage. External knowledge providers receive only permission-filtered context and must be explicitly configured.
