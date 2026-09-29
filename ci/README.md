# CI workflow (not active yet)

`github-ci.yml` is the GitHub Actions pipeline (lint → layer contracts → types → tests →
import smoke test → build → secret scan). It lives here because the Claude GitHub app may not
write to `.github/workflows/` without the `workflows` permission.

To turn CI on, either:
- on GitHub: open `ci/github-ci.yml` → rename the path to `.github/workflows/ci.yml` → commit; or
- locally: `git mv ci/github-ci.yml .github/workflows/ci.yml && git commit -m "ci: enable" && git push`.
