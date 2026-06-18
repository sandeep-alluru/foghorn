# GitHub Copilot Instructions — foghorn

foghorn: Decision staleness alerts for AI agents

## Module map

```
src/foghorn/
├── # TODO: fill in after implementation
```

## Key invariants

- TODO: document invariants

## Code style

- Python 3.10+, type-annotated, mypy strict mode
- Ruff lint rules: E W F I UP B S N SIM RUF PT; ignore S101 (assert in tests), N806
- No `print()` in library code — use `rich.console.Console`
- All public classes and functions must have docstrings
- Tests use `pytest`; CLI tests use `click.testing.CliRunner`

## Adding a new output format

1. Add `to_<format>(result) -> str` in `report.py`
2. Add format name to `--format` choices in `cli.py`
3. Add tests

## Adding a new adapter / integration

1. Create `src/foghorn/instrument_<framework>.py`
2. Export from `__init__.py`, add to `__all__` alphabetically
3. Add tests
