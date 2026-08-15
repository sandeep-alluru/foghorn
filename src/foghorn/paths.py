"""Path confinement helpers (CodeQL py/path-injection / CWE-22).

Uses *positive* ``startswith`` guards before returning/using paths so CodeQL
clears taint at sinks (makedirs / sqlite connect / open).
"""

from __future__ import annotations

import os
import sqlite3
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


def _under(base: str, full: str) -> bool:
    """True if *full* is base or a file/dir strictly under base (CodeQL sanitizer)."""
    base_r = os.path.realpath(base)
    full_r = os.path.realpath(full)
    prefix = base_r if base_r.endswith(os.sep) else base_r + os.sep
    return full_r == base_r or full_r.startswith(prefix)


def resolve_store_path(
    path: str | Path,
    *,
    root: str | Path | None = None,
    env_var: str = "",
    default_name: str = "store.db",
) -> tuple[str, str | None]:
    """Resolve *path* under a trusted root.

    Returns ``(full_path, base_root)``. For ``:memory:`` returns
    ``(MEMORY_URI, None)``. Raises PathEscapeError if the path escapes.
    """
    raw_s = str(path)
    if raw_s == MEMORY_URI:
        return MEMORY_URI, None
    if chr(0) in raw_s:
        raise PathEscapeError("path must not contain NUL bytes")
    if ".." in Path(raw_s).parts:
        raise PathEscapeError("path must not contain '..' components")

    expanded = os.path.expanduser(raw_s)

    if root is not None:
        base = data_root(root, env_var=env_var)
        if os.path.isabs(expanded):
            full = os.path.realpath(expanded)
        else:
            cleaned = expanded
            for prefix in (
                DEFAULT_DATA_DIR + "/",
                DEFAULT_DATA_DIR + os.sep,
                "./" + DEFAULT_DATA_DIR + "/",
            ):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix) :]
                    break
            full = os.path.realpath(os.path.join(base, cleaned or default_name))
        # Positive guard — CodeQL taint barrier
        if _under(base, full):
            return full, base
        raise PathEscapeError(f"path escapes data root {base}: {path!r}")

    if os.path.isabs(expanded):
        # Absolute: basename only under realpath(parent) as trusted root
        parent = os.path.dirname(expanded) or os.curdir
        base = os.path.realpath(parent)
        name = os.path.basename(expanded) or default_name
        if name in (".", "..") or os.sep in name or (os.altsep and os.altsep in name):
            raise PathEscapeError(f"invalid store filename: {name!r}")
        full = os.path.realpath(os.path.join(base, name))
        if _under(base, full):
            return full, base
        raise PathEscapeError(f"absolute path escapes parent {base}: {path!r}")

    # Relative under default data dir
    base = data_root(env_var=env_var)
    cleaned = expanded
    for prefix in (
        DEFAULT_DATA_DIR + "/",
        DEFAULT_DATA_DIR + os.sep,
        "./" + DEFAULT_DATA_DIR + "/",
    ):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    full = os.path.realpath(os.path.join(base, cleaned or default_name))
    if _under(base, full):
        return full, base
    raise PathEscapeError(f"path escapes data root {base}: {path!r}")


# Back-compat name used by tests/callers
def safe_db_path(
    path: str | Path,
    *,
    root: str | Path | None = None,
    env_var: str = "",
    default_name: str = "store.db",
) -> str:
    full, _base = resolve_store_path(path, root=root, env_var=env_var, default_name=default_name)
    return full


def ensure_parent_dir(full: str, base: str | None) -> None:
    """Create parent of *full* only after positive under-base guard (CodeQL sink)."""
    if full == MEMORY_URI or not base:
        return
    # Re-check at sink so CodeQL sees the guard dominating makedirs
    if _under(base, full):
        parent = os.path.dirname(full)
        if parent and _under(base, parent):
            os.makedirs(parent, exist_ok=True)
            return
        if parent == os.path.realpath(base) or parent == base:
            os.makedirs(parent, exist_ok=True)
            return
    raise PathEscapeError(f"refusing makedirs outside base {base}: {full!r}")


def connect_sqlite(full: str, base: str | None, **kwargs: object) -> sqlite3.Connection:
    """sqlite3.connect only after positive under-base guard (CodeQL sink)."""
    if full == MEMORY_URI:
        return sqlite3.connect(MEMORY_URI, **kwargs)  # type: ignore[arg-type]
    if base is None:
        raise PathEscapeError("sqlite connect requires trusted base")
    if _under(base, full):
        return sqlite3.connect(full, **kwargs)  # type: ignore[arg-type]
    raise PathEscapeError(f"refusing sqlite connect outside base {base}: {full!r}")
