# Required PR checks

GitHub Actions workflows are versioned in this repository, but merge blocking is
a repository setting. Configure branch protection or a repository ruleset for the
protected branch (for example, `main`) with these requirements:

1. Require a pull request before merging.
2. Require status checks to pass before merging.
3. Select the required check named `Python tests` from the `Tests` workflow.
4. If merge queue is enabled, keep the `merge_group` trigger in
   `.github/workflows/tests.yml` so queued merges rerun the same checks.

With those settings enabled, GitHub will disallow merging pull requests unless
this test workflow passes.
