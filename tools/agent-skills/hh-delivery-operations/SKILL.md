---
name: hh-delivery-operations
description: Diagnose or change HH CI/CD, Docker/Compose image delivery, deployment scripts, reverse-proxy integration or explicitly authorized rollout/restoration; investigate deployed route/image mismatches.
---

# Delivery and production diagnosis

Resolve hh-deploy-tools and the affected consuming repository from the workspace. Repository-prefixed paths are relative to the checkout parent. Read their AGENTS.md and current action/workflow/Dockerfile/Compose source before acting; earlier hardening may have been rolled back.

1. Establish application, target environment, requested operation and existing authorization. Read-only analysis does not authorize SSH, deployment, database migration or bot execution. For production inspection prefer the user's redacted offline evidence; do not invent a host.
2. Trace build -> publish -> digest/output -> Compose service/image -> started container -> health/route. A 404 suggests route/artifact mismatch; compare controller route, CI publish result and deployed image age/ID before changing credentials or persistence.
3. Inspect actual workflow_dispatch inputs, commit gates and launcher support before proposing terminal triggers. Never assume a previously planned launcher exists.
4. For pipeline changes validate input/output names, digest propagation, shell quoting, service scoping, drain/reload/failure behavior and temporary override cleanup. Keep credentials/logs redacted; do not dump environment values.
5. Inspect current nginx configuration and integration context before editing; use available nginx/observability skill guidance when appropriate. Do not silently migrate bare-metal nginx into containers or vice versa.
6. For an explicitly requested restore compare exact named paths against the selected baseline, preserving SQL/unrelated work. Avoid history reset/force-push. For rollout verify resolved service and immutable artifact, then execute only authorized steps.
7. Validate scripts/actions with isolated fixtures or syntax checks. Running configured infrastructure is not a syntax check. Report source checks, publish/upload, loaded image/health and end-user evidence separately.
8. Update affected repository operation notes. Hytale plugin publication follows its own module shadowJarDeploy workflow, not a guessed backend pipeline.


Repository names in code paths identify checkouts, not folders inside an installed skill. Resolve them from the current workspace and its siblings; if a required checkout is unavailable, report that limitation and continue independent in-scope work. Never guess a production target.
