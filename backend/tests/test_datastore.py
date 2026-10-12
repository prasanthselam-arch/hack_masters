import sqlite3
import subprocess

import pytest

from app.config import get_settings
from app.services import datastore


@pytest.fixture()
def remote(tmp_path, monkeypatch):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    s = get_settings()
    monkeypatch.setattr(s, "data_repo", str(bare))
    monkeypatch.setattr(s, "data_repo_token", "")
    monkeypatch.setattr(datastore, "_enabled", False)
    return bare


def _instance(tmp_path, monkeypatch, name):
    """Point the app at a fresh, empty disk, like a new Render instance."""
    s = get_settings()
    monkeypatch.setattr(s, "database_url", f"sqlite:///{tmp_path / name / 'copilot.db'}")
    monkeypatch.setattr(s, "storage_dir", tmp_path / name / "files")
    monkeypatch.setattr(s, "data_repo_dir", tmp_path / name / ".data-repo")
    monkeypatch.setattr(datastore, "_enabled", False)
    s.storage_dir.mkdir(parents=True)
    return tmp_path / name


def _commits(bare):
    return int(subprocess.run(["git", "rev-list", "--count", "main"], cwd=bare, capture_output=True, text=True, check=True).stdout)


def test_data_survives_a_restart_through_the_repository(remote, tmp_path, monkeypatch):
    first = _instance(tmp_path, monkeypatch, "first")
    datastore.restore()
    assert datastore.enabled()
    with sqlite3.connect(first / "copilot.db") as db:
        db.execute("create table account (login text)")
        db.execute("insert into account values ('+919876543210')")
    (first / "files" / "doc1").mkdir()
    (first / "files" / "doc1" / "original.pdf").write_bytes(b"%PDF-1.4 test")
    assert datastore.sync() is True
    assert datastore.sync() is False  # nothing changed

    second = _instance(tmp_path, monkeypatch, "second")
    datastore.restore()
    with sqlite3.connect(second / "copilot.db") as db:
        assert db.execute("select login from account").fetchall() == [("+919876543210",)]
    assert (second / "files" / "doc1" / "original.pdf").read_bytes() == b"%PDF-1.4 test"

    (second / "files" / "doc1" / "original.pdf").unlink()
    assert datastore.sync() is True
    assert _commits(remote) == 1  # same day: the snapshot commit is amended, not stacked
    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"], cwd=remote, capture_output=True, text=True).stdout
    assert "files/doc1/original.pdf" not in listing and "copilot.db" in listing


def test_overlapping_instances_do_not_reject_or_drop_snapshots(remote, tmp_path, monkeypatch):
    old = _instance(tmp_path, monkeypatch, "old")
    datastore.restore()
    (old / "files" / "a.txt").write_text("a")
    datastore.sync()
    old_state = dict(get_settings().__dict__)

    new = _instance(tmp_path, monkeypatch, "new")
    datastore.restore()
    new_state = dict(get_settings().__dict__)

    # the old instance's final snapshot lands after the new one restored
    get_settings().__dict__.update(old_state)
    (old / "files" / "b.txt").write_text("b")
    datastore.sync()

    get_settings().__dict__.update(new_state)
    (new / "files" / "c.txt").write_text("c")
    assert datastore.sync() is True
    assert _commits(remote) == 2
    old_tree = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main~1"], cwd=remote, capture_output=True, text=True).stdout
    assert "files/b.txt" in old_tree  # the old instance's snapshot is kept in history
    head = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"], cwd=remote, capture_output=True, text=True).stdout
    assert "files/c.txt" in head


def test_unreadable_repository_turns_syncing_off(tmp_path, monkeypatch, remote):
    monkeypatch.setattr(get_settings(), "data_repo", str(tmp_path / "missing.git"))
    _instance(tmp_path, monkeypatch, "lost")
    datastore.restore()
    assert not datastore.enabled()
    assert datastore.sync() is False


def test_built_frontend_is_served_with_spa_fallback(tmp_path, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    monkeypatch.setattr(get_settings(), "static_dir", dist)
    import app.main

    main = importlib.reload(app.main)
    try:
        c = TestClient(main.app)
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert c.get("/timeline").text == "<div id=root></div>"  # client-side route
        assert c.get("/api/nope").status_code == 404
        assert c.get("/api/health").json()["status"] == "ok"
        assert c.get("/../../etc/passwd").text == "<div id=root></div>"
    finally:
        monkeypatch.setattr(get_settings(), "static_dir", None)
        importlib.reload(app.main)
