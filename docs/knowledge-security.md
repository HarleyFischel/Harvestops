# Knowledge document security

Operating procedures are tracked under the repository-level `knowledge/` directory and are copied into the application image as private application data. They are not duplicated under `harvestops/assets`, so Dash's public asset route cannot serve them.

Search, citations, Claude context, and MCP tools use the same document inventory and role policy. Search results link to `/knowledge/documents/<basename>`. That route requires an authenticated principal, resolves only an allow-listed basename, rejects path traversal, and checks the document's roles before reading the file. Missing documents return 404; an authenticated but unauthorized principal receives 403 without document content; unauthenticated requests receive 401. The route serves inline Markdown for citations and does not expose arbitrary filesystem paths.

The local keyword search is the default and does not require an API key. The optional Claude adapter re-checks authorization immediately before sending context and applies request/token limits. Remote provider failures leave local search available. The official MCP tools reuse the same permission boundary and are read-only.

The direct-request regression tests cover viewer access to the approver-only purchasing procedure, former static URLs, traversal-shaped paths, and an authorized approver citation. Live remote provider and remote MCP deployment checks remain account-dependent.
