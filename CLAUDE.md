# worldgit — Session Anchor

**Research spec:** `../tech-research/01-Memory-and-Knowledge-State/differential-knowledge-runtime-dkr-version-controlled-me/README.md`  
**One-liner:** Git for agent world-state — version-controlled, mergeable belief DAG with AGM-compliant merge  
**Phase:** backlog  
**Stack:** Python, sqlite3 (stdlib), NetworkX, rdflib  

## Key decisions
<!-- fill in as decisions are made during build sessions -->

## Next step
Read the research spec, then design the core data model: content-addressed fact snapshots + belief-commit DAG.

## MVP definition
- `pip install worldgit` works
- CLI: `worldgit commit "Alice is CEO"`, `worldgit diff HEAD~1`, `worldgit log`, `worldgit merge`
- Content-addressed immutable fact snapshots (hyperedges)
- DAG of belief commits (mutable refs)
- 3-way merge for typed triples with basic conflict detection
- SQLite backend (zero setup)
- README with git analogy and demo output
