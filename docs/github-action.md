# GitHub Action

Use worldgit directly in your GitHub Actions workflow:

```yaml
- name: worldgit
  uses: sandeep-alluru/worldgit@v0.1.0
  with:
    # TODO: add action inputs
    fail-on-error: "true"
```

Or use the CLI directly:

```yaml
- name: Install worldgit
  run: pip install worldgit

- name: Run worldgit
  run: worldgit --help
```
