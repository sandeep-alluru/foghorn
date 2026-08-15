"""Path confinement helpers (CodeQL py/path-injection / CWE-22)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_DIR = ".foghorn"
MEMORY_URI = ":memory:"


class PathEscapeError(ValueError):
    """Path would escape the allowed data root."""


def data_root(root: str | Path | None = None, *, env_var: str = "") -> str:
    if root is not None:
        return os.path.realpath(os.path.expanduser(str(root)))
    env = os.environ.get(env_var, DEFAULT_DATA_DIR) if env_var else DEFAULT_DATA_DIR
    return os.path.realpath(os.path.expanduser(str(env)))


def safe_db_path(
    path: str | Path,
    *,
    root: str | Path | None = None,
    env_var: str = "",
    default_name: str = "store.db",
) -> str:
    """Return a realpath confined under a trusted root (CodeQL startswith sanitizer).

    Relative paths resolve under ``root`` / default data dir.
    Absolute paths must realpath under their parent directory
    (blocks ``/tmp/foo/../../etc/passwd``).
    """
    raw_s = str(path)
    if raw_s == MEMORY_URI:
        return MEMORY_URI
    if chr(0) in raw_s:
        raise PathEscapeError("path must not contain NUL bytes")

    expanded = os.path.expanduser(raw_s)

    if ".." in Path(expanded).parts:
        raise PathEscapeError("path must not contain '..' components")

    if root is not None or not os.path.isabs(expanded):
        base = data_root(root, env_var=env_var)
        cleaned = expanded
        for prefix in (
            DEFAULT_DATA_DIR + "/",
            DEFAULT_DATA_DIR + os.sep,
            "./" + DEFAULT_DATA_DIR + "/",
        ):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :]
                break
        if os.path.isabs(cleaned):
            full = os.path.realpath(cleaned)
        else:
            full = os.path.realpath(os.path.join(base, cleaned or default_name))
        base_prefix = base if base.endswith(os.sep) else base + os.sep
        if full != base and not full.startswith(base_prefix):
            raise PathEscapeError(f"path escapes data root {base}: {path!r}")
        return full

    parent_given = os.path.dirname(expanded) or os.curdir
    given_dir = os.path.realpath(parent_given)
    full = os.path.realpath(expanded)
    base_prefix = given_dir if given_dir.endswith(os.sep) else given_dir + os.sep
    if full != given_dir and not full.startswith(base_prefix):
        raise PathEscapeError(f"absolute path escapes its parent dir {given_dir}: {path!r}")
    return full


def ensure_parent_dir(confined_path: str) -> None:
    if confined_path == MEMORY_URI:
        return
    parent = os.path.dirname(confined_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
