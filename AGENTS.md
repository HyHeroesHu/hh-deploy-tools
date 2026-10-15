# HH deployment tools

Read the affected composite action, consuming workflow, Dockerfile, Compose and nginx configuration before changes. Preserve existing inputs/output names, secrets, service scoping and unrelated working-tree changes.

For delivery/image/route diagnosis or explicitly authorized rollout/restoration, use [hh-delivery-operations](tools/agent-skills/hh-delivery-operations/SKILL.md). Its versioned source is synchronized to user discovery through the sibling [skill library](../HyHeroesMods/docs/agent-skills/README.md).

Validate changes locally with isolated script/action fixtures or syntax/source checks. Do not connect to production, execute deployments/database changes, send notifications or start configured services as incidental verification. A named operation/environment already authorized by the user needs no repeated approval.

Update owning operation notes when behavior changes. Do not commit, push or deploy unless requested. Keep source/build/publish evidence separate from the running image, health and end-user acceptance.
