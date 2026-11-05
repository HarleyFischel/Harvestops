"""Permission-filtered local search with an optional Claude answer adapter."""

import json
from dataclasses import dataclass
from urllib import request as urlrequest

from .domain import User


@dataclass(frozen=True)
class KnowledgeDocument:
    title: str
    body: str
    source: str
    roles: frozenset[str] = frozenset({"viewer", "operator", "approver", "admin"})


DOCUMENTS = (
    KnowledgeDocument("KPI definitions", "Fill rate is shipped quantity divided by ordered quantity. On-time rate is on-time departures divided by closed shipments.", "knowledge/kpi-definitions.md"),
    KnowledgeDocument("Dock exception playbook", "For a late departure, confirm appointment, carrier arrival, and quantity before changing status or escalating.", "knowledge/dock-operations.md", frozenset({"viewer", "operator", "admin"})),
    KnowledgeDocument("Purchase controls", "A requester cannot approve their own request. Approval decisions require the pending state and current version.", "knowledge/purchasing.md", frozenset({"approver", "admin"})),
    KnowledgeDocument("Shipment exception handling", "Repeated shipment imports are idempotent by external shipment reference. Invalid rows are rejected into the import error report and do not overwrite the accepted shipment record.", "knowledge/shipment-exceptions.md"),
)


class KnowledgeService:
    def __init__(self, api_key: str = "", model: str = "claude-3-5-haiku-latest"):
        self.api_key = api_key
        self.model = model

    @staticmethod
    def _allowed(user: User | None, document: KnowledgeDocument) -> bool:
        return bool(user and user.roles.intersection(document.roles))

    def search(self, query: str, user: User | None, limit: int = 3) -> list[KnowledgeDocument]:
        terms = [term for term in (query or "").lower().split() if term]
        if not terms:
            return []
        scored = []
        for document in DOCUMENTS:
            if self._allowed(user, document):
                text = f"{document.title} {document.body}".lower()
                score = sum(term in text for term in terms)
                if score:
                    scored.append((score, document))
        scored.sort(key=lambda item: -item[0])
        return [document for _, document in scored[: max(1, min(limit, 3))]]

    def answer_with_claude(self, query: str, documents: list[KnowledgeDocument]) -> dict:
        if not self.api_key:
            return {"status": "unavailable", "message": "Claude answer mode is not configured; choose Local search.", "usage": {}}
        context = "\n\n".join(f"[{doc.source}] {doc.title}: {doc.body}" for doc in documents)[:6000]
        payload = json.dumps({"model": self.model, "max_tokens": 300, "system": "Answer only from the supplied HarvestOps operating documents. Say when the documents do not answer the question.", "messages": [{"role": "user", "content": f"Question: {query[:500]}\n\nSources:\n{context}"}]}).encode()
        req = urlrequest.Request("https://api.anthropic.com/v1/messages", data=payload, headers={"content-type": "application/json", "x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())
            text = " ".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
            usage = {key: data.get("usage", {}).get(key) for key in ("input_tokens", "output_tokens")}
            return {"status": "ok", "message": text[:4000], "usage": usage}
        except Exception as exc:  # provider failures are user-facing, not process-fatal
            return {"status": "error", "message": f"Claude answer unavailable ({type(exc).__name__}); local search remains available.", "usage": {}}
