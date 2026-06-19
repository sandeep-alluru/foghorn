# GitHub Action

Use foghorn directly in your GitHub Actions workflow:

```yaml
- name: foghorn
  uses: sandeep-alluru/foghorn@v0.1.0
  with:
    # TODO: add action inputs
    fail-on-error: "true"
```

Or use the CLI directly:

```yaml
- name: Install foghorn
  run: pip install foghorn-ai

- name: Run foghorn
  run: foghorn --help
```
