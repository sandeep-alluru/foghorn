# Contributing

For the full contribution guide see [CONTRIBUTING.md](../CONTRIBUTING.md) in the repo root.

## Quick links

- [Bug report](https://github.com/sandeep-alluru/foghorn/issues/new?template=bug_report.yml)
- [Feature request](https://github.com/sandeep-alluru/foghorn/issues/new?template=feature_request.yml)
- [Architecture](architecture.md)

## Dev setup

```bash
git clone https://github.com/sandeep-alluru/foghorn
cd foghorn
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Make targets

```bash
make all        # lint + typecheck + test
make test       # pytest with coverage
make lint       # ruff check + format check
make typecheck  # mypy
make fmt        # ruff format (auto-fix)
make docs       # mkdocs serve (live preview)
```
