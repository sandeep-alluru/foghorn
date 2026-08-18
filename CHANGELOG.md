# Changelog


## [0.1.4] - 2026-08-18

### Changed
- Publish Glama/MCP readiness: mcp pin <2, TDQS tool descriptions, Dockerfile from repo tip, glama.json.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `PropagationResult` and `propagate_staleness()` — build a propagation graph from
  changed facts to directly and transitively stale decisions, with depth tracking
- `export_json()`, `import_json()`, and `export_graphviz()` — export/import the full
  repo state as JSON; export fact→decision dependency graph in Graphviz DOT format
- `Recommendation` and `recommend()` — generate prioritized actionable recommendations
  ("re-evaluate", "archive", "update-fact") for all stale decisions
- `WorldRepo.export_json()`, `WorldRepo.recommend()`, `WorldRepo.propagate()` — convenience
  methods on the main entry point for the three new capabilities
- CLI command `foghorn recommend` — display a Rich table of all staleness recommendations
- Exports in `__init__.py`: `PropagationResult`, `Recommendation`, `propagate_staleness`,
  `recommend`, `export_json`, `import_json`, `export_graphviz`

## [0.1.0] - 2026-06-17

### Added
- Content-addressed `Fact` and `Decision` data model backed by SQLite
- `WorldRepo` — high-level API for fact/decision lifecycle and commit history
- Staleness propagation engine: `compute_staleness()` finds decisions invalidated by changed facts
- `WorldCommit` DAG with parent-chain traversal and `diff_commits()` for fact-level diffs
- Rich terminal output, JSON, and Markdown formatters
- Click CLI: `fact`, `decide`, `commit`, `stale`, `diff`, `log`, `status` subcommands
- FastAPI REST server: `/fact`, `/decide`, `/commit`, `/stale`, `/log`, `/health`
- MCP server (`foghorn-mcp`) for native Claude tool integration
- 77 unit tests, 87% branch coverage

[Unreleased]: https://github.com/sandeep-alluru/foghorn/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sandeep-alluru/foghorn/releases/tag/v0.1.0
