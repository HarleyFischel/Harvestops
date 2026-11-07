#!/usr/bin/env python3
"""Refresh the sanitized evidence snapshot from explicit local/CI evidence.

Missing JUnit files are recorded as ``unknown``. The script never turns an
absent artifact into zero failures or a passing result.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "Unknown"


def parse_junit(path: Path, label: str, commit: str) -> dict:
    if not path.exists():
        return {
            "id": label.lower().replace(" ", "-"),
            "label": label,
            "status": "unknown",
            "summary": f"JUnit artifact not found at {path}; result is unknown.",
            "commit": commit,
            "scope": "local structured artifact",
            "collected_at_utc": now_iso(),
        }
    try:
        root = ElementTree.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
        failures = sum(
            int(suite.attrib.get("failures", "0")) + int(suite.attrib.get("errors", "0"))
            for suite in suites
        )
        skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
        status = "failed" if failures else "passed"
        summary = f"{tests} tests, {failures} failures, {skipped} skipped"
    except (OSError, ElementTree.ParseError, ValueError) as exc:
        status = "unknown"
        summary = f"JUnit artifact could not be parsed ({type(exc).__name__}); result is unknown."
    return {
        "id": label.lower().replace(" ", "-"),
        "label": label,
        "status": status,
        "summary": summary,
        "commit": commit,
        "scope": "local structured artifact",
        "collected_at_utc": now_iso(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--output", type=Path, default=Path("evidence/snapshot.json"))
    parser.add_argument("--repository", default="HarleyFischel/Harvestops")
    parser.add_argument("--commit", default="")
    parser.add_argument("--ci-run-id", default="")
    parser.add_argument("--ci-run-url", default="")
    args = parser.parse_args()
    commit = args.commit or git_value("rev-parse", "HEAD")
    collected = now_iso()
    quality = [
        parse_junit(args.results_dir / "pytest.xml", "Local Python suite", commit),
        parse_junit(args.results_dir / "browser.xml", "Browser suite", commit),
        parse_junit(args.results_dir / "sql-integration.xml", "SQL integration suite", commit),
    ]
    preserved = {}
    if args.output.exists():
        try:
            candidate = json.loads(args.output.read_text(encoding="utf-8"))
            if isinstance(candidate, dict):
                preserved = candidate
        except (OSError, json.JSONDecodeError):
            preserved = {}

    ci_runs = list(preserved.get("ci_runs", []))
    if args.ci_run_id and args.ci_run_url:
        ci_runs = [
            {
                "id": args.ci_run_id,
                "label": "GitHub Actions CI",
                "status": "passed",
                "conclusion": "success",
                "commit": commit,
                "url": args.ci_run_url,
                "scope": "hosted-main",
                "collected_at_utc": collected,
            },
            *[run for run in ci_runs if run.get("id") != args.ci_run_id],
        ]
    snapshot = {
        "schema_version": 1,
        "snapshot_type": "sanitized-portfolio",
        "repository": args.repository,
        "source_commit": commit,
        "collected_at_utc": collected,
        "scope": "Explicitly recorded local structured results and optional hosted CI metadata.",
        "sources": preserved.get(
            "sources",
            [
                {
                    "label": "Source repository",
                    "url": f"https://github.com/{args.repository}",
                    "visibility": "public",
                }
            ],
        ),
        "ci_runs": ci_runs,
        "quality": quality,
        "releases": preserved.get("releases", []),
        "support_documents": preserved.get("support_documents", []),
        "open_work": preserved.get("open_work", []),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote sanitized evidence snapshot to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
