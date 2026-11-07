"""Structured SDLC evidence with an offline snapshot and optional GitHub adapter."""

from __future__ import annotations

import copy
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import requests

from .build_info import BuildInfo
from .config import Settings
from .domain import User

log = logging.getLogger("harvestops.evidence")

SNAPSHOT_SCHEMA_VERSION = 1
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
STATUS_VALUES = {
    "passed",
    "failed",
    "running",
    "skipped",
    "not_configured",
    "unverified",
    "stale",
    "unknown",
}
GITHUB_STATUS_MAP = {
    "queued": "running",
    "in_progress": "running",
    "failure": "failed",
    "timed_out": "failed",
    "cancelled": "failed",
    "action_required": "failed",
    "neutral": "skipped",
    "skipped": "skipped",
    "success": "passed",
}


class EvidenceError(ValueError):
    """Raised when an evidence snapshot is malformed or unsafe."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bounded_text(value: Any, field: str, max_length: int = 4000) -> str:
    if not isinstance(value, str) or len(value) > max_length:
        raise EvidenceError(f"{field} must be a bounded string")
    return value


def _status(value: Any, field: str) -> str:
    value = _bounded_text(value, field, 32)
    if value not in STATUS_VALUES:
        raise EvidenceError(f"{field} has an unsupported status")
    return value


def validate_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Validate the small JSON contract before any snapshot data reaches the UI."""
    if not isinstance(snapshot, dict):
        raise EvidenceError("snapshot must be an object")
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise EvidenceError("unsupported evidence schema version")
    repository = snapshot.get("repository")
    if not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository):
        raise EvidenceError("snapshot repository is invalid")
    for field in ("source_commit", "collected_at_utc", "scope"):
        _bounded_text(snapshot.get(field), field, 200)
    if not isinstance(snapshot.get("sources"), list) or len(snapshot["sources"]) > 40:
        raise EvidenceError("sources must be a bounded list")
    for source in snapshot["sources"]:
        if not isinstance(source, dict):
            raise EvidenceError("source entries must be objects")
        _bounded_text(source.get("label"), "source.label", 160)
        _bounded_text(source.get("url"), "source.url", 500)
        _bounded_text(source.get("visibility", "public"), "source.visibility", 32)
    for collection, limit in (
        ("ci_runs", 30),
        ("quality", 40),
        ("releases", 30),
        ("open_work", 30),
        ("support_documents", 30),
    ):
        value = snapshot.get(collection, [])
        if not isinstance(value, list) or len(value) > limit:
            raise EvidenceError(f"{collection} must be a bounded list")
        for item in value:
            if not isinstance(item, dict):
                raise EvidenceError(f"{collection} entries must be objects")
            if "status" in item:
                _status(item["status"], f"{collection}.status")
            for key, max_length in (
                ("id", 160),
                ("label", 240),
                ("summary", 1600),
                ("commit", 160),
                ("url", 500),
                ("collected_at_utc", 80),
            ):
                if key in item:
                    _bounded_text(item[key], f"{collection}.{key}", max_length)
    return copy.deepcopy(snapshot)


class GitHubEvidenceAdapter:
    """Read-only, repository-scoped GitHub API adapter."""

    def __init__(self, token: str, repository: str, api_url: str, timeout: float = 5.0):
        if not token:
            raise EvidenceError("GitHub token is not configured")
        if not REPOSITORY_RE.fullmatch(repository):
            raise EvidenceError("GitHub repository must be owner/name")
        self.repository = repository
        self.base_url = api_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        if response.status_code == 429:
            raise EvidenceError("GitHub evidence rate limit reached")
        response.raise_for_status()
        return response.json()

    def collect(self, prior: dict[str, Any] | None = None) -> dict[str, Any]:
        repo = self._get(f"/repos/{self.repository}")
        default_branch = repo.get("default_branch") or "main"
        branch_commit = self._get(f"/repos/{self.repository}/commits/{default_branch}")
        runs = self._get(
            f"/repos/{self.repository}/actions/runs",
            {"branch": default_branch, "per_page": 10},
        )
        ci_runs = []
        for run in (runs.get("workflow_runs") or [])[:10]:
            conclusion = run.get("conclusion")
            raw_status = (conclusion or run.get("status") or "unknown").lower()
            status = GITHUB_STATUS_MAP.get(raw_status, raw_status)
            if status not in STATUS_VALUES:
                status = "unknown"
            ci_runs.append(
                {
                    "id": str(run.get("id", "unknown")),
                    "label": run.get("name") or "GitHub Actions",
                    "status": status,
                    "conclusion": conclusion or "unknown",
                    "commit": run.get("head_sha") or "Unknown",
                    "url": run.get("html_url") or "",
                    "scope": "hosted-default-branch",
                    "collected_at_utc": run.get("updated_at") or utc_now_iso(),
                }
            )
        now = utc_now_iso()
        return validate_snapshot(
            {
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "snapshot_type": "github-read-only",
                "repository": self.repository,
                "source_commit": branch_commit.get("sha") or "Unknown",
                "collected_at_utc": now,
                "scope": "configured repository metadata and workflow summaries",
                "sources": [
                    {
                        "label": "GitHub repository API",
                        "url": f"https://github.com/{self.repository}",
                        "visibility": "server-only",
                    },
                    {
                        "label": "GitHub Actions API",
                        "url": f"https://github.com/{self.repository}/actions",
                        "visibility": "server-only",
                    },
                ],
                "ci_runs": ci_runs,
                "quality": [],
                "releases": [],
                "support_documents": [],
                "open_work": [],
            }
        )


class EvidenceService:
    """Loads validated snapshots and optionally refreshes them from GitHub."""

    def __init__(
        self, settings: Settings, build_info: BuildInfo, snapshot_path: Path | None = None
    ):
        self.settings = settings
        self.build_info = build_info
        self.snapshot_path = snapshot_path or Path(settings.evidence_snapshot_path)
        self._snapshot: dict[str, Any] | None = None
        self._loaded_at = 0.0
        self._error: str | None = None
        self._lock = Lock()
        self._load_snapshot()

    def _load_snapshot(self) -> None:
        try:
            self._snapshot = validate_snapshot(
                json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            )
            self._error = None
        except (OSError, json.JSONDecodeError, EvidenceError) as exc:
            self._snapshot = None
            self._error = str(exc)

    def _try_live_refresh(self) -> None:
        if not self.settings.github_evidence_token:
            return
        now = datetime.now(timezone.utc).timestamp()
        if now - self._loaded_at < self.settings.evidence_cache_seconds:
            return
        with self._lock:
            now = datetime.now(timezone.utc).timestamp()
            if now - self._loaded_at < self.settings.evidence_cache_seconds:
                return
            try:
                adapter = GitHubEvidenceAdapter(
                    self.settings.github_evidence_token,
                    self.settings.github_repository,
                    self.settings.github_api_url,
                    self.settings.github_evidence_timeout,
                )
                self._snapshot = adapter.collect(self._snapshot)
                self._error = None
                self._loaded_at = now
            except (EvidenceError, requests.RequestException, ValueError) as exc:
                self._error = "GitHub evidence refresh failed"
                self._loaded_at = now
                log.warning("GitHub evidence refresh failed: %s", type(exc).__name__)

    def snapshot(self) -> dict[str, Any]:
        self._try_live_refresh()
        if self._snapshot is None:
            return {
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "snapshot_type": "unavailable",
                "repository": self.settings.github_repository,
                "source_commit": "Unknown",
                "collected_at_utc": "Unknown",
                "scope": "No validated evidence snapshot available",
                "sources": [],
                "ci_runs": [],
                "quality": [],
                "releases": [],
                "support_documents": [],
                "open_work": [],
            }
        return copy.deepcopy(self._snapshot)

    def state(self) -> str:
        if self._error and self._snapshot:
            return "stale"
        if self._error:
            return "unknown"
        return "passed"

    def view_for(self, user: User | None) -> dict[str, Any]:
        snapshot = self.snapshot()
        detailed = bool(user and user.roles.intersection({"operator", "admin"}))
        if not detailed:
            # The committed snapshot is already sanitized. This second projection
            # prevents future adapters from accidentally publishing server-only fields.
            snapshot["sources"] = [
                source
                for source in snapshot.get("sources", [])
                if source.get("visibility") == "public"
            ]
            snapshot["ci_runs"] = [
                {
                    key: value
                    for key, value in run.items()
                    if key
                    in {
                        "id",
                        "label",
                        "status",
                        "conclusion",
                        "commit",
                        "url",
                        "scope",
                        "collected_at_utc",
                    }
                }
                for run in snapshot.get("ci_runs", [])
            ]
            snapshot["quality"] = [
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"details", "logs", "private_notes"}
                }
                for item in snapshot.get("quality", [])
            ]
        snapshot["evidence_state"] = self.state()
        snapshot["runtime"] = self.build_info.as_dict()
        snapshot["runtime_commit_matches_snapshot"] = (
            self.build_info.source_commit != "Unknown"
            and self.build_info.source_commit == snapshot.get("source_commit")
        )
        snapshot["runtime_commit"] = self.build_info.source_commit
        snapshot["runtime_environment"] = self.build_info.environment
        return snapshot
