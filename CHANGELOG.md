# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-17

### Added
- Content-addressed `Fact` and `Decision` data model backed by SQLite
- `WorldRepo` — high-level API for fact/decision lifecycle and commit history
- Staleness propagation engine: `compute_staleness()` finds decisions invalidated by changed facts
- `WorldCommit` DAG with parent-chain traversal and `diff_commits()` for fact-level diffs
- Rich terminal output, JSON, and Markdown formatters
- Click CLI: `fact`, `decide`, `commit`, `stale`, `diff`, `log`, `status` subcommands
- FastAPI REST server: `/fact`, `/decide`, `/commit`, `/stale`, `/log`, `/health`
- MCP server (`worldgit-mcp`) for native Claude tool integration
- 77 unit tests, 87% branch coverage

[Unreleased]: https://github.com/sandeep-alluru/worldgit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sandeep-alluru/worldgit/releases/tag/v0.1.0
