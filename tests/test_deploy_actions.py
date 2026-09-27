"""Run with Python 3 and Bash; deployment commands are isolated shell stubs."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get("DEPLOY_TEST_BASH") or shutil.which("bash")


def remote_script(action):
    text = (ROOT / action / "action.yml").read_text(encoding="utf-8")
    match = re.search(r"^        script: \|\n((?:          [^\n]*\n|\n)+)", text, re.M)
    if not match:
        raise AssertionError("Remote script not found")
    return "\n".join(line[10:] for line in match[1].splitlines()).strip() + "\n"


def backend_build_script():
    text = (ROOT / "hh-build-dotnet-app" / "action.yml").read_text(encoding="utf-8")
    match = re.search(r"    - name: Build and Push Docker Image\n.*?      run: \|\n((?:        [^\n]*\n|\n)+)", text, re.S)
    if not match:
        raise AssertionError("Backend build script not found")
    return "\n".join(line[8:] for line in match[1].splitlines()).strip() + "\n"


class BackendBuildTest(unittest.TestCase):
    def run_fixture(self, scenario="success"):
        with tempfile.TemporaryDirectory(prefix="hh-build-test-") as directory:
            fixture = Path(directory)
            script = r'''
git() {
  if [[ "$2" == HH.Backend.Common ]]; then printf 'common-commit\n';
  else printf 'app-commit\n'; fi
}
docker() {
  printf '%s\n' "$*" >> "$HH_TEST_FIXTURE/commands"
  case "$1" in
    push) [[ "$HH_TEST_SCENARIO" != push-failure ]] || return 7 ;;
    image)
      printf 'fixture/other-image@sha256:%064d\n' 0
      if [[ "$HH_TEST_SCENARIO" != missing-digest ]]; then
        printf 'fixture/image@sha256:%064d\n' 0
      fi ;;
  esac
}
'''
            script += backend_build_script()
            script_path = fixture / "fixture.sh"
            script_path.write_text(script, encoding="utf-8", newline="\n")
            environment = os.environ.copy()
            environment.update({
                "HH_TEST_FIXTURE": fixture.as_posix(),
                "HH_TEST_SCENARIO": scenario,
                "HH_IMAGE_REPOSITORY": "fixture/image",
                "HH_APP_DIRECTORY": "HH.Backend.BackgroundOperator",
                "TIMESTAMP": "123",
                "GITHUB_OUTPUT": (fixture / "outputs").as_posix(),
            })
            result = subprocess.run([BASH, str(script_path)], env=environment, capture_output=True, text=True, timeout=15)
            return {
                "status": result.returncode,
                "output": result.stdout + result.stderr,
                "commands": (fixture / "commands").read_text(),
                "outputs": (fixture / "outputs").read_text() if (fixture / "outputs").exists() else "",
            }

    def test_build_publishes_digest_and_source_revisions(self):
        result = self.run_fixture()
        self.assertEqual(result["status"], 0, result["output"])
        self.assertEqual(result["outputs"], "image-reference=fixture/image@sha256:" + "0" * 64 + "\n")
        self.assertIn("org.opencontainers.image.revision=app-commit", result["commands"])
        self.assertIn("hu.hyheroes.common.revision=common-commit", result["commands"])
        self.assertIn("-t fixture/image:123 -t fixture/image:latest", result["commands"])
        self.assertIn("push fixture/image:123\npush fixture/image:latest", result["commands"])

    def test_failed_push_cannot_publish_digest(self):
        result = self.run_fixture("push-failure")
        self.assertEqual(result["status"], 7, result["output"])
        self.assertEqual(result["outputs"], "")
        self.assertNotIn("image inspect", result["commands"])

    def test_missing_repository_digest_cannot_report_success(self):
        result = self.run_fixture("missing-digest")
        self.assertNotEqual(result["status"], 0)
        self.assertEqual(result["outputs"], "")


STUBS = r'''
log() { printf '%s\n' "$*" >> "$fixture/commands"; }
flock() { log "lock $*"; }
sleep() { SECONDS=$((SECONDS + 1)); }
sysctl() { log "sysctl $*"; }
sudo() {
  if [[ "$1" != nginx ]]; then "$@"; return; fi
  log "nginx ${*:2}"
  local count=0
  [[ ! -f "$fixture/nginx-count" ]] || count=$(cat "$fixture/nginx-count")
  count=$((count + 1))
  printf '%s' "$count" > "$fixture/nginx-count"
  if [[ "$scenario" == drain-validation && $count -eq 1 ]] ||
     [[ "$scenario" == drain-reload && $count -eq 2 ]] ||
     [[ "$scenario" == restore-validation && $count -eq 3 ]] ||
     [[ "$scenario" == restore-reload && $count -eq 4 ]]; then return 7; fi
  return 0
}
docker() {
  log "docker $*"
  if [[ "$1" == compose ]]; then
    shift
    while [[ "${1:-}" == -f ]]; do
      if [[ "$2" == *'.hh-image-override.'* ]]; then
        log "image override: $(cat "$2")"
      fi
      shift 2
    done
    set -- compose "$@"
  fi
  case "$1 $2" in
    'login '*) cat > /dev/null ;;
    'compose pull') [[ "$scenario" != pull-failure ]] || return 7 ;;
    'compose up') [[ "$scenario" != recreate-failure ]] || return 7 ;;
    'compose ps') printf 'fixture-container\n' ;;
    'compose config')
      if [[ "$scenario" == missing-service ]]; then printf 'other-service\n';
      else printf 'fixture-service\n'; fi ;;
    'image inspect')
      if [[ "$4" == '{{.Id}}' ]]; then printf 'sha256:built-image\n';
      else printf 'Application revision: app-commit; Common revision: common-commit\n'; fi ;;
    'inspect --format')
      if [[ "$3" == '{{.Image}}' ]]; then
        if [[ "$scenario" == image-mismatch ]]; then printf 'sha256:old-image\n';
        else printf 'sha256:built-image\n'; fi
        return 0
      fi
      local count=0
      [[ ! -f "$fixture/inspect-count" ]] || count=$(cat "$fixture/inspect-count")
      count=$((count + 1))
      printf '%s' "$count" > "$fixture/inspect-count"
      case "$scenario" in
        exited) printf 'exited 0 none false\n' ;;
        dead) printf 'dead 0 none false\n' ;;
        restart) printf 'running 1 none true\n' ;;
        unhealthy) printf 'running 0 unhealthy true\n' ;;
        timeout) printf 'running 0 starting true\n' ;;
        delayed-health)
          if (( count < 15 )); then printf 'running 0 starting true\n';
          else printf 'running 0 healthy true\n'; fi ;;
        *) printf 'running 0 none true\n' ;;
      esac ;;
    'image prune') [[ "$scenario" != prune-failure ]] || return 7 ;;
    'images --format') printf 'fixture/image:old\n' ;;
    'pull '*) [[ "$scenario" != pull-failure ]] || return 7 ;;
    'container inspect') return 1 ;;
    'create --name') printf 'temporary-container\n' ;;
    'cp '*)
      [[ "$scenario" != copy-failure && "$scenario" != staging-cleanup-failure ]] || return 7
      if [[ "$scenario" != missing-index ]]; then
        printf 'new site' > "${@: -1}/index.html"
      fi ;;
    'rm '*) [[ "$scenario" != cleanup-failure && "$scenario" != copy-cleanup-failure ]] || return 8 ;;
  esac
  if [[ "$1" == cp && "$scenario" == copy-cleanup-failure ]]; then return 7; fi
  return 0
}
mv() {
  log "mv $*"
  if [[ "$scenario" == promotion-failure && "$*" == *'.hh.webpanel-stage.'* ]]; then return 7; fi
  command mv "$@"
}
rm() {
  log "rm $*"
  if [[ "$scenario" == staging-cleanup-failure && "$*" == *'.hh.webpanel-stage.'* ]]; then return 8; fi
  command rm "$@"
}
'''


class DeployActionsTest(unittest.TestCase):
    def run_fixture(self, action, scenario="success", config=None, existing=True, nginx=True, image_reference=""):
        with tempfile.TemporaryDirectory(prefix="hh-deploy-test-") as directory:
            fixture = Path(directory)
            host = fixture / "host"
            host.mkdir()
            (host / "docker-compose.yml").write_text("services:\n  fixture-service:\n    image: fixture/image:latest\n")
            production = host / "hh.webpanel"
            if existing:
                production.mkdir()
                (production / "index.html").write_text("old site")
            config_path = host / "nginx.conf"
            original = config or "upstream api {\n  server 127.0.0.1:5000; # target\n  server 127.0.0.1:5001;\n}\n"
            config_path.write_text(original)
            script = remote_script(action)
            values = {
                "inputs.docker-container-name": "fixture-service",
                "inputs.nginx-site-config-path": config_path.as_posix() if nginx else "",
                "inputs.docker-container-port": "5000",
                "inputs.dockerhub-pat": "test-token",
                "inputs.dockerhub-user": "test-user",
                "inputs.secret-env-base64": "VEVTVF9FTlY9MQo=",
                "inputs.dockerhub-namespace": "fixture",
                "inputs.dockerhub-image-name": "image",
                "inputs.image-reference": image_reference,
                "inputs.docker-image-name": "",  # Finding 1 deliberately remains unchanged.
                "inputs.version-timestamp": "123",
                "github.ref_name": "main",
                "github.run_id": "123456789",
                "github.run_attempt": "2",
            }
            for expression, value in values.items():
                script = script.replace("${{ " + expression + " }}", value)
            script = script.replace("/var/www", host.as_posix()).replace("cd /srv", f"cd '{host.as_posix()}'")
            script = script.replace("nginx_work=$(mktemp -d)", 'nginx_work=$(mktemp -d "$fixture/nginx.XXXXXXXX")')
            # Execute the heredoc body with functions instead of real host commands.
            body = script.split("bash -se <<'HH_DEPLOY_SCRIPT'\n", 1)[1].rsplit("HH_DEPLOY_SCRIPT", 1)[0]
            # Unsetting removes Bash's wall-clock behavior for a deterministic test clock.
            body = f"fixture='{fixture.as_posix()}'\nscenario='{scenario}'\nunset SECONDS\nSECONDS=0\n" + STUBS + body
            script_path = fixture / "fixture.sh"
            script_path.write_text(body, encoding="utf-8", newline="\n")
            result = subprocess.run([BASH, str(script_path)], capture_output=True, text=True, timeout=15)
            commands = (fixture / "commands").read_text() if (fixture / "commands").exists() else ""
            backups = list(host.glob("hh.webpanel-backup-*"))
            return {
                "status": result.returncode,
                "output": result.stdout + result.stderr,
                "commands": commands,
                "config": config_path.read_text(),
                "original": original,
                "production": (production / "index.html").read_text() if (production / "index.html").exists() else None,
                "backups": [(path / "index.html").read_text() for path in backups],
                "backup_names": [path.name for path in backups],
                "staging": list(host.glob(".hh.webpanel-stage.*")),
                "inspect_count": int((fixture / "inspect-count").read_text()) if (fixture / "inspect-count").exists() else 0,
                "image_overrides": list(host.glob(".hh-image-override.*")),
            }

    def test_shell_syntax(self):
        for action in ("hh-deploy-dotnet-image", "hh-deploy-webpanel-image"):
            with self.subTest(action=action):
                result = subprocess.run([BASH, "-n"], input=remote_script(action), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_backend_pull_failure_preserves_service_and_nginx(self):
        result = self.run_fixture("hh-deploy-dotnet-image", "pull-failure")
        self.assertEqual(result["status"], 7, result["output"])
        self.assertEqual(result["config"], result["original"])
        self.assertNotIn("compose up", result["commands"])
        self.assertNotIn("nginx", result["commands"])

    def test_backend_drain_failures_restore_original_before_shutdown(self):
        for scenario in ("drain-validation", "drain-reload"):
            with self.subTest(scenario=scenario):
                result = self.run_fixture("hh-deploy-dotnet-image", scenario)
                self.assertEqual(result["status"], 7, result["output"])
                self.assertEqual(result["config"], result["original"])
                self.assertNotIn("compose up", result["commands"])

    def test_backend_requires_one_active_match(self):
        for config in ("server 127.0.0.1:5001;\n", "server 127.0.0.1:5000;\n" * 2, "server 127.0.0.1:5000 down;\n"):
            with self.subTest(config=config):
                result = self.run_fixture("hh-deploy-dotnet-image", config=config)
                self.assertNotEqual(result["status"], 0)
                self.assertEqual(result["config"], config)
                self.assertNotIn("compose up", result["commands"])

    def test_backend_failure_keeps_only_target_drained(self):
        for scenario in ("recreate-failure", "exited", "dead", "restart", "unhealthy", "timeout", "restore-validation", "restore-reload"):
            with self.subTest(scenario=scenario):
                result = self.run_fixture("hh-deploy-dotnet-image", scenario)
                self.assertNotEqual(result["status"], 0, result["output"])
                self.assertIn("server 127.0.0.1:5000 down; # target", result["config"])
                self.assertIn("server 127.0.0.1:5001;", result["config"])
                self.assertIn("Recover fixture-service manually", result["output"])

    def test_backend_success_restores_exact_config(self):
        configs = (
            "server 127.0.0.1:5000; # plain\nserver 127.0.0.1:5001;\n",
            "\tserver\t127.0.0.1:5000  max_conns=2000 weight=2 ; # parameters\nserver 127.0.0.1:5001;\n",
        )
        for config in configs:
            with self.subTest(config=config):
                result = self.run_fixture("hh-deploy-dotnet-image", config=config)
                self.assertEqual(result["status"], 0, result["output"])
                self.assertEqual(result["config"], config)
                self.assertGreaterEqual(result["inspect_count"], 11)
                self.assertIn("compose up -d --no-deps --force-recreate fixture-service", result["commands"])
                self.assertLess(result["commands"].index("compose pull"), result["commands"].index("nginx -t"))
                self.assertLess(result["commands"].index("lock"), result["commands"].index("compose pull"))

    def test_backend_draining_preserves_parameters_and_comments(self):
        config = "\tserver\t127.0.0.1:5000 max_conns=2000 weight=2; # target\nserver 127.0.0.1:5001;\n"
        result = self.run_fixture("hh-deploy-dotnet-image", "exited", config=config)
        self.assertNotEqual(result["status"], 0)
        self.assertEqual(result["config"], config.replace("weight=2;", "weight=2 down;"))

    def test_backend_delayed_health_and_optional_prune(self):
        for scenario in ("delayed-health", "prune-failure"):
            with self.subTest(scenario=scenario):
                result = self.run_fixture("hh-deploy-dotnet-image", scenario)
                self.assertEqual(result["status"], 0, result["output"])
                self.assertEqual(result["config"], result["original"])
                if scenario == "delayed-health":
                    self.assertGreaterEqual(result["inspect_count"], 15)
                else:
                    self.assertIn("Warning: image pruning failed", result["output"])

    def test_backend_without_nginx(self):
        result = self.run_fixture("hh-deploy-dotnet-image", nginx=False)
        self.assertEqual(result["status"], 0, result["output"])
        self.assertNotIn("nginx", result["commands"])

    def test_backend_deploys_and_verifies_built_digest(self):
        image = "fixture/image@sha256:" + "a" * 64
        result = self.run_fixture("hh-deploy-dotnet-image", image_reference=image)
        self.assertEqual(result["status"], 0, result["output"])
        self.assertIn('image: "' + image + '"', result["commands"])
        self.assertIn("image inspect --format {{.Id}} " + image, result["commands"])
        self.assertIn("inspect --format {{.Image}} fixture-container", result["commands"])
        self.assertIn("Application revision: app-commit", result["output"])
        self.assertIn("Common revision: common-commit", result["output"])
        self.assertEqual(result["image_overrides"], [])

    def test_backend_wrong_image_cannot_report_success(self):
        image = "fixture/image@sha256:" + "a" * 64
        result = self.run_fixture("hh-deploy-dotnet-image", "image-mismatch", image_reference=image)
        self.assertNotEqual(result["status"], 0)
        self.assertIn("Container image mismatch", result["output"])
        self.assertIn("server 127.0.0.1:5000 down;", result["config"])
        self.assertEqual(result["image_overrides"], [])

    def test_backend_rejects_wrong_repository_before_pull(self):
        image = "fixture/wrong-image@sha256:" + "a" * 64
        result = self.run_fixture("hh-deploy-dotnet-image", image_reference=image)
        self.assertNotEqual(result["status"], 0)
        self.assertIn("Built image repository does not match", result["output"])
        self.assertNotIn("compose", result["commands"])
        self.assertEqual(result["config"], result["original"])

    def test_backend_digest_pull_failure_cleans_override(self):
        image = "fixture/image@sha256:" + "a" * 64
        result = self.run_fixture("hh-deploy-dotnet-image", "pull-failure", image_reference=image)
        self.assertEqual(result["status"], 7, result["output"])
        self.assertNotIn(" up ", result["commands"])
        self.assertEqual(result["config"], result["original"])
        self.assertEqual(result["image_overrides"], [])

    def test_backend_digest_requires_existing_compose_service(self):
        image = "fixture/image@sha256:" + "a" * 64
        result = self.run_fixture("hh-deploy-dotnet-image", "missing-service", image_reference=image)
        self.assertNotEqual(result["status"], 0)
        self.assertIn("absent from the server Compose configuration", result["output"])
        self.assertNotIn(" pull ", result["commands"])
        self.assertNotIn(" up ", result["commands"])
        self.assertEqual(result["config"], result["original"])
        self.assertEqual(result["image_overrides"], [])

    def test_webpanel_failures_preserve_live_site(self):
        for scenario in ("pull-failure", "copy-failure", "missing-index", "copy-cleanup-failure"):
            with self.subTest(scenario=scenario):
                result = self.run_fixture("hh-deploy-webpanel-image", scenario)
                self.assertNotEqual(result["status"], 0, result["output"])
                self.assertEqual(result["production"], "old site")
                self.assertEqual(result["backups"], [])
                self.assertEqual(result["staging"], [])
                if scenario == "copy-cleanup-failure":
                    self.assertEqual(result["status"], 7, result["output"])

    def test_webpanel_failed_promotion_rolls_back(self):
        result = self.run_fixture("hh-deploy-webpanel-image", "promotion-failure")
        self.assertEqual(result["status"], 7, result["output"])
        self.assertEqual(result["production"], "old site")
        self.assertEqual(result["backups"], [])

    def test_webpanel_success_retains_backup_and_handles_first_deploy(self):
        for existing in (True, False):
            with self.subTest(existing=existing):
                result = self.run_fixture("hh-deploy-webpanel-image", existing=existing)
                self.assertEqual(result["status"], 0, result["output"])
                self.assertEqual(result["production"], "new site")
                self.assertEqual(result["backups"], ["old site"] if existing else [])
                if existing:
                    self.assertRegex(result["backup_names"][0], r"^hh\.webpanel-backup-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-run-123456789-attempt-2-[A-Za-z0-9]+$")
                self.assertEqual(result["staging"], [])

    def test_webpanel_cleanup_failure_preserves_success(self):
        result = self.run_fixture("hh-deploy-webpanel-image", "cleanup-failure")
        self.assertEqual(result["status"], 0, result["output"])
        self.assertEqual(result["production"], "new site")
        self.assertIn("Warning: temporary container cleanup failed", result["output"])

    def test_webpanel_staging_cleanup_failure_preserves_failure(self):
        result = self.run_fixture("hh-deploy-webpanel-image", "staging-cleanup-failure")
        self.assertEqual(result["status"], 7, result["output"])
        self.assertEqual(result["production"], "old site")
        self.assertEqual(len(result["staging"]), 1)
        self.assertIn("Warning: staging cleanup failed", result["output"])


if __name__ == "__main__":
    unittest.main()
