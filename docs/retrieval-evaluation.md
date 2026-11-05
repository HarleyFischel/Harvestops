# Local retrieval evaluation

This is permission-filtered keyword search, not vector RAG. The fixture in `knowledge/evaluation.json` contains four synthetic queries and expected source citations. Running the fixture with the local search service on 2026-11-05 returned the expected source for 4/4 queries (100% exact-source hit rate). This result is a small deterministic smoke evaluation, not a quality claim for production retrieval. A future vector/hybrid implementation must document its embedding provider/model, index, retrieval method, costs, and permission filtering separately.
