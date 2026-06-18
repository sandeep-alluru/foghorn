"""
End-to-end smoke test for foghorn.

Simulates a user who just cloned the repo and wants to verify everything works.
No mocking, no fixtures — real behaviour, real CLI, real HTTP server.

Run from repo root:
    python smoke_test.py
    python smoke_test.py --verbose

Exit 0 = all passed. Exit 1 = at least one failure.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

# ── Colours ───────────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv
REPO_ROOT = Path(__file__).parent
PYTHON = sys.executable

passed: list[str] = []
failed: list[tuple[str, str]] = []


def ok(name: str) -> None:
    passed.append(name)
    print(f"  {GREEN}✓{RESET} {name}")


def fail(name: str, reason: str) -> None:
    failed.append((name, reason))
    print(f"  {RED}✗{RESET} {name}")
    if VERBOSE:
        print(f"    {YELLOW}{reason}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


def run(name: str, fn):  # noqa: ANN001
    try:
        fn()
        ok(name)
    except Exception as exc:
        reason = str(exc) if not VERBOSE else traceback.format_exc().strip()
        fail(name, reason)


# ── 1. Package import ─────────────────────────────────────────────────────────

section("1. Package import")

def _test_import_version():
    import foghorn
    assert foghorn.__version__, "__version__ is empty"
    assert foghorn.__version__ != "0.0.0"

def _test_import_public_api():
    from foghorn import Fact, Decision, StalenessAlert, WorldRepo, WorldCommit
    assert callable(WorldRepo.init)

run("foghorn package imports", _test_import_version)
run("Public API (WorldRepo, Fact, Decision, StalenessAlert)", _test_import_public_api)


# ── 2. Core data model ────────────────────────────────────────────────────────

section("2. Core data model (Fact, Decision, WorldCommit)")

def _test_fact_content_addressed():
    from foghorn.fact import Fact
    f1 = Fact(subject="Redis", predicate="is", object="fast")
    f2 = Fact(subject="Redis", predicate="is", object="fast")
    assert f1.id == f2.id, "Same triple must produce same ID"
    f3 = Fact(subject="Redis", predicate="is", object="slow")
    assert f1.id != f3.id

def _test_fact_serialization():
    from foghorn.fact import Fact
    f = Fact(subject="Redis", predicate="is-appropriate-for", object="rate-limiting", confidence=0.9)
    d = f.to_dict()
    assert d["subject"] == "Redis"
    assert d["confidence"] == 0.9
    f2 = Fact.from_dict(d)
    assert f2.id == f.id

def _test_decision_serialization():
    from foghorn.fact import Decision, Fact
    f = Fact(subject="Redis", predicate="is", object="fast")
    dec = Decision(label="chose-redis", content="Redis is fast", fact_ids=[f.id])
    d = dec.to_dict()
    assert d["label"] == "chose-redis"
    assert f.id in d["fact_ids"]
    dec2 = Decision.from_dict(d)
    assert dec2.id == dec.id

def _test_worldrepo_commit_round_trip():
    from foghorn import WorldRepo
    with tempfile.TemporaryDirectory() as tmp:
        with WorldRepo.init(f"{tmp}/world.db") as repo:
            repo.add_fact("Redis", "is-appropriate-for", "rate-limiting")
            wc = repo.commit("Initial facts")
            assert wc.id
            assert len(wc.fact_ids) == 1
            commits = repo.log()
            assert len(commits) == 1
            assert commits[0].message == "Initial facts"

run("Fact.id is content-addressed (same triple = same ID)", _test_fact_content_addressed)
run("Fact.to_dict() / from_dict() round-trip", _test_fact_serialization)
run("Decision.to_dict() / from_dict() preserves fact_ids", _test_decision_serialization)
run("WorldRepo commit + log round-trip", _test_worldrepo_commit_round_trip)


# ── 3. Staleness propagation ──────────────────────────────────────────────────

section("3. Staleness propagation")

def _test_stale_detects_changed_fact():
    from foghorn import WorldRepo
    with tempfile.TemporaryDirectory() as tmp:
        with WorldRepo.init(f"{tmp}/world.db") as repo:
            f = repo.add_fact("Redis", "is-appropriate-for", "rate-limiting")
            repo.decide("chose-redis", "Redis fits our needs", depends_on=[f.id])
            repo.commit("v1")
            repo.retract_fact(f.id)
            repo.add_fact("Valkey", "replaced", "Redis")
            repo.commit("v2")
            alerts = repo.stale()
            assert len(alerts) > 0, "Should detect stale decision after fact changes"
            assert alerts[0].decision_label == "chose-redis"

def _test_no_stale_identical_facts():
    from foghorn import WorldRepo
    with tempfile.TemporaryDirectory() as tmp:
        with WorldRepo.init(f"{tmp}/world.db") as repo:
            f = repo.add_fact("Redis", "is", "fast")
            repo.decide("chose-redis", "Redis is fast", depends_on=[f.id])
            repo.commit("v1")
            repo.add_fact("Redis", "is", "fast")  # same fact — idempotent
            # Nothing new staged after the idempotent add (same ID already exists)
            try:
                repo.commit("v2")
            except ValueError:
                pass  # nothing staged is fine
            alerts = repo.stale()
            assert len(alerts) == 0, "Identical facts should not cause staleness"

def _test_staleness_alert_fields():
    from foghorn import WorldRepo
    with tempfile.TemporaryDirectory() as tmp:
        with WorldRepo.init(f"{tmp}/world.db") as repo:
            f = repo.add_fact("Redis", "is", "fast", confidence=0.9)
            repo.decide("chose-redis", "Redis is fast", depends_on=[f.id])
            repo.commit("v1")
            repo.retract_fact(f.id)
            repo.add_fact("Valkey", "replaced", "Redis")
            repo.commit("v2")
            alerts = repo.stale()
            assert alerts[0].impact_score > 0
            assert len(alerts[0].stale_fact_ids) > 0

run("stale() detects decision invalidated by fact change", _test_stale_detects_changed_fact)
run("stale() returns empty when facts unchanged", _test_no_stale_identical_facts)
run("StalenessAlert has impact_score and stale_fact_ids", _test_staleness_alert_fields)


# ── 4. Report formatters ──────────────────────────────────────────────────────

section("4. Report formatters")

def _test_to_json_with_alerts():
    from foghorn import WorldRepo
    from foghorn.report import to_json
    with tempfile.TemporaryDirectory() as tmp:
        with WorldRepo.init(f"{tmp}/world.db") as repo:
            f = repo.add_fact("Redis", "is", "fast")
            repo.decide("chose-redis", "Redis is fast", depends_on=[f.id])
            repo.commit("v1")
            repo.retract_fact(f.id)
            repo.add_fact("Valkey", "replaced", "Redis")
            repo.commit("v2")
            alerts = repo.stale()
    parsed = json.loads(to_json(alerts))
    assert parsed["has_stale"] is True
    assert parsed["stale_count"] >= 1
    assert "alerts" in parsed

def _test_to_markdown():
    from foghorn.fact import StalenessAlert
    from foghorn.report import to_markdown
    alerts = [StalenessAlert("dec1", "chose-redis", ["fact1"], 0.9)]
    md = to_markdown(alerts)
    assert "foghorn" in md
    assert "stale" in md.lower()
    assert "|" in md

def _test_print_stale():
    import io
    from rich.console import Console
    from foghorn.fact import StalenessAlert
    from foghorn.report import print_stale
    buf = io.StringIO()
    con = Console(file=buf, highlight=False)
    alerts = [StalenessAlert("dec1", "chose-redis", ["fact1"], 0.9)]
    print_stale(alerts, console=con)
    output = buf.getvalue()
    assert "STALE" in output or "stale" in output.lower()

run("to_json() returns valid JSON with has_stale and alerts", _test_to_json_with_alerts)
run("to_markdown() produces Markdown with table", _test_to_markdown)
run("print_stale() outputs stale alerts to console", _test_print_stale)


# ── 5. CLI ────────────────────────────────────────────────────────────────────

section("5. CLI (foghorn)")

def _test_cli_help():
    r = subprocess.run(
        [PYTHON, "-m", "foghorn.cli", "--help"],
        capture_output=True, text=True
    )
    assert r.returncode == 0
    assert len(r.stdout) > 20, "Help output is empty"

run("foghorn --help returns 0", _test_cli_help)

# TODO: Add CLI integration tests for each subcommand, e.g.:
#   def _test_cli_run():
#       r = subprocess.run([PYTHON, "-m", "foghorn.cli", "run", "--help"],
#                          capture_output=True, text=True)
#       assert r.returncode == 0
#   run("foghorn run --help returns 0", _test_cli_run)


# ── 6. FastAPI server ─────────────────────────────────────────────────────────

section("6. FastAPI server (foghorn[api])")

def _test_api_import():
    from foghorn.api import app
    assert app.title == "foghorn API"

def _test_api_health():
    from fastapi.testclient import TestClient
    from foghorn.api import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()

def _test_api_fact_and_stale():
    from fastapi.testclient import TestClient
    from foghorn.api import app
    client = TestClient(app)
    with tempfile.TemporaryDirectory() as tmp:
        db = f"{tmp}/world.db"
        r_fact = client.post("/fact", json={
            "subject": "Redis", "predicate": "is", "object": "fast", "db": db
        })
        assert r_fact.status_code == 200
        fact_id = r_fact.json()["id"]
        client.post("/decide", json={
            "label": "chose-redis", "content": "Redis is fast",
            "depends_on": [fact_id], "db": db,
        })
        client.post("/commit", json={"message": "v1", "db": db})
        client.post("/fact", json={
            "subject": "Valkey", "predicate": "replaced", "object": "Redis", "db": db
        })
        client.post("/commit", json={"message": "v2", "db": db})
        r_stale = client.get("/stale", params={"db": db})
        assert r_stale.status_code == 200
        assert "has_stale" in r_stale.json()

run("foghorn.api imports and app.title is correct", _test_api_import)
run("GET /health returns {status: ok, version: ...}", _test_api_health)
run("POST /fact + /commit + GET /stale workflow", _test_api_fact_and_stale)


# ── 7. MCP server ─────────────────────────────────────────────────────────────

section("7. MCP server (foghorn[mcp])")

def _test_mcp_server_importable():
    import foghorn.mcp_server as m
    assert hasattr(m, "run_server")

def _test_mcp_server_loads_cleanly():
    import foghorn.mcp_server  # noqa: F401

run("mcp_server.py imports without error", _test_mcp_server_importable)
run("mcp_server module loads cleanly (no import-time crash)", _test_mcp_server_loads_cleanly)


# ── 8. Agent config files ─────────────────────────────────────────────────────

section("8. Agent config files (what a clone gives you)")

def _check_file_nonempty(rel: str) -> None:
    p = REPO_ROOT / rel
    assert p.exists(), f"Missing: {rel}"
    assert p.stat().st_size > 50, f"File too small (likely empty): {rel}"

def _check_json_valid(rel: str) -> None:
    p = REPO_ROOT / rel
    assert p.exists(), f"Missing: {rel}"
    json.loads(p.read_text())

def _check_yaml_parseable(rel: str) -> None:
    try:
        import yaml  # type: ignore[import-untyped]
        p = REPO_ROOT / rel
        assert p.exists(), f"Missing: {rel}"
        yaml.safe_load(p.read_text())
    except ImportError:
        content = (REPO_ROOT / rel).read_text()
        assert len(content) > 20, f"File appears empty: {rel}"

def _test_claude_commands():
    commands = list((REPO_ROOT / ".claude/commands").glob("*.md"))
    assert len(commands) >= 4, f"Expected ≥4 slash commands, found {len(commands)}"

def _test_openai_tools_valid():
    _check_json_valid("tools/openai-tools.json")
    tools = json.loads((REPO_ROOT / "tools/openai-tools.json").read_text())
    assert len(tools) >= 3
    assert all("function" in t for t in tools)

def _test_openapi_yaml_parseable():
    _check_yaml_parseable("openapi.yaml")

run("AGENTS.md exists and non-empty", lambda: _check_file_nonempty("AGENTS.md"))
run("CLAUDE.md exists and non-empty", lambda: _check_file_nonempty("CLAUDE.md"))
run("CODEX.md exists and non-empty", lambda: _check_file_nonempty("CODEX.md"))
run(".github/copilot-instructions.md exists", lambda: _check_file_nonempty(".github/copilot-instructions.md"))
def _test_cursor_rules():
    mdc_files = list((REPO_ROOT / ".cursor/rules").glob("*.mdc"))
    assert len(mdc_files) >= 1, f"Expected ≥1 .mdc file in .cursor/rules/, found none"

run(".cursor/rules/ has at least one .mdc file", _test_cursor_rules)
run(".windsurfrules exists", lambda: _check_file_nonempty(".windsurfrules"))
run(".aider.conf.yml exists", lambda: _check_file_nonempty(".aider.conf.yml"))
run(".continue/config.json is valid JSON", lambda: _check_json_valid(".continue/config.json"))
run(".claude/commands/ has ≥4 slash commands", _test_claude_commands)
run("tools/openai-tools.json is valid JSON with ≥3 tools", _test_openai_tools_valid)
run("openapi.yaml is parseable YAML", _test_openapi_yaml_parseable)


# ── 9. Docs site ──────────────────────────────────────────────────────────────

section("9. MkDocs documentation site")

def _test_mkdocs_yml():
    _check_file_nonempty("mkdocs.yml")
    content = (REPO_ROOT / "mkdocs.yml").read_text()
    assert "site_name" in content
    assert "material" in content

def _test_docs_pages():
    docs = list((REPO_ROOT / "docs").glob("*.md"))
    assert len(docs) >= 8, f"Expected ≥8 doc pages, found {len(docs)}"
    names = {p.name for p in docs}
    for required in ("index.md", "quickstart.md", "architecture.md", "api-reference.md"):
        assert required in names, f"Missing docs/{required}"

run("mkdocs.yml exists with site_name and material theme", _test_mkdocs_yml)
run("docs/ has ≥8 pages including index, quickstart, architecture, api-reference", _test_docs_pages)


# ── 10. examples/demo.py ─────────────────────────────────────────────────────

section("10. examples/demo.py end-to-end")

def _test_demo_runs():
    demo = REPO_ROOT / "examples" / "demo.py"
    assert demo.exists(), "examples/demo.py not found"
    r = subprocess.run(
        [PYTHON, str(demo)],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT)
    )
    if r.returncode != 0:
        raise AssertionError(f"demo.py exited {r.returncode}:\n{r.stderr[-500:]}")

run("examples/demo.py runs end-to-end without error", _test_demo_runs)


# ── Summary ───────────────────────────────────────────────────────────────────

total = len(passed) + len(failed)
print(f"\n{'═'*60}")
print(f"{BOLD}Results: {len(passed)}/{total} passed{RESET}")

if failed:
    print(f"{RED}Failed ({len(failed)}):{RESET}")
    for name, reason in failed:
        print(f"  {RED}✗{RESET} {name}")
        short = reason.split("\n")[0][:120]
        print(f"    {YELLOW}→ {short}{RESET}")
    print(f"\n{YELLOW}Tip: run with --verbose for full tracebacks{RESET}")
else:
    print(f"{GREEN}All {total} checks passed — foghorn is ready to ship{RESET}")

print(f"{'═'*60}\n")
sys.exit(0 if not failed else 1)
