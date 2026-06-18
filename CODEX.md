# worldgit — Codex Developer Guide

> Read by OpenAI Codex CLI. Supplements AGENTS.md with Codex-specific conventions.

## What this project does

Decision staleness alerts for AI agents

## Module map

```
src/worldgit/
├── # TODO: fill in after implementation
```

## Build and test commands

```bash
make all        # lint + typecheck + test
make test       # pytest with coverage
make lint       # ruff check + ruff format --check
make typecheck  # mypy
make fmt        # ruff format (auto-fix)
```

## Key invariants — never change without tests

- TODO: document invariants that must not be broken

## Code conventions

- Python 3.10+, fully type-annotated, mypy strict
- Ruff rules: E W F I UP B S N SIM RUF PT
- No `print()` in library code — use `rich.console.Console`
- All public functions and classes require docstrings

## What NOT to do

- Do not commit `coverage.xml` — it is in `.gitignore`
- Do not push without running `make all` first
- Do not bump `pyproject.toml` version — releases are cut by the maintainer from CHANGELOG
