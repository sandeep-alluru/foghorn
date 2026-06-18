Domain-specific slash commands for foghorn.

Replace this file with commands that match the tool's core operations.
See agentdelta's .claude/commands/ for reference examples:
  - diff.md    — runs the primary comparison operation
  - inspect.md — inspects a single artifact
  - record.md  — generates recording boilerplate
  - add-adapter.md — scaffolds a new framework adapter

Naming convention: /project:<verb> where verb describes what it does,
not what it is. "diff" not "agentdelta", "record" not "trace".
