# HyHeroes deployment tools

Reusable GitHub Actions for building and deploying HyHeroes applications. The application repositories call these actions from their `.github/workflows/` folders; those workflows decide **when to run** and supply credentials and application settings.

## What happens

- **Backend build:** [hh-build-dotnet-app](hh-build-dotnet-app/action.yml) checks out the application and `HH.Backend.Common`, builds using the application's Dockerfile, and pushes a `latest` image to Docker Hub.
- **Backend deployment:** [hh-deploy-dotnet-image](hh-deploy-dotnet-image/action.yml) connects over SSH, pulls the Compose service image, and writes `/srv/.env`. If an nginx configuration is supplied, it temporarily disables the matching upstream before recreating that service. It waits for 10 seconds of stable operation, also requiring a healthy Docker healthcheck when present, with a 60-second verification limit. Traffic returns only after verification succeeds. Failed startup leaves the upstream disabled for manual recovery; there is no automatic backend rollback.
- **WebPanel build:** [hh-build-webpanel](hh-build-webpanel/action.yml) builds the frontend image and pushes it with a `<branch>-<timestamp>` tag.
- **WebPanel deployment:** [hh-deploy-webpanel-image](hh-deploy-webpanel-image/action.yml) pulls that image, extracts its static files, and checks for a nonempty `index.html`. It replaces `/var/www/hh.webpanel`, restores the old site if promotion fails, and retains a successful deployment's previous site at `/var/www/hh.webpanel-backup-*`.
- **Redis:** [redis-deploy](redis-deploy/action.yml) uploads its Dockerfile to `/etc/redis/` and attempts to rebuild and replace Redis. This legacy flow still has known build/password-command defects and needs correction before use.

The actions send start, success, and failure notifications to Discord. Backend deployments share a host lock; WebPanel deployments use a separate lock to prevent overlapping site replacements.

WebPanel backup names include the deployment time in Budapest, GitHub run ID, attempt, and a unique suffix, for example: `/var/www/hh.webpanel-backup-2026-09-27_16-30-00-run-123456789-attempt-1-AbCd1234`. They contain the site replaced by that deployment; the exact path is printed in its logs. Backups are not automatically deleted.

## Where to look

| Key point | Location |
| --- | --- |
| Triggers, application names, credentials | Application repository's `.github/workflows/`; action `inputs` sections |
| Host services, images, ports, and mounts | [docker-compose.yml](docker-compose.yml); backend deployment uses the copy in `/srv` |
| Deployment order, startup checks, and recovery | `Deploy Docker image to VPS via SSH` step in each deployment action |
| Domains, proxy upstreams, and static site root | [nginx-configs](nginx-configs); installed configurations live under `/etc/nginx` |
| Failure details and backup paths | GitHub Actions deployment-step logs |
| Isolated deployment checks | [tests/test_deploy_actions.py](tests/test_deploy_actions.py), run with Python 3 and Bash (`DEPLOY_TEST_BASH` can select Bash) |

**Remaining limitation:** WebPanel's existing image-cleanup command can target unrelated Docker images. Backend images still use `latest`. The recent safety changes did not resolve those separate audit findings.
