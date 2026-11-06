# Identity and authorization modes

## Development demo mode

Set `APP_ENV=development`, `DEMO_MODE=true`, and `IDENTITY_MODE=demo`. The application creates a server-side demo session for `demo.viewer`, and the development-only selector can switch to `demo.operator`, `demo.approver`, or `demo.admin`. The selector is hidden outside demo mode; authorization is still enforced in service methods and direct routes.

## Microsoft Entra ID mode

Set `DEMO_MODE=false`, `IDENTITY_MODE=entra`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_REDIRECT_URI`, and a shared `SESSION_REDIS_URL`. Register a web application in the tenant, add the exact redirect URI (for example `https://app.example/auth/callback`), and grant the OpenID profile/email sign-in scopes. Use a certificate or secret stored outside source control.

Create app roles named `HarvestOps.Operator`, `HarvestOps.Approver`, and `HarvestOps.Admin`. The callback maps those claims to the internal `operator`, `approver`, and `admin` roles and always grants the authenticated principal `viewer`. Role claims are stored in the server-side session so multiple workers do not rely on process-local identity state. Production rejects demo identity and requires Redis-backed sessions.

`/auth/login` starts MSAL's supported `initiate_auth_code_flow` with an empty application-scope list. MSAL adds the reserved OpenID scopes and creates the nonce, PKCE verifier/challenge, and state-bound flow. The flow is stored server-side; `/auth/callback` accepts the registered `form_post` response and passes that exact flow to `acquire_token_by_auth_code_flow`, which validates the state, nonce, and PKCE exchange. The session identifier is regenerated after successful sign-in when the configured server-side session interface supports it. `POST /auth/logout` clears the server-side session. The adapter and negative paths are covered by local tests with mocked discovery/token responses; Entra tenant credentials, live redirect behavior, and Microsoft sign-in remain unverified until account configuration is supplied.
