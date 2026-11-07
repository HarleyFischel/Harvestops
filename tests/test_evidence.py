import json

import requests

from harvestops.build_info import BuildInfo
from harvestops.config import Settings
from harvestops.domain import User
from harvestops.evidence import (
    EvidenceError,
    EvidenceService,
    GitHubEvidenceAdapter,
    validate_snapshot,
)


def snapshot_payload():
    return {
        "schema_version": 1,
        "snapshot_type": "test",
        "repository": "HarleyFischel/Harvestops",
        "source_commit": "abc123",
        "collected_at_utc": "2026-11-07T00:00:00Z",
        "scope": "test",
        "sources": [
            {"label": "Public", "url": "https://example.test", "visibility": "public"},
            {"label": "Server", "url": "https://example.test/private", "visibility": "server-only"},
        ],
        "ci_runs": [
            {
                "id": "1",
                "label": "CI",
                "status": "passed",
                "commit": "abc123",
                "url": "https://example.test",
            }
        ],
        "quality": [
            {
                "id": "q",
                "label": "Quality",
                "status": "passed",
                "summary": "ok",
                "private_notes": "secret",
            }
        ],
        "releases": [],
        "support_documents": [],
        "open_work": [],
    }


def build_info():
    return BuildInfo("0.1.0", "abc123", "2026-11-07T00:00:00Z", "test", "Unknown")


def test_snapshot_validation_rejects_bad_status_and_repository():
    payload = snapshot_payload()
    payload["repository"] = "not-a-repository"
    try:
        validate_snapshot(payload)
    except ValueError as exc:
        assert "repository" in str(exc)
    else:
        raise AssertionError("invalid repository must be rejected")

    payload = snapshot_payload()
    payload["ci_runs"][0]["status"] = "fabricated"
    try:
        validate_snapshot(payload)
    except ValueError as exc:
        assert "status" in str(exc)
    else:
        raise AssertionError("invalid status must be rejected")


def test_viewer_projection_hides_server_only_fields(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot_payload()), encoding="utf-8")
    service = EvidenceService(
        Settings(secret_key="test", evidence_snapshot_path=str(path)), build_info()
    )
    viewer = service.view_for(User("viewer", "Viewer", {"viewer"}))
    assert [source["label"] for source in viewer["sources"]] == ["Public"]
    assert "private_notes" not in viewer["quality"][0]
    assert viewer["runtime_commit_matches_snapshot"] is True


def test_malformed_snapshot_is_unknown_not_success(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text("{not-json", encoding="utf-8")
    service = EvidenceService(
        Settings(secret_key="test", evidence_snapshot_path=str(path)), build_info()
    )
    view = service.view_for(User("viewer", "Viewer", {"viewer"}))
    assert view["evidence_state"] == "unknown"
    assert view["source_commit"] == "Unknown"
    assert view["ci_runs"] == []


def test_github_adapter_maps_running_status_and_is_repository_scoped(monkeypatch):
    responses = {
        "/repos/HarleyFischel/Harvestops": {"default_branch": "main"},
        "/repos/HarleyFischel/Harvestops/commits/main": {"sha": "def456"},
        "/repos/HarleyFischel/Harvestops/actions/runs": {
            "workflow_runs": [
                {
                    "id": 2,
                    "name": "CI",
                    "status": "in_progress",
                    "conclusion": None,
                    "head_sha": "def456",
                    "html_url": "https://example.test/run/2",
                    "updated_at": "2026-11-07T00:00:00Z",
                }
            ]
        },
    }

    class Response:
        def __init__(self, value):
            self.value = value
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self.value

    adapter = GitHubEvidenceAdapter(
        "fixture-credential", "HarleyFischel/Harvestops", "https://api.test"
    )
    monkeypatch.setattr(
        adapter.session,
        "get",
        lambda url, params=None, timeout=None: Response(
            responses[url.removeprefix("https://api.test")]
        ),
    )
    snapshot = adapter.collect()
    assert snapshot["source_commit"] == "def456"
    assert snapshot["ci_runs"][0]["status"] == "running"
    assert "Authorization" in adapter.session.headers


def test_snapshot_mode_without_token_is_available(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot_payload()), encoding="utf-8")
    settings = Settings(
        secret_key="test", evidence_snapshot_path=str(path), github_evidence_token=""
    )
    service = EvidenceService(settings, build_info())
    assert service.state() == "passed"
    assert service.view_for(User("viewer", "Viewer", {"viewer"}))["source_commit"] == "abc123"


def test_live_timeout_keeps_last_snapshot_and_marks_it_stale(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot_payload()), encoding="utf-8")
    settings = Settings(
        secret_key="test",
        evidence_snapshot_path=str(path),
        github_evidence_token="server-token",
        evidence_cache_seconds=0,
    )
    service = EvidenceService(settings, build_info())
    monkeypatch.setattr(
        GitHubEvidenceAdapter,
        "collect",
        lambda self, prior=None: (_ for _ in ()).throw(requests.Timeout()),
    )
    view = service.view_for(User("viewer", "Viewer", {"viewer"}))
    assert view["source_commit"] == "abc123"
    assert view["evidence_state"] == "stale"


def test_github_rate_limit_is_explicit(monkeypatch):
    adapter = GitHubEvidenceAdapter(
        "fixture-credential", "HarleyFischel/Harvestops", "https://api.test"
    )

    class Response:
        status_code = 429

        def raise_for_status(self):
            raise AssertionError("rate limit should be handled before raise_for_status")

    monkeypatch.setattr(adapter.session, "get", lambda *args, **kwargs: Response())
    try:
        adapter._get("/repos/HarleyFischel/Harvestops")
    except EvidenceError as exc:
        assert "rate limit" in str(exc)
    else:
        raise AssertionError("rate limits must be explicit")
