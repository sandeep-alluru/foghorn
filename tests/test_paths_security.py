"""Coverage + security for path confinement helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from foghorn.paths import PathEscapeError, ensure_parent_dir, safe_db_path


def test_relative_under_root(tmp_path: Path) -> None:
    p = safe_db_path("x.db", root=tmp_path / "data")
    assert p.endswith("x.db")
    assert (
        os.path.realpath(str(tmp_path / "data")) in os.path.realpath(p)
        or str(tmp_path / "data") in p
    )


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


def test_ensure_parent(tmp_path: Path) -> None:
    target = tmp_path / "n" / "f.db"
    ensure_parent_dir(str(target))
    assert (tmp_path / "n").is_dir()


def test_nul_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError):
        safe_db_path("x" + chr(0) + ".db", root=tmp_path)
