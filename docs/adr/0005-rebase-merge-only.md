# Rebase merge only, and drop the PR-title check

**Status**: accepted (2026-10-05)

Every release since `v0.2.0` listed each changelog entry twice — e.g.
`v0.2.4`'s "align CI/CD docs with the main branch ruleset" appears once for
the branch commit (`3a0bd72`) and once for the merge commit of PR #85
(`46408cb`). `main` only accepted merge commits, and GitHub always puts the
PR title in a merge commit's message (as subject or body: the only accepted
combinations are `PR_TITLE`/`PR_BODY`, `PR_TITLE`/`BLANK` and
`MERGE_MESSAGE`/`PR_TITLE`). Since the `pr-title` check forced that title to
be a Conventional Commit, release-please parsed it as one on top of the
branch commits, and it has no option to skip merge commits.

`main` now accepts **rebase merge only**: `allow_rebase_merge: true`,
`allow_merge_commit: false`, `allow_squash_merge: false` at the repo level,
and `allowed_merge_methods: ["rebase"]` plus `required_linear_history` in
the `main` ruleset. Every branch commit lands on `main` as-is, with no merge
commit, so release-please reads each change exactly once. The PR title no
longer reaches history, so the `pr-title` job (and its required status
check) is removed; `commitlint` and `dco` still check every commit.
Dependabot auto-merge switches to `gh pr merge --auto --rebase`
(ADR-0003's policy is otherwise unchanged).

This aligns with the sibling repo `datahub-healthdcat-ap-exporter`, which
hit the same duplication (its releases 0.1.3 to 0.1.9) and made the same
switch the same day (its ADR-0002 §1).

**Considered options**: squash merge only (rejected — the changelog would
then depend on the PR title alone, losing the per-commit Conventional
Commit log that ADR-0001 relies on); keep merge commits and make the PR
title non-conventional (rejected — nothing would enforce that, and a
conventional-looking title would silently reintroduce duplicates).

**Consequences**: a branch must be kept free of merge commits and updated
by rebase ("Update with rebase"), not by merging `main` into it. GitHub
rewrites rebased commits (new SHAs) but keeps their `Signed-off-by`
trailers, so `dco` is unaffected. Required status checks on `main` drop to
four: `CI status`, `dependency-review`, `dco`, `commitlint`. ADR-0001's
consequence that "a semantic PR-title check [is] enforced in CI" is
superseded by this ADR. Changelog entries already published for
`v0.2.0`–`v0.2.4` keep their duplicates; they are not rewritten.
