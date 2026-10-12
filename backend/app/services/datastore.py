"""Keep the SQLite database and uploaded files in a private GitHub repository.

Free hosts such as Render's free web services lose their disk on every restart, deploy and spin-down. When
DATA_REPO is set, start-up restores `copilot.db` and `files/` from that repository, and a snapshot is pushed
back shortly after anything changes and again on shutdown. Each day keeps one commit (later syncs that day
amend it), so the repository has a daily history without growing with every change.

If the repository cannot be read at start-up, syncing stays off, so an empty instance never overwrites it.
"""

import base64
import logging
import os
import shutil
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None
_enabled = False
_last_fingerprint: tuple | None = None


def _db_path() -> Path | None:
    url = get_settings().database_url
    return Path(url.removeprefix("sqlite:///")) if url.startswith("sqlite:///") else None


def _remote() -> str:
    repo = get_settings().data_repo.strip()
    return repo if "://" in repo or repo.startswith("/") else f"https://github.com/{repo.removesuffix('.git')}.git"


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    s = get_settings()
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "TZ": "UTC",
           "GIT_AUTHOR_NAME": "Health Copilot", "GIT_AUTHOR_EMAIL": "data@health-copilot.local",
           "GIT_COMMITTER_NAME": "Health Copilot", "GIT_COMMITTER_EMAIL": "data@health-copilot.local"}
    if s.data_repo_token:
        # pass the token as a header through the environment, so it is never in a URL, argv or .git/config
        basic = base64.b64encode(f"x-access-token:{s.data_repo_token}".encode()).decode()
        env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}"})
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
    if check and r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        if s.data_repo_token:
            msg = msg.replace(s.data_repo_token, "***")
        raise RuntimeError(f"git {args[0]} failed: {msg}")
    return r


def enabled() -> bool:
    return _enabled


def restore() -> None:
    """Fetch the latest snapshot into the data folders. Call before the database is first opened."""
    global _enabled
    s = get_settings()
    if not s.data_repo:
        return
    repo = s.data_repo_dir
    shutil.rmtree(repo, ignore_errors=True)
    repo.parent.mkdir(parents=True, exist_ok=True)
    try:
        heads = _git("ls-remote", "--heads", _remote(), s.data_repo_branch, cwd=repo.parent).stdout.strip()
        if heads:
            _git("clone", "-q", "--depth", "1", "--branch", s.data_repo_branch, _remote(), str(repo), cwd=repo.parent)
        else:
            repo.mkdir()
            _git("init", "-q", "-b", s.data_repo_branch, cwd=repo)
            _git("remote", "add", "origin", _remote(), cwd=repo)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
        log.error("Data repository %s could not be read; syncing is off so it is not overwritten. %s", s.data_repo, e)
        return

    db = _db_path()
    if db and (repo / "copilot.db").exists():
        db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / "copilot.db", db)
    if (repo / "files").is_dir():
        shutil.copytree(repo / "files", s.storage_dir, dirs_exist_ok=True)
    _enabled = True
    log.info("Restored data from %s (%s)", s.data_repo, "snapshot found" if heads else "empty repository")


def _mirror(src: Path, dst: Path) -> None:
    """Make dst an exact copy of src, copying only files that changed."""
    dst.mkdir(parents=True, exist_ok=True)
    wanted: set[Path] = set()
    for root, _, names in os.walk(src):
        for name in names:
            f = Path(root) / name
            rel = f.relative_to(src)
            wanted.add(rel)
            out = dst / rel
            st = f.stat()
            if not out.exists() or out.stat().st_size != st.st_size or int(out.stat().st_mtime) != int(st.st_mtime):
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, out)
    for root, dirs, names in os.walk(dst, topdown=False):
        for name in names:
            f = Path(root) / name
            if f.relative_to(dst) not in wanted:
                f.unlink()
        for d in dirs:
            p = Path(root) / d
            if not any(p.iterdir()):
                p.rmdir()


def _fingerprint() -> tuple:
    s = get_settings()
    db = _db_path()
    parts: list = [db.stat().st_mtime_ns if db and db.exists() else 0]
    count, newest = 0, 0
    for root, _, names in os.walk(s.storage_dir):
        for name in names:
            count += 1
            newest = max(newest, (Path(root) / name).stat().st_mtime_ns)
    return (*parts, count, newest)


def sync() -> bool:
    """Push a snapshot if anything changed. Returns True when a commit was pushed."""
    if not _enabled:
        return False
    s = get_settings()
    repo = s.data_repo_dir
    with _lock:
        db = _db_path()
        if db and db.exists():
            tmp = repo / "copilot.db.tmp"
            src, dst = sqlite3.connect(db), sqlite3.connect(tmp)
            try:
                src.backup(dst)  # consistent copy even while the app is writing
            finally:
                dst.close()
                src.close()
            os.replace(tmp, repo / "copilot.db")
        _mirror(s.storage_dir, repo / "files")
        _git("add", "-A", cwd=repo)
        if not _git("status", "--porcelain", cwd=repo).stdout.strip():
            return False
        branch = s.data_repo_branch
        today = datetime.now(timezone.utc).date().isoformat()
        message = f"Data snapshot {today}"
        amend = _git("log", "-1", "--format=%cs", cwd=repo, check=False).stdout.strip() == today
        _git("commit", "-q", *(["--amend"] if amend else []), "-m", message, cwd=repo)
        lease = [f"--force-with-lease={branch}"] if amend else []
        if _git("push", "-q", *lease, "origin", f"HEAD:{branch}", cwd=repo, check=False).returncode:
            # The remote moved since this instance last saw it (during a deploy the old instance pushes its
            # final snapshot while the new one is already running): stack this snapshot on top instead.
            _git("fetch", "-q", "--depth", "1", "origin", branch, cwd=repo)
            _git("reset", "-q", "--soft", "FETCH_HEAD", cwd=repo)
            _git("commit", "-q", "-m", message, cwd=repo)
            _git("push", "-q", "origin", f"HEAD:{branch}", cwd=repo)
        log.info("Data snapshot pushed to %s", s.data_repo)
        return True


def _watch() -> None:
    global _last_fingerprint
    interval = max(10, get_settings().data_sync_seconds)
    while not _stop.wait(interval):
        try:
            fp = _fingerprint()
            if fp != _last_fingerprint:
                sync()
                _last_fingerprint = fp
        except Exception:  # noqa: BLE001  (keep watching; the next round retries)
            log.exception("Data sync failed")


def start() -> None:
    global _thread, _last_fingerprint
    if not _enabled or _thread:
        return
    _last_fingerprint = _fingerprint()
    _stop.clear()
    _thread = threading.Thread(target=_watch, name="data-sync", daemon=True)
    _thread.start()


def stop() -> None:
    """Final snapshot on shutdown (Render sends SIGTERM before stopping or spinning down)."""
    global _thread
    _stop.set()
    if _thread:
        _thread.join(timeout=5)
        _thread = None
    try:
        sync()
    except Exception:  # noqa: BLE001
        log.exception("Final data sync failed")
