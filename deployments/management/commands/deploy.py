"""Auto-deploy pipeline for the Caluu+ backend.

Polls origin/<branch>, fast-forwards the working tree, syncs dependencies,
applies migrations, restarts the gunicorn systemd service and verifies
health. Any failure triggers an automatic rollback:

  * git reset --hard <previous commit>
  * restore the SQLite snapshot taken before migrations were applied
  * restart the service

Every run is recorded in the ``deployments.Deployment`` table (when the
database survives the run). A durable plain-text audit log, configured via
``DEPLOY_LOG_FILE`` (default ``/var/log/caluu-deploy.log``), is always
written so even rolled-back runs remain traceable.

Intended to be driven by a systemd timer (every minute) or run manually:
  venv/bin/python manage.py deploy --branch main --trigger timer
"""

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from backups.utils import _get_db_path, perform_backup
from deployments.models import Deployment, DeploymentStatus


def _git(cwd, *args, log=None):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if log is not None:
        for line in proc.stdout.strip().splitlines():
            log(line)
        for line in proc.stderr.strip().splitlines():
            log(line)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed ({proc.returncode})")
    return proc.stdout.strip()


def _pip(cwd, *args, log=None):
    proc = subprocess.run(
        [sys.executable, "-m", "pip", *args], cwd=cwd, capture_output=True, text=True
    )
    if log is not None:
        for line in (proc.stdout + proc.stderr).strip().splitlines():
            log(line)
    if proc.returncode != 0:
        raise RuntimeError(f"pip {' '.join(args)} failed ({proc.returncode})")
    return (proc.stdout + proc.stderr).strip()


def _manage(base_dir, *args, log=None, settings_module=None):
    env = dict(os.environ)
    if settings_module:
        env["DJANGO_SETTINGS_MODULE"] = settings_module
    proc = subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=base_dir, env=env, capture_output=True, text=True,
    )
    if log is not None:
        for line in (proc.stdout + proc.stderr).strip().splitlines():
            log(line)
    if proc.returncode != 0:
        raise RuntimeError(f"manage.py {' '.join(args)} failed ({proc.returncode})")
    return (proc.stdout + proc.stderr).strip()


def _restart(service, log=None):
    try:
        proc = subprocess.run(
            ["systemctl", "restart", service], capture_output=True, text=True
        )
    except FileNotFoundError:
        if log is not None:
            log("systemctl not found; skipping service restart (local dev)")
        return
    if log is not None:
        for line in (proc.stdout + proc.stderr).strip().splitlines():
            log(line)
    if proc.returncode != 0:
        raise RuntimeError(f"systemctl restart {service} failed ({proc.returncode})")


def _wait_healthy(url, timeout, log=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                if resp.status < 500:
                    if log is not None:
                        log(f"health OK ({resp.status})")
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(3)
    return False


class Command(BaseCommand):
    help = "Pull origin/<branch> and deploy the backend with automatic rollback."

    def add_arguments(self, parser):
        parser.add_argument("--branch", default="main")
        parser.add_argument(
            "--trigger", default="timer", choices=["timer", "manual"],
            help="Where this run was initiated from (for the audit record).",
        )
        parser.add_argument("--health-url", default="")
        parser.add_argument("--health-timeout", type=int, default=120)
        parser.add_argument(
            "--skip-deps", action="store_true", help="Do not pip install -r requirements.txt"
        )
        parser.add_argument(
            "--skip-restart", action="store_true",
            help="Do not restart the service or run the health check (CI)",
        )
        parser.add_argument(
            "--force", action="store_true", help="Deploy even when already up to date"
        )

    def handle(self, *args, **options):  # noqa: C901 - linear pipeline is fine
        base_dir = settings.BASE_DIR
        branch = options["branch"]
        service = os.getenv("DEPLOY_SERVICE_NAME", "caluu-backendii.service")
        health_url = options["health_url"] or os.getenv(
            "DEPLOY_HEALTH_URL", "http://127.0.0.1:8006/api/university-calendar/"
        )
        # Settings module the gunicorn service actually boots with. All
        # deploy-time manage.py calls must run against it so migrations and
        # system checks match the app that will serve traffic (drift between
        # settings.py and production.py used to break requests at import time).
        deploy_settings = os.getenv(
            "DEPLOY_SETTINGS_MODULE", "academic_backend.production"
        )

        log_lines = []

        def log(line=""):
            log_lines.append(str(line))
            self.stdout.write(str(line))

        audit_path = Path(os.getenv("DEPLOY_LOG_FILE", "/var/log/caluu-deploy.log"))

        def durable(line):
            try:
                audit_path.parent.mkdir(parents=True, exist_ok=True)
                with audit_path.open("a", encoding="utf-8") as fh:
                    fh.write(f"{timezone.now():%Y-%m-%d %H:%M:%S} {line}\n")
            except OSError:
                pass

        # First run: the deployments table may not exist yet; ensure the
        # migration for this very app is applied before recording anything.
        try:
            tables = set(connection.introspection.table_names())
        except Exception:  # noqa: BLE001 - connection issues surface below
            tables = set()
        if "deployments_deployment" not in tables:
            log("Bootstrapping: applying pending deployments migrations...")
            try:
                _manage(base_dir, "migrate", "--no-input", log=log, settings_module=deploy_settings)
            except RuntimeError as exc:
                raise CommandError(f"initial migration failed: {exc}")

        try:
            _git(base_dir, "fetch", "origin", branch, log=log)
            before = _git(base_dir, "rev-parse", "HEAD")
            target = _git(base_dir, "rev-parse", f"origin/{branch}")
        except RuntimeError as exc:
            raise CommandError(f"git fetch/rev-parse failed: {exc}")

        if before == target and not options["force"]:
            log(f"Already up to date at {before[:12]} ({branch}); nothing to deploy")
            return

        record = Deployment.objects.create(
            branch=branch,
            commit_before=before,
            status=DeploymentStatus.RUNNING,
            trigger=options["trigger"],
        )
        durable(f"[{record.pk}] START deploy {branch} {before[:12]} -> {target[:12]}")

        start = time.time()
        db_path = _get_db_path()

        def finish(status, error=""):
            record.status = status
            record.log = "\n".join(log_lines)
            record.error_summary = error
            record.finished_at = timezone.now()
            record.duration_seconds = round(time.time() - start, 2)
            try:
                record.save()
            except Exception:  # noqa: BLE001
                # DB was rolled back to a snapshot without this table; the
                # durable plain-text log is the audit trail in that case.
                pass
            durable(f"[{record.pk}] DONE {status} in {record.duration_seconds:.1f}s {error}")

        try:
            backup_rec, backup_err = perform_backup(notify=False)
            if not backup_rec:
                raise RuntimeError(f"pre-deploy DB snapshot failed: {backup_err}")
            record.db_backup_path = backup_rec.file_path
            record.save(update_fields=["db_backup_path"])
            log(f"DB snapshot: {backup_rec.file_path}")

            _git(base_dir, "merge", "--ff-only", f"origin/{branch}", log=log)
            after = _git(base_dir, "rev-parse", "HEAD")
            record.commit_after = after
            record.save(update_fields=["commit_after"])
            log(f"Fast-forwarded to {after[:12]}")

            if not options["skip_deps"]:
                log("Syncing dependencies...")
                _pip(base_dir, "install", "-r", "requirements.txt", log=log)

            log("Applying migrations...")
            _manage(
                base_dir, "migrate", "--no-input", log=log,
                settings_module=deploy_settings,
            )

            log("Collecting static files...")
            _manage(
                base_dir, "collectstatic", "--noinput", log=log,
                settings_module=deploy_settings,
            )

            if not options["skip_restart"]:
                log(f"Running system check ({deploy_settings})...")
                _manage(base_dir, "check", log=log, settings_module=deploy_settings)

                log(f"Restarting {service}...")
                _restart(service, log=log)
                log(f"Waiting for health at {health_url}...")
                if not _wait_healthy(health_url, options["health_timeout"], log=log):
                    raise RuntimeError("health check did not pass after restart")

            # Optional media-serving probe (DEPLOY_MEDIA_URL). Warns, does not
            # roll back: a broken /media/ is an nginx/filesystem concern that
            # code rollback cannot repair, but the warning is surfaced in the
            # deployment log + admin so it is caught on every deploy.
            media_url = os.getenv("DEPLOY_MEDIA_URL", "")
            if media_url and not options["skip_restart"]:
                try:
                    with urllib.request.urlopen(media_url, timeout=15) as resp:
                        media_ok = resp.status == 200
                except (urllib.error.URLError, OSError):
                    media_ok = False
                if media_ok:
                    log("Media probe OK (200)")
                else:
                    log("WARNING: media probe did not reach 200 - check nginx /media/ and the media directory")

            finish(DeploymentStatus.SUCCESS)
        except Exception as exc:  # noqa: BLE001
            log(f"ERROR: {exc}")
            durable(f"[{record.pk}] ERROR {exc}")

            try:
                _git(base_dir, "reset", "--hard", before, log=log)
                if record.db_backup_path:
                    if Path(record.db_backup_path).exists():
                        shutil.copy2(record.db_backup_path, db_path)
                        log(f"Restored DB from {record.db_backup_path}")
                    else:
                        log("Backup snapshot missing; DB not restored")
                if not options["skip_restart"]:
                    _restart(service, log=log)
            except Exception as rb:  # noqa: BLE001
                log(f"ROLLBACK PROBLEMS: {rb}")
                durable(f"[{record.pk}] ROLLBACK PROBLEMS {rb}")

            finish(DeploymentStatus.ROLLED_BACK, error=str(exc))