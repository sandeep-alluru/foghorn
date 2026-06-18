Run the full pre-PR checklist and report what's ready and what needs fixing.

Steps:
1. Run lint: `make lint` (ruff check + ruff format --check)
2. Run type check: `make typecheck` (mypy)
3. Run tests: `make test` (pytest with coverage)
4. Check CHANGELOG.md has an entry under [Unreleased] for this change
5. Check that no debug print() statements or TODO comments were left in modified files

Report in this format:
  ✅ Lint — clean
  ✅ Types — clean
  ✅ Tests — 43 passed, 87% coverage
  ⚠️  CHANGELOG — no [Unreleased] entry found
  ✅ No debug artifacts

If anything fails, show the exact error and the file:line to fix.
Do not mark the PR ready until all 5 checks pass.
