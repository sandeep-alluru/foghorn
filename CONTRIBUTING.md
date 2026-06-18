# Contributing to worldgit

Thank you for your interest in contributing. This guide covers everything you need to go from zero to a merged PR.

## What we're looking for

| Contribution type | Notes |
|---|---|
| Bug fixes | Always welcome — open an issue first if it's non-obvious |
| New decision adapters | LangGraph, OpenAI Agents SDK, CrewAI integrations |
| Staleness propagation improvements | Better dependency graph traversal, cycle detection |
| Performance improvements | Batched processing, async support |
| Documentation | Examples, guides, translations |
| Tests | More edge cases, property-based tests |

## Quick start

```bash
git clone https://github.com/sandeep-alluru/worldgit
cd worldgit
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Running checks

```bash
make test       # run the full test suite
make lint       # ruff check + ruff format --check
make typecheck  # mypy
make all        # lint + typecheck + test
```

Or individually:

```bash
pytest tests/ -v
ruff check src/ tests/
mypy src/worldgit/
```

## Adding a new adapter

1. Create `src/worldgit/adapters/{framework}.py`
2. Implement a class that emits `WorldFact` and `Decision` objects
3. Export the class from `src/worldgit/adapters/__init__.py`
4. Add tests in `tests/test_{framework}_adapter.py`
5. Document the new adapter in the `## Adapters` section of the README

## Branch model

- Branch from `main`
- Name branches: `fix/describe-the-bug`, `feat/new-feature`, `docs/what-changed`
- Keep PRs focused — one logical change per PR

## PR requirements

- All tests must pass (`make test`)
- No new lint or type errors (`make lint && make typecheck`)
- New behaviour must have corresponding tests
- Update `CHANGELOG.md` under `[Unreleased]`
- Follow [Conventional Commits](https://www.conventionalcommits.org/) for the PR title:
  `fix:`, `feat:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`

## Review timeline

PRs are reviewed within **5 business days**. If you haven't heard back, ping `@sandeep-alluru` in the PR comments.

## Code style

- Ruff for formatting and linting (configured in `pyproject.toml`)
- MyPy for type checking
- All public functions and classes require docstrings
- No `print()` in library code — use `rich.console.Console` or logging
- No silent failures — raise descriptive exceptions at boundaries

## Commit signing

We recommend signing commits (`git config commit.gpgsign true`) but do not require it.
