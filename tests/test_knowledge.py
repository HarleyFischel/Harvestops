import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from harvestops.domain import User
from harvestops.knowledge import DOCUMENTS, KnowledgeService


def test_local_search_is_permission_filtered():
    service = KnowledgeService()
    viewer = User("viewer", "Viewer", {"viewer"})
    approver = User("approver", "Approver", {"approver"})
    assert service.search("purchase approval", viewer) == []
    assert service.search("purchase approval", approver)[0].source == "knowledge/purchasing.md"


def test_claude_mode_is_graceful_without_credentials():
    user = User("v", "Viewer", {"viewer"})
    result = KnowledgeService().answer_with_claude(
        "What is fill rate?",
        KnowledgeService().search("fill rate", user),
        user,
    )
    assert result["status"] == "unavailable"
    assert "Local search" in result["message"]


def test_provider_boundary_rechecks_document_permissions(monkeypatch):
    service = KnowledgeService(api_key="test-key")
    viewer = User("v", "Viewer", {"viewer"})
    documents = [
        service.search("fill rate", viewer)[0],
        next(
            doc for doc in service.search("purchase approval", User("a", "Approver", {"approver"}))
        ),
    ]
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"content":[{"type":"text","text":"Answer"}],"usage":{"input_tokens":4,"output_tokens":2}}'

    def fake_urlopen(request, timeout):
        captured["body"] = request.data.decode()
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("harvestops.knowledge.urlrequest.urlopen", fake_urlopen)
    result = service.answer_with_claude("What is fill rate?", documents, viewer)

    assert result["status"] == "ok"
    assert "KPI definitions" in captured["body"]
    assert "Purchase controls" not in captured["body"]
    assert captured["timeout"] == 10


@pytest.mark.parametrize(
    "failure", [TimeoutError(), HTTPError("https://api.anthropic.com", 429, "rate", {}, None)]
)
def test_provider_failures_are_graceful(monkeypatch, failure):
    service = KnowledgeService(api_key="test-key")
    user = User("v", "Viewer", {"viewer"})

    def failed_urlopen(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr("harvestops.knowledge.urlrequest.urlopen", failed_urlopen)
    result = service.answer_with_claude(
        "What is fill rate?", service.search("fill rate", user), user
    )

    assert result["status"] == "error"
    assert "local search remains available" in result["message"].lower()


def test_provider_answer_requires_principal_before_external_call(monkeypatch):
    called = False

    def unexpected_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not be called without a principal")

    monkeypatch.setattr("harvestops.knowledge.urlrequest.urlopen", unexpected_urlopen)
    result = KnowledgeService(api_key="test-key").answer_with_claude(
        "question", list(DOCUMENTS), None
    )

    assert result["status"] == "forbidden"
    assert called is False


def test_retrieval_evaluation_fixture_hits_expected_sources():
    fixture = json.loads(Path("knowledge/evaluation.json").read_text())
    service = KnowledgeService()
    user = User("viewer", "Viewer", {"viewer", "operator", "approver", "admin"})
    hits = [service.search(item["query"], user)[0].source for item in fixture]
    assert hits == [item["expected_source"] for item in fixture]
