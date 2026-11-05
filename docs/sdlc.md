# SDLC and leadership practices

## Definition of Ready

Acceptance criteria, data/security impact, observability, rollback path, test approach, and migration compatibility are understood; dependencies and owners are identified.

## Definition of Done

Code reviewed, lint/tests pass, security impact assessed, database migration reversible or backward-compatible, docs updated, evidence recorded, and a release/rollback path is rehearsed.

## Branching and review

Use short-lived feature branches, small coherent commits, and PR review. Require checks for lint, unit/integration tests, image build, dependency/security scanning, and migration validation. Production promotion must be manual and environment-protected where the GitHub plan supports it; YAML alone cannot create unavailable protection rules.

## Release checklist

Confirm image digest, migration compatibility, smoke checks, monitoring, change ticket, backup/restore posture, and rollback revision. Promote the same digest between environments; do not rebuild per environment.

## Mentoring exercise

Ask a developer to trace a shipment status change from the Dash callback through InMemoryStore.change_status, identify the role and version checks, add a negative test for a forbidden transition, and explain why the SQL stored procedure must use a row-version predicate.
