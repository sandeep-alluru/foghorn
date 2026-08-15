"""Coverage + security for path confinement helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from foghorn.paths import (
    PathEscapeError,
    connect_sqlite,
    ensure_parent_dir,
    resolve_store_path,
    safe_db_path,
)


def test_relative_under_root(tmp_path: Path) -> None:
    p = safe_db_path("x.db", root=tmp_path / "data")
    assert p.endswith("x.db")


def test_absolute_tmp_ok(tmp_path: Path) -> None:
    target = tmp_path / "a.db"
    p = safe_db_path(str(target))
    assert os.path.realpath(p) == os.path.realpath(str(target))


def test_rejects_dotdot(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError):
        safe_db_path("../etc/passwd", root=tmp_path)


def test_rejects_absolute_escape(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError):
        safe_db_path("/etc/passwd", root=tmp_path)


def test_memory() -> None:
    assert safe_db_path(":memory:") == ":memory:"
    full, base = resolve_store_path(":memory:")
    assert full == ":memory:"
    assert base is None


def test_ensure_parent(tmp_path: Path) -> None:
    full, base = resolve_store_path(tmp_path / "n" / "f.db")
    ensure_parent_dir(full, base)
    assert (tmp_path / "n").is_dir()


def test_nul_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError):
        safe_db_path("x" + chr(0) + ".db", root=tmp_path)


def test_connect_sqlite_memory() -> None:
    conn = connect_sqlite(":memory:", None)
    conn.execute("select 1")
    conn.close()


def test_connect_sqlite_file(tmp_path: Path) -> None:
    full, base = resolve_store_path(tmp_path / "s.db")
    ensure_parent_dir(full, base)
    conn = connect_sqlite(full, base)
    conn.execute("create table t(x int)")
    conn.close()
    assert Path(full).exists()


def test_resolve_with_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FOGHORN_DATA_DIR", str(tmp_path / "data"))
    full, base = resolve_store_path("z.db", env_var="FOGHORN_DATA_DIR")
    assert full.endswith("z.db")
    assert base is not None
