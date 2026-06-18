Prepare a release: bump version, finalize CHANGELOG, and show the git tag command.

Usage: /project:release <version>  (e.g. /project:release 0.2.0)

Steps:
1. Verify all checks pass: lint, typecheck, tests (run make all)
2. In CHANGELOG.md:
   - Rename [Unreleased] to [<version>] - <today's date in YYYY-MM-DD>
   - Add a new empty [Unreleased] section at the top
   - Update the comparison links at the bottom
3. In pyproject.toml: set version = "<version>"
4. Show the git commands needed (do NOT run them):
   ```
   git add CHANGELOG.md pyproject.toml
   git commit -m "chore: release v<version>"
   git tag v<version>
   git push origin main --tags
   ```
5. Note: the GitHub Actions release.yml will auto-publish to PyPI on tag push.

Do NOT push or tag without explicit user confirmation.
