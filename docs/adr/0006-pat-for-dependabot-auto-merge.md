# Enable Dependabot auto-merge with a PAT, so merges trigger release-please

**Status**: accepted (2026-10-05)

`dependabot-auto-merge.yml` (ADR-0003) enabled auto-merge with the
workflow's `GITHUB_TOKEN`. GitHub suppresses every workflow run triggered
by an event that token causes (except `workflow_dispatch` and
`repository_dispatch`), and a merge queued with `gh pr merge --auto` is
attributed to whoever enabled it. So the push to `main` that an
auto-merged Dependabot PR produces triggered nothing: neither `release.yml`
(release-please never refreshed the open release PR) nor `ci.yml` on
`main`. Observed on 2026-10-05: `acryl-datahub` 1.7.0.14 and a
dev-dependencies group landed on `main` at 16:00 UTC with no Release run,
and release PR #92 kept listing only the four commits merged before them.

Auto-merge is now enabled with the maintainer's **fine-grained personal
access token**, stored as the **Dependabot secret** `AUTO_MERGE_TOKEN` (a
workflow triggered by Dependabot cannot read Actions secrets). The merge is
attributed to the maintainer, so its push triggers `release.yml` and
`ci.yml` like any by-hand merge. The token is scoped to this repository
only, with:

- Contents: read and write (perform the merge),
- Pull requests: read and write (enable auto-merge),
- Workflows: read and write (Dependabot's `github-actions` PRs edit
  `.github/workflows/*`, which a token can only merge with this
  permission).

If the secret is missing or empty, the step falls back to `GITHUB_TOKEN`
with a workflow warning: PRs still merge, as before this ADR, and
release-please catches up at the next push to `main`.

**Considered options**: a daily `schedule` trigger on `release.yml` plus a
`workflow_dispatch` without `publish_tag` (rejected by the maintainer — no
secret to manage, but the release PR lags up to a day behind and `ci.yml`
still never runs on auto-merged commits); a GitHub App token (rejected —
same effect as the PAT, but an App to create, install and keep its private
key for a solo-maintained repo); dispatching `release.yml` from the
auto-merge job (not viable — the job only *queues* the merge, which
happens later, once required checks pass).

**Consequences**: a long-lived credential now exists. It only reaches the
`auto-merge` job, which runs solely for `dependabot[bot]` PRs on `main`
(ADR-0003, `spec/spec-process-cicd-dependabot-auto-merge.md` SEC-002/SEC-005),
and is never passed to code from the PR. It expires: rotate it before its
expiry date (the maintainer's GitHub settings show it), or auto-merge
silently degrades to the `GITHUB_TOKEN` fallback. Auto-merged commits now
appear as merged by the maintainer, not by `github-actions[bot]`.
`datahub-healthdcat-ap-exporter`'s ADR-0003 rules out PATs for its own
release workflow; this ADR does not change that repo.
