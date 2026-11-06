# Knowledge assistant modes

Local search is deterministic, permission-filtered keyword search over synthetic operating procedures. It is deliberately not called vector RAG. Results include source citations and the UI labels the mode as `Local search`.

The optional Claude adapter is enabled only when `CLAUDE_API_KEY` is configured. It re-checks the caller principal and document permissions immediately before sending context, caps the question/context and response size, applies a timeout, exposes usage metadata, and returns graceful provider errors without logging prompts or credentials. The adapter has not been called against a paid provider in this environment.

The four-query fixture in `knowledge/evaluation.json` is a deterministic exact-source smoke evaluation; its result is recorded in [retrieval evaluation](retrieval-evaluation.md). A future vector or hybrid implementation must document its embedding provider/model, index, retrieval method, cost, and authorization boundary separately.
