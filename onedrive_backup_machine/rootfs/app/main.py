"""OneDrive Backup Machine API and scheduler."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web
from croniter import croniter

from one_drive import OneDriveClient
from token_cache import load_json, save_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_LOGGER = logging.getLogger("onedrive_backup_machine")

DATA_DIR = Path(os.environ.get("ODBM_DATA_DIR", "/data"))
BACKUP_ROOT = Path(os.environ.get("ODBM_BACKUP_ROOT", "/share/onedrive_backup_machine"))
LISTEN_PORT = int(os.environ.get("ODBM_LISTEN_PORT", "8080"))
CLIENT_ID = os.environ.get("ODBM_CLIENT_ID", "").strip()

TASKS_FILE = DATA_DIR / "tasks.json"
JOBS_FILE = DATA_DIR / "jobs.json"
STATE_FILE = DATA_DIR / "state.json"
TOKEN_CACHE_FILE = DATA_DIR / "msal_token_cache.bin"

MAX_JOBS = 50


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_tasks() -> list[dict[str, Any]]:
    return [
        {
            "id": "default",
            "name": "Default OneDrive backup",
            "remote_path": "",
            "mode": "incremental",
            "schedule": "0 3 * * *",
            "enabled": True,
        }
    ]


class AppState:
    def __init__(self) -> None:
        self.client = OneDriveClient(CLIENT_ID, TOKEN_CACHE_FILE)
        self.tasks: list[dict[str, Any]] = load_json(TASKS_FILE, default_tasks())
        self.jobs: list[dict[str, Any]] = load_json(JOBS_FILE, [])
        self.state: dict[str, Any] = load_json(STATE_FILE, {"running": False, "current_job_id": None})
        self._lock = asyncio.Lock()
        self._runner_task: asyncio.Task | None = None

    def persist(self) -> None:
        save_json(TASKS_FILE, self.tasks)
        save_json(JOBS_FILE, self.jobs[:MAX_JOBS])
        save_json(STATE_FILE, self.state)

    def status_payload(self) -> dict[str, Any]:
        latest = self.jobs[0] if self.jobs else None
        return {
            "authenticated": self.client.is_authenticated() if self.client.configured else False,
            "client_id_configured": self.client.configured,
            "running": bool(self.state.get("running")),
            "current_job_id": self.state.get("current_job_id"),
            "backup_root": str(BACKUP_ROOT),
            "task_count": len(self.tasks),
            "latest_job_status": (latest or {}).get("status"),
            "api": "onedrive-backup-machine",
            "version": "1.0.0",
        }

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        for task in self.tasks:
            if task.get("id") == task_id:
                return task
        return None

    async def enqueue_run(self, task_id: str | None = None) -> dict[str, Any]:
        task = self.get_task(task_id) if task_id else (self.tasks[0] if self.tasks else None)
        if not task:
            raise web.HTTPBadRequest(text='{"error":"No task available"}')
        if self.state.get("running"):
            raise web.HTTPConflict(text='{"error":"A backup job is already running"}')

        job = {
            "id": str(uuid.uuid4()),
            "task_id": task["id"],
            "task_name": task.get("name") or task["id"],
            "mode": task.get("mode") or "incremental",
            "status": "queued",
            "started_at": None,
            "completed_at": None,
            "summary": {"downloaded": 0, "skipped": 0, "errors": 0, "error_messages": []},
        }
        self.jobs.insert(0, job)
        self.jobs = self.jobs[:MAX_JOBS]
        self.persist()
        self._runner_task = asyncio.create_task(self._run_job(job["id"]))
        return job

    async def _run_job(self, job_id: str) -> None:
        async with self._lock:
            job = next((j for j in self.jobs if j["id"] == job_id), None)
            task = self.get_task((job or {}).get("task_id", ""))
            if not job or not task:
                return

            self.state["running"] = True
            self.state["current_job_id"] = job_id
            job["status"] = "running"
            job["started_at"] = utc_now()
            self.persist()

            downloaded = skipped = errors = 0
            error_messages: list[str] = []
            mode = task.get("mode") or "incremental"
            remote_path = task.get("remote_path") or ""
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            # Full snapshots go into timestamped folders. Incremental updates a stable latest/ tree.
            target_root = (
                BACKUP_ROOT / task["id"] / "latest"
                if mode == "incremental"
                else BACKUP_ROOT / task["id"] / stamp
            )

            try:
                if not self.client.configured:
                    raise RuntimeError("client_id is not configured in the add-on options")
                if not self.client.is_authenticated():
                    raise RuntimeError("Not authenticated. Open the add-on UI and login to OneDrive.")

                manifest_path = DATA_DIR / f"manifest_{task['id']}.json"
                previous = load_json(manifest_path, {}) if mode == "incremental" else {}
                current_manifest: dict[str, Any] = {}

                timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async for item in self.client.iter_files(session, remote_path):
                        rel = item["_relative_path"]
                        etag = item.get("eTag") or item.get("lastModifiedDateTime") or ""
                        current_manifest[rel] = etag
                        dest = target_root / rel
                        if mode == "incremental" and previous.get(rel) == etag and dest.exists():
                            skipped += 1
                            continue
                        try:
                            await self.client.download_file(session, item, dest)
                            downloaded += 1
                        except Exception as ex:  # pylint: disable=broad-except
                            errors += 1
                            msg = f"{rel}: {ex}"
                            error_messages.append(msg)
                            _LOGGER.exception("Download failed for %s", rel)

                save_json(manifest_path, current_manifest if mode != "incremental" else {**previous, **current_manifest})

                job["status"] = "completed" if errors == 0 else "completed_with_errors"
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Backup job failed")
                job["status"] = "failed"
                errors += 1
                error_messages.append(str(ex))
            finally:
                job["completed_at"] = utc_now()
                job["summary"] = {
                    "downloaded": downloaded,
                    "skipped": skipped,
                    "errors": errors,
                    "error_messages": error_messages[:50],
                }
                self.state["running"] = False
                self.state["current_job_id"] = None
                task["last_run_at"] = job["completed_at"]
                self.persist()


STATE = AppState()


def json_response(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


async def handle_index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(Path(__file__).parent / "static" / "index.html")


async def handle_app_js(_: web.Request) -> web.FileResponse:
    return web.FileResponse(Path(__file__).parent / "static" / "app.js")


async def api_status(_: web.Request) -> web.Response:
    return json_response(STATE.status_payload())


async def api_tasks(_: web.Request) -> web.Response:
    return json_response({"tasks": STATE.tasks})


async def api_jobs(_: web.Request) -> web.Response:
    return json_response({"jobs": STATE.jobs})


async def api_backup(_: web.Request) -> web.Response:
    job = await STATE.enqueue_run(task_id=None)
    return json_response(job)


async def api_run_task(request: web.Request) -> web.Response:
    job = await STATE.enqueue_run(task_id=request.match_info["task_id"])
    return json_response(job)


async def api_login_start(_: web.Request) -> web.Response:
    try:
        payload = STATE.client.begin_device_login()
        return json_response(payload)
    except Exception as ex:  # pylint: disable=broad-except
        return json_response({"error": str(ex)}, status=400)


async def api_login_complete(_: web.Request) -> web.Response:
    try:
        # Device flow completion is blocking; run in a worker thread.
        payload = await asyncio.to_thread(STATE.client.complete_device_login)
        return json_response(payload)
    except Exception as ex:  # pylint: disable=broad-except
        return json_response({"error": str(ex)}, status=400)


async def api_upsert_task(request: web.Request) -> web.Response:
    body = await request.json()
    task_id = str(body.get("id") or uuid.uuid4())
    existing = STATE.get_task(task_id)
    task = {
        "id": task_id,
        "name": str(body.get("name") or (existing or {}).get("name") or task_id),
        "remote_path": str(body.get("remote_path") if body.get("remote_path") is not None else (existing or {}).get("remote_path") or ""),
        "mode": str(body.get("mode") or (existing or {}).get("mode") or "incremental"),
        "schedule": str(body.get("schedule") or (existing or {}).get("schedule") or "0 3 * * *"),
        "enabled": bool(body.get("enabled") if body.get("enabled") is not None else (existing or {}).get("enabled", True)),
    }
    if existing:
        idx = STATE.tasks.index(existing)
        STATE.tasks[idx] = {**existing, **task}
    else:
        STATE.tasks.append(task)
    STATE.persist()
    return json_response(task)


async def scheduler_loop() -> None:
    _LOGGER.info("Scheduler started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            for task in list(STATE.tasks):
                if not task.get("enabled", True):
                    continue
                schedule = task.get("schedule") or ""
                if not schedule or not croniter.is_valid(schedule):
                    continue
                base = task.get("last_scheduled_check")
                base_dt = datetime.fromisoformat(base) if base else now
                itr = croniter(schedule, base_dt)
                next_run = itr.get_next(datetime)
                if next_run <= now and not STATE.state.get("running"):
                    task["last_scheduled_check"] = now.isoformat()
                    STATE.persist()
                    _LOGGER.info("Scheduled run for task %s", task.get("id"))
                    try:
                        await STATE.enqueue_run(task_id=task["id"])
                    except Exception as ex:  # pylint: disable=broad-except
                        _LOGGER.warning("Scheduled enqueue skipped: %s", ex)
                else:
                    task["last_scheduled_check"] = now.isoformat()
            STATE.persist()
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Scheduler iteration failed")
        await asyncio.sleep(30)


async def on_startup(app: web.Application) -> None:
    app["scheduler"] = asyncio.create_task(scheduler_loop())


async def on_cleanup(app: web.Application) -> None:
    task = app.get("scheduler")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/static/app.js", handle_app_js)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/tasks", api_tasks)
    app.router.add_get("/api/jobs", api_jobs)
    app.router.add_post("/api/backup", api_backup)
    app.router.add_post("/api/tasks/{task_id}/run", api_run_task)
    app.router.add_post("/api/tasks", api_upsert_task)
    app.router.add_post("/api/login/start", api_login_start)
    app.router.add_post("/api/login/complete", api_login_complete)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    _LOGGER.info(
        "Listening on 0.0.0.0:%s (client_id configured=%s)",
        LISTEN_PORT,
        bool(CLIENT_ID),
    )
    web.run_app(create_app(), host="0.0.0.0", port=LISTEN_PORT)


if __name__ == "__main__":
    main()
