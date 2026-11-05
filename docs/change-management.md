# Release and change-management checklist

1. Link the change to a requirement or issue and review data/security impact.
2. Run lint, unit tests, browser smoke, SQL integration when configured, and both image builds.
3. Review migration compatibility and backup/restore posture.
4. Promote the same immutable image digest between environments; do not rebuild for production.
5. Apply migrations as a separate controlled job, observe `/readyz`, logs, and revision health.
6. For rollback, route traffic to the prior Container Apps revision/image digest, then address backward-compatible database changes.
7. Record evidence, approver, release version, migration version, and follow-up limitations.
