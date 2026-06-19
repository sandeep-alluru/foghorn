"""Tests for foghorn.mcp_server — import guard and run_server()."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_has_mcp_flag_is_bool() -> None:
    """_HAS_MCP must be a boolean."""
    from foghorn import mcp_server
    assert isinstance(mcp_server._HAS_MCP, bool)


def test_run_server_exits_when_mcp_missing() -> None:
    """run_server() should exit with code 1 when MCP is not available."""
    import foghorn.mcp_server as mcp_mod
    with patch.object(mcp_mod, "_HAS_MCP", False):
        with pytest.raises(SystemExit) as exc_info:
            mcp_mod.run_server()
        assert exc_info.value.code == 1


def test_run_server_prints_error_when_mcp_missing(capsys) -> None:
    """run_server() should print install instructions to stderr when MCP is missing."""
    import foghorn.mcp_server as mcp_mod
    with patch.object(mcp_mod, "_HAS_MCP", False), pytest.raises(SystemExit):
        mcp_mod.run_server()
    captured = capsys.readouterr()
    assert "foghorn-ai[mcp]" in captured.err
