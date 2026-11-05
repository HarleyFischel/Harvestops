# Identity and authorization modes

## Development demo mode

Set `APP_ENV=development`, `DEMO_MODE=true`, and `IDENTITY_MODE=demo`. The application creates a server-side demo session for `demo.viewer`, and the development-only selector can switch to `demo.operator`, `demo.approver`, or `demo.admin`. The selector is hidden outside demo mode; authorization is still enforced in service methods and direct routes.

## Microsoft Entra ID mode

Set `DEMO_MODE=false`, `IDENTITY_MODE=entra`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_REDIRECT_URI`, and a shared `SESSION_REDIS_URL`. Register a web application in the tenant, add the exact redirect URI (for example `https://app.example/auth/callback`), and grant the OpenID profile/email sign-in scopes. Use a certificate or secret stored outside source control.

Create app roles named `HarvestOps.Operator`, `HarvestOps.Approver`, and `HarvestOps.Admin`. The callback maps those claims to the internal `operator`, `approver`, and `admin` roles and always grants the authenticated principal `viewer`. Role claims are stored in the server-side session so multiple workers do not rely on process-local identity state. Production rejects demo identity and requires Redis-backed sessions.

`/auth/login` starts the MSAL authorization-code flow with a session-bound state value. `/auth/callback` validates state and exchanges the code. `POST /auth/logout` clears the server-side session. Entra, tenant, client credentials, and cloud redirect behavior were not exercised without tenant credentials.
