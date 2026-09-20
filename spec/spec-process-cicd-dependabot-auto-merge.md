---
title: CI/CD Workflow Specification - Dependabot Auto-merge
version: 1.3
date_created: 2026-09-15
last_updated: 2026-09-20
owner: David Ouagne
tags: [process, cicd, github-actions, automation, dependencies, dependabot, supply-chain]
---

## Workflow Overview

**Purpose**: Stop the maintainer from having to manually review and merge routine, low-risk Dependabot
version bumps, while still requiring manual review for anything that could plausibly break the build —
mirrors the policy already proven in production on the sibling repo `datahub-healthdcat-ap-exporter`
(ADR-0003).

**Trigger Events**: `pull_request` targeting `main` (any event type), filtered in-job to PRs opened by
`dependabot[bot]`.

**Target Environments**: None. Acts on pull requests only; never deploys anything.

> **Status**: Implemented at `.github/workflows/dependabot-auto-merge.yml`. This document is the design
> contract that file must satisfy; changes to either should keep the other in sync, per Change
> Management below.

## Execution Flow Diagram

```mermaid
graph TD
    A[pull_request event] --> B{actor == dependabot bot?}
    B -->|no| Z[Job skipped]
    B -->|yes| C[dependabot/fetch-metadata@v3<br/>reads updated-dependencies-json]
    C --> D{every dependency in the PR is<br/>patch-level, OR minor + direct:development?}
    D -->|yes, all of them| E[gh pr merge --auto --merge<br/>queues the merge]
    D -->|no, at least one fails| F[No action -- PR waits for manual review]
    E --> G[main ruleset: CI status + dependency-review + dco + commitlint + pr-title]
    G -->|all green| H[GitHub merges the PR automatically]
    G -->|any red| I[Merge stays queued until fixed, or PR closed by hand]

    style A fill:#e1f5fe
    style H fill:#e8f5e8
    style F fill:#fff3e0
```

## Jobs & Dependencies

| Job Name | Purpose | Dependencies | Execution Context |
|----------|---------|--------------|--------------------|
| `auto-merge` | Read the triggering PR's Dependabot metadata; if **every** dependency it updates is patch-level (any dependency) or minor-level to a dev-only dependency, call `gh pr merge --auto --merge` on it. No-ops (via `if:` on the whole job) for any PR not opened by `dependabot[bot]`, and no-ops (via a `continue-on-error` eligibility step gating the merge step) for any PR where at least one updated dependency fails the classification. | None | Linux runner |

## Requirements Matrix

### Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| REQ-001 | Patch-level bumps auto-merge regardless of which dependency they touch. | High | A Dependabot PR where every entry in `updated-dependencies-json` has `updateType: version-update:semver-patch` has `gh pr merge --auto` invoked on it. |
| REQ-002 | Minor-level bumps to dev-only dependencies auto-merge. | High | A Dependabot PR where every entry in `updated-dependencies-json` is either patch-level, or `updateType: version-update:semver-minor` with `dependencyType: direct:development`, has `gh pr merge --auto` invoked on it. |
| REQ-003 | Major-version bumps never auto-merge. | High | A Dependabot PR containing **any** entry with `updateType: version-update:semver-major` does not have `gh pr merge --auto` invoked on it, regardless of what the other entries in the same PR are. |
| REQ-004 | Minor-version bumps to production (or indirect) dependencies never auto-merge. | High | A Dependabot PR containing **any** entry with `updateType: version-update:semver-minor` and `dependencyType` of `direct:production` or `indirect` does not have `gh pr merge --auto` invoked on it, regardless of what the other entries in the same PR are — this holds even inside a grouped PR that also contains an eligible dependency (REQ-003/REQ-004 are per-dependency, not per-PR-aggregate; see Error Handling Strategy for why the aggregated `update-type`/`dependency-type` outputs cannot be used for this check). |
| REQ-005 | Non-Dependabot PRs are never touched. | High | The job's `if: github.actor == 'dependabot[bot]'` skips the entire job for any other PR author. |
| REQ-006 | Auto-merge never bypasses required status checks. | High | `gh pr merge --auto` only *enables* GitHub's native auto-merge on the PR; the PR still merges only once `main`'s required status checks (`CI status`, `dependency-review`, `dco`, `commitlint`, `pr-title`) report success. |
| REQ-007 | The repository allows GitHub's native auto-merge, so `gh pr merge --auto` can actually succeed. | High | Repo setting "Allow auto-merge" (`allow_auto_merge` via `gh api repos/{owner}/{repo}`) is `true`. Enabled 2026-09-15 as part of this change (previously `false`, which would have made every eligible PR fail silently — see Error Handling Strategy). Without it, `gh pr merge --auto` fails for every eligible PR. |

### Security Requirements

| ID | Requirement | Implementation Constraint |
|----|-------------|----------------------------|
| SEC-001 | The job holds the minimum token scope it needs. | Top-level `permissions: {}`; the `auto-merge` job grants itself only `contents: write` and `pull-requests: write` (needed by `gh pr merge`), nothing else. |
| SEC-002 | The job cannot be triggered to act on arbitrary attacker-controlled PRs. | Gated on `github.actor == 'dependabot[bot]'`, which is not attacker-settable; Dependabot PRs in this repo are always same-repo branches (never forks), so no `pull_request_target`/secret-exposure concern applies. |
| SEC-003 | Auto-merge cannot silently widen beyond the two approved bump classes. | The eligibility condition is a single `jq` filter in the `eligibility` step, reviewed in this spec; any change to it is a Change-Management-tracked edit to this document. |
| SEC-004 | Dependency/package names cannot be used to inject shell commands into this workflow. | `updated-dependencies-json` is passed into the `eligibility` step via `env: DEPENDENCIES_JSON`, never interpolated directly into the `run:` script body via `${{ }}` — the standard mitigation for the GitHub Actions script-injection class. |
| SEC-005 | Auto-merge only ever acts on PRs targeting the one branch branch protection actually covers. | `on: pull_request: branches: [main]`, matching `ci.yml`'s scoping (`spec/spec-process-cicd-ci.md`'s "Branch protection on `main`" section) — a PR targeting any other branch never triggers this job at all. |

## Error Handling Strategy

| Situation | Response | Recovery Action |
|-----------|----------|-------------------|
| `dependabot/fetch-metadata` cannot parse the PR (unexpected title/branch format), returns `updated-dependencies-json` as an empty array (`[]`), or returns unparseable JSON | The `eligibility` filter opens with `(. != []) and ...` specifically so an empty array is treated as ineligible rather than vacuously satisfying `all(.[]; ...)` (which is `true` on zero elements — the initial draft got this wrong; caught in code review); unparseable JSON makes `jq -e` itself fail. Either way `continue-on-error: true` keeps the job green but the step's `outcome` is `failure`. | PR is left for manual review, same as any ineligible bump — fails safe, never fails open. |
| Required checks fail after auto-merge is enabled | GitHub holds the merge queued, does not merge | Maintainer investigates like any other red PR; fixing the check (or the offending bump) lets the queued auto-merge proceed, or the maintainer closes/edits the PR to cancel it. |
| A grouped PR (`dev-dependencies` / `prod-minor-patch` / `actions`, per `.github/dependabot.yml`) mixes bump levels across its member dependencies | **Rejected design**: `dependabot/fetch-metadata`'s top-level `update-type` and `dependency-type` outputs are each computed independently across the *whole* PR (highest semver level; highest-priority dependency type) — they do not describe the same dependency, so a group containing (say) an indirect minor bump alongside a direct-dev patch bump would read as `update-type: minor` + `dependency-type: direct:development` and wrongly pass a single combined check. **Actual design**: the `eligibility` step evaluates `updated-dependencies-json`, which carries one entry per updated dependency, and requires (via `jq`'s `all(.[]; ...)`) that *every* entry independently satisfies patch-any-or-minor-dev — so one ineligible member anywhere in the group blocks the whole PR's auto-merge. | Working as intended; this is REQ-003/REQ-004's actual enforcement mechanism, not a residual gap. Covered by VLD-007 below. |
| The repo's "Allow auto-merge" setting is off | `gh pr merge --auto` fails outright (the run shows red), and no merge is queued | One-time repo-setting prerequisite — see REQ-007 / VLD-006. Until it is enabled, every eligible PR still ends up needing a manual merge, silently defeating the point of this workflow without failing any required check. |
| `main`'s branch protection keeps `required_status_checks.strict: false` (a deliberate, pre-existing posture — see `spec/spec-process-cicd-ci.md`'s "Branch protection on `main`" section) | An auto-merged PR can land without ever having been re-tested against commits that merged to `main` after its own checks went green (e.g. another auto-merged PR in between) | Accepted residual risk, not mitigated by this workflow: the same gap already existed for by-hand merges under `strict: false`, and this spec does not change branch protection. If a stale-base merge from this path ever breaks `main`, `ci.yml`'s next run on `main` surfaces it immediately; revisit `strict` in `spec/spec-process-cicd-ci.md` if that happens more than once. |

## Quality Gates

| Gate | Criteria | Bypass Conditions |
|------|----------|----------------------|
| `main` ruleset | `CI status`, `dependency-review`, `dco`, `commitlint`, `pr-title` all pass | None — `gh pr merge --auto` requests a merge GitHub will only perform once these pass; it grants no bypass. |
| Classification correctness | Only patch (any) and minor+dev-only PRs get `gh pr merge --auto` called on them | None — this is what the workflow exists to gate; see Validation Criteria. |

## Integration Points

| Component | Relationship | Mechanism |
|-----------|---------------|--------------|
| `spec/spec-process-cicd-dependabot.md` | Upstream PR producer for scheduled version-update PRs | Triggers on `pull_request`, filtered to `dependabot[bot]` |
| Repo "Dependabot security updates" setting | Also an upstream PR producer — on-demand security-fix PRs are authored by `dependabot[bot]` too, independent of `.github/dependabot.yml`'s schedule/grouping, and pass this workflow's actor filter the same way | Same trigger/filter as above; classification (REQ-001..REQ-004) applies identically — a patch-level security fix auto-merges, a minor-to-production one still waits for review |
| `spec/spec-process-cicd-ci.md` / `spec/spec-process-cicd-dependency-review.md` | The required status checks that gate the actual merge | `main` ruleset required checks (`CI status`, `dependency-review`, `dco`, `commitlint`, `pr-title`) |
| `dependabot/fetch-metadata@v3` (third-party Action) | Supplies `updated-dependencies-json` (one entry per dependency updated by the triggering PR), which the `eligibility` step evaluates per-dependency | `uses: dependabot/fetch-metadata@v3` step, no inputs needed (reads the PR from the triggering event) |
| `docs/adr/0003-dependabot-auto-merge-policy.md` | Records the decision this workflow implements | Referenced in the workflow file's header comment |

## Validation Criteria

- **VLD-001**: Observe (or simulate, e.g. via a scratch dependency bump) a Dependabot PR whose only
  updated dependency is a patch-level bump and confirm the workflow calls `gh pr merge --auto --merge`
  on it.
- **VLD-002**: Observe/simulate a Dependabot PR whose only updated dependency is a minor-level bump to a
  dev-only dependency (`dependencyType: direct:development`) and confirm the same.
- **VLD-003**: Observe/simulate a Dependabot PR containing a major-level bump and confirm the workflow
  does **not** call `gh pr merge --auto` on it.
- **VLD-004**: Observe/simulate a Dependabot PR containing a minor-level bump to a production dependency
  (`dependencyType: direct:production`) and confirm the workflow does **not** call `gh pr merge --auto`
  on it.
- **VLD-005**: Confirm a PR opened by anyone other than `dependabot[bot]` never triggers the `auto-merge`
  job at all (check the workflow run list for that PR).
- **VLD-006**: `gh api repos/davidouagne/datahub-yaml-source -q '.allow_auto_merge'` returns `true`
  before relying on this workflow; VLD-001/VLD-002 above only pass end-to-end (PR actually merges, not
  just "auto-merge enabled") if this prerequisite holds.
- **VLD-007**: Observe/simulate a grouped PR that mixes an ineligible dependency (e.g. an indirect or
  production minor bump) alongside an otherwise-eligible one (e.g. a direct-dev patch bump) and confirm
  the workflow does **not** call `gh pr merge --auto` on it — the case the aggregated `update-type`/
  `dependency-type` outputs cannot distinguish, and the reason the `eligibility` step evaluates
  `updated-dependencies-json` per-entry instead of using them. `jq` logic covering this and the other
  six cases above can be exercised directly (no live PR needed) by piping representative
  `updated-dependencies-json` fixtures through the `eligibility` step's filter.
- **VLD-008**: `echo '[]' | jq -e '(. != []) and all(.[]; ...)'` (the `eligibility` step's exact filter)
  exits non-zero — an empty `updated-dependencies-json` must never be treated as eligible. Exercise
  directly with the fixture technique from VLD-007; no live PR needed.
- **VLD-009**: A PR authored by `dependabot[bot]` targeting a branch other than `main` does not trigger
  the `auto-merge` job at all (check the workflow run list for that PR) — `on: pull_request: branches:
  [main]` scopes the trigger before the actor `if:` is even evaluated.

## Change Management

### Update Process

1. **Specification Update**: Modify this document first.
2. **Implementation**: Apply to `.github/workflows/dependabot-auto-merge.yml`.
3. **Verification**: Confirm the Validation Criteria against a real or simulated PR of each bump type.
4. **Deployment**: Merge; the workflow applies to the next Dependabot PR that opens.

Widening or narrowing which bump types qualify for auto-merge, changing the merge method
(`--merge` vs. `--squash`/`--rebase`), or changing the actor gate are each material changes: update
this spec and `docs/adr/0003-dependabot-auto-merge-policy.md` first.

### Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-15 | Initial specification. `.github/workflows/dependabot-auto-merge.yml` added (issue #51, part of the `#48` standardization epic; policy recorded in ADR-0003, mirroring `datahub-healthdcat-ap-exporter`'s workflow of the same name): `pull_request` trigger gated to `dependabot[bot]`, `dependabot/fetch-metadata@v3` for classification, `gh pr merge --auto --merge` for patch-level (any dependency) or minor-level dev-only bumps. `spec/spec-process-cicd-dependabot.md` updated in the same change to reference this document and drop its "no auto-merge" assertions. Repo setting "Allow auto-merge" (`allow_auto_merge`) enabled via `gh api` in the same change — it was `false`, which would have made `gh pr merge --auto` fail for every eligible PR (caught in code review before merge). Also corrected an initial-draft claim that this workflow only sees `.github/dependabot.yml`-produced PRs; on-demand Dependabot security-update PRs pass the same actor filter and are classified identically. A second code-review pass (still pre-merge) caught a logic bug in the initial draft: it used the action's aggregated top-level `update-type`/`dependency-type` outputs, which are each computed independently across the whole PR and can therefore report a combination no single dependency in a grouped PR actually has (e.g. an indirect minor bump reading as eligible alongside an unrelated direct-dev patch bump). Replaced with an `eligibility` step that evaluates `updated-dependencies-json` per-dependency via `jq`'s `all(.[]; ...)`, requiring every updated dependency in the PR to independently qualify; REQ-003/REQ-004/SEC-003 and this table's grouped-PR row rewritten to match, SEC-004 and VLD-007 added. A third code-review pass (still pre-merge) caught two more issues in that same `eligibility` step and its trigger: `all(.[]; ...)` is vacuously `true` on an empty array, so a PR for which Dependabot metadata extraction failed (`updated-dependencies-json: []`) would have wrongly passed eligibility — fixed by prefixing the filter with `(. != []) and`, added SEC's coverage via VLD-008. Separately, the `pull_request` trigger had no `branches: [main]` filter (inconsistent with `ci.yml`/`quality.yml`), so a `dependabot[bot]`-authored PR targeting a branch without `main`'s required-checks protection could have had auto-merge enabled unconstrained by any required check — fixed by scoping the trigger to `branches: [main]`; added SEC-005 and VLD-009. | David Ouagne |
| 1.1 | 2026-09-15 | Cross-reference update, no workflow-file change: `main`'s actual required-status-checks list moved on twice since v1.0 (`spec/spec-process-cicd-ci.md` v1.11/v1.12) — `dependency-review` was promoted to required, then `ruff`/`mypy` were folded into `CI status` (renamed `lint`/`typecheck`) and `quality.yml` was retired/merged into `ci.yml`. Every stale `["CI status", "ruff", "mypy"]` reference in this document updated to the current `["CI status", "dependency-review"]`, and `spec/spec-process-cicd-quality.md` references replaced with `spec/spec-process-cicd-dependency-review.md`. | David Ouagne |
| 1.2 | 2026-09-15 | Cross-reference update, no workflow-file change: `.github/dependabot.yml`'s group names changed (`spec/spec-process-cicd-dependabot.md` v1.5, matching the sibling repo) from `uv-minor-patch`/`actions-minor-patch` to `dev-dependencies`/`prod-minor-patch`/`actions`. Updated the Edge Cases scenario row's illustrative group names to match; the per-member eligibility logic it describes (VLD-007) is unaffected. | David Ouagne |
| 1.3 | 2026-09-20 | Documentation-accuracy correction, no workflow-file change: `main` is now protected by a repository ruleset requiring `CI status`, `dependency-review`, `dco`, `commitlint` and `pr-title` (`spec/spec-process-cicd-ci.md` v1.13); updated the flow diagram, REQ-006, Quality Gates and Integration Points. Dependabot's commits carry `Signed-off-by: dependabot[bot]`, so the newly-required `dco` does not block auto-merge (`spec/spec-process-cicd-commit-policy.md` v1.2). | David Ouagne |

## Related Specifications

- `spec/spec-process-cicd-dependabot.md` — the PR producer this workflow consumes; owns the grouping/
  scheduling/ecosystem decisions this workflow does not touch.
- `spec/spec-process-cicd-ci.md` — `CI status`; one of the required checks `gh pr merge --auto` waits on.
- `spec/spec-process-cicd-dependency-review.md` — `dependency-review`; the other required check it waits on.
