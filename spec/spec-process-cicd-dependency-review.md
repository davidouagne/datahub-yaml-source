---
title: CI/CD Workflow Specification - Dependency Review (PR gate)
version: 1.0
date_created: 2026-09-15
last_updated: 2026-09-15
owner: David Ouagne
tags: [process, cicd, github-actions, automation, security, license-compliance, supply-chain]
---

## Workflow Overview

**Purpose**: Block a pull request from merging if it would introduce a dependency with a
high-or-critical-severity known vulnerability, or a dependency licensed under a copyleft license
incompatible with this repo's Apache-2.0 license. Complements the weekly, already-merged-code-scoped
`pip-audit` scan (`spec/spec-process-cicd-audit.md`) by catching the same class of problem *before* a
bad dependency lands, using GitHub's own dependency-graph diff rather than a lockfile re-scan. Mirrors
the `dependency-review` job already proven in production on the sibling repo
`datahub-healthdcat-ap-exporter` (issue #57, part of the `#48` standardization epic).

**Trigger Events**: `pull_request` targeting `main`.

**Target Environments**: None. Read-only analysis of the PR's dependency-graph diff; never deploys
anything.

> **Status**: Implemented at `.github/workflows/dependency-review.yml`. This document is the design
> contract that file must satisfy; changes to either should keep the other in sync, per Change
> Management below.

## Execution Flow Diagram

```mermaid
graph TD
    A[pull_request event, targets main] --> B[actions/dependency-review-action@v5]
    B --> C{Diff base..head dependency graph}
    C --> D{Any new/changed dependency has a<br/>known vuln at severity >= high?}
    C --> E{Any new/changed dependency is licensed<br/>GPL-2.0/3.0 or AGPL-3.0 -*-only/-or-later?}
    D -->|yes| F[Check fails]
    E -->|yes| F
    D -->|no| G{E also no?}
    E -->|no| G
    G -->|yes| H[Check passes]

    style A fill:#e1f5fe
    style H fill:#e8f5e8
    style F fill:#ffebee
```

## Jobs & Dependencies

| Job Name | Purpose | Dependencies | Execution Context |
|----------|---------|--------------|--------------------|
| `dependency-review` | Run `actions/dependency-review-action@v5` against the PR's dependency-graph diff, configured with `fail-on-severity: high` and a GPL-2.0/3.0 + AGPL-3.0 `deny-licenses` list. | None | Linux runner |

## Requirements Matrix

### Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| REQ-001 | The check runs on every pull request targeting `main`. | High | `on.pull_request.branches` includes `main`; the `dependency-review` check-run appears on every such PR. |
| REQ-002 | A PR that introduces a dependency with a known vulnerability at severity `high` or above fails the check. | High | `fail-on-severity: high` on the `dependency-review-action` step; verified against a throwaway PR adding a package/version pinned to a known high-or-above CVE. |
| REQ-003 | A PR that introduces a dependency under GPL-2.0, GPL-3.0, or AGPL-3.0 (in either `-only` or `-or-later` SPDX form) fails the check. | High | `deny-licenses` lists all six identifiers: `GPL-2.0-only`, `GPL-2.0-or-later`, `GPL-3.0-only`, `GPL-3.0-or-later`, `AGPL-3.0-only`, `AGPL-3.0-or-later`; verified against a throwaway PR adding a GPL-licensed package. |
| REQ-004 | The check operates against a dependency graph GitHub can actually resolve for this repo. | High | The repo is `uv`/`pyproject.toml`-managed (post issue #49); `gh api repos/davidouagne/datahub-yaml-source/dependency-graph/sbom` lists resolved first- and third-party packages, confirming GitHub parses the manifest (a dynamic `setup.py`, this repo's pre-#49 state, was not reliably parseable this way). |
| REQ-005 | A PR that changes no dependency, or only bumps one within already-accepted severity/license bounds, passes. | High | The check reports success when the base..head dependency-graph diff contains no new high-or-above vulnerability and no newly introduced denied license. |

### Security Requirements

| ID | Requirement | Implementation Constraint |
|----|-------------|----------------------------|
| SEC-001 | The job holds the minimum token scope it needs. | Top-level `permissions: {}`; the `dependency-review` job grants itself only `contents: read`. The action needs no write access -- it only reports a check-run conclusion. |
| SEC-002 | The check cannot be widened or narrowed by a PR that also happens to be the one being evaluated. | The `fail-on-severity` threshold and `deny-licenses` list live in this workflow file on the target branch (`main`); `pull_request` (not `pull_request_target`) checks out/evaluates the PR's own code with a read-only, restricted token and cannot itself alter `main`'s copy of the workflow to weaken this check as part of the same PR. |

## Error Handling Strategy

| Situation | Response | Recovery Action |
|-----------|----------|-------------------|
| PR introduces a dependency with a `high`-or-above severity known vulnerability | `dependency-review` check fails | Drop or replace the dependency, or bump to a patched version, then push a new commit. |
| PR introduces a GPL-2.0/3.0- or AGPL-3.0-licensed dependency | `dependency-review` check fails | Find a differently-licensed alternative, or vendor only the specific piece needed under a compatible license; this check does not support per-PR overrides. |
| GitHub's dependency-graph API is unavailable or times out | The `dependency-review-action` step itself errors; the check reports failure (infrastructure failure, not a real finding) | Re-run the check once the API is available again; not distinguishable in the check UI from a real finding without opening the run log, but this repo has no auto-merge path that would need automatic disambiguation. |
| A PR touches no dependency manifest at all | The dependency-graph diff is empty; the action reports success trivially | None needed -- expected behavior. |

## Quality Gates

| Gate | Criteria | Bypass Conditions |
|------|----------|----------------------|
| `dependency-review` check | No new/changed dependency in the PR has a known vulnerability at severity `high`+, and none is licensed under a denied license | None built into the workflow itself. **Not currently a `main` required status check** (see Integration Points) -- see the note below on what this means in practice. |

**Not yet wired into branch protection.** Unlike `ruff`/`mypy`/`CI status`
(`spec/spec-process-cicd-ci.md`'s "Branch protection on `main`" section), this check is not in `main`'s
`required_status_checks.contexts` as of this spec version -- issue #57's acceptance criteria (mirroring
how `#48` scoped issue #56's `pip-audit` workflow) required only that the check exist, run on every PR,
and be verified to fail on a real violation; it did not require promoting it to a required check, and
sibling repo `datahub-healthdcat-ap-exporter`'s own `dependency-review` job is likewise advisory there
(that repo's `main` has no branch protection at all). A failing `dependency-review` check is therefore
currently visible on the PR but does not block the "Merge pull request" button the way `ruff`/`mypy`/`CI
status` do. Promoting it to required is a deliberate follow-up, not an oversight -- see Change
Management.

## Integration Points

| Component | Relationship | Mechanism |
|-----------|---------------|--------------|
| `spec/spec-process-cicd-audit.md` | Sibling security signal over the same dependency tree; that one is a scheduled re-scan of already-merged `uv.lock`, this one is a pre-merge gate on the diff | Independent triggers (`schedule`/`workflow_dispatch` vs. `pull_request`); no direct coupling |
| `spec/spec-process-cicd-ci.md` | `main`'s required-status-check set (`CI status`, `ruff`, `mypy`) | This workflow's check is **not** currently a member of that set (see Quality Gates note) |
| GitHub dependency-graph API | Supplies the base..head dependency diff `dependency-review-action` evaluates | Parses `pyproject.toml`/`uv.lock`; requires the `uv` migration (issue #49) to have landed |
| `spec/spec-process-cicd-dependabot.md` | Indirect -- a Dependabot PR is itself a dependency-manifest change, so it also triggers this check | Same `pull_request` trigger surface |

## Validation Criteria

- **VLD-001**: `gh api repos/davidouagne/datahub-yaml-source/dependency-graph/sbom` lists resolved
  packages -- confirms GitHub can parse this repo's manifest (REQ-004).
- **VLD-002**: A throwaway PR adding a dependency pinned to a version with a known `high`-or-above
  severity advisory shows the `dependency-review` check-run as failed, with the flagged package/advisory
  named in its summary.
- **VLD-003**: A throwaway PR adding a dependency under one of the six denied SPDX license identifiers
  shows the `dependency-review` check-run as failed, with the license violation named in its summary.
- **VLD-004**: A PR that only touches non-dependency files, or bumps a dependency without introducing a
  new high-or-above vulnerability or denied license, shows the `dependency-review` check-run as passed.
- **VLD-005**: `gh api repos/davidouagne/datahub-yaml-source/branches/main/protection -q
  '.required_status_checks.contexts'` does **not** (yet) contain `dependency-review` -- confirms the
  "advisory, not blocking" status recorded in Quality Gates is accurate at this spec version, not stale
  documentation.

## Change Management

### Update Process

1. **Specification Update**: Modify this document first.
2. **Implementation**: Apply to `.github/workflows/dependency-review.yml`.
3. **Verification**: Confirm the Validation Criteria, including a real throwaway PR of each violation
   type (VLD-002, VLD-003).
4. **Deployment**: Merge; the check applies to every PR opened or updated afterward.

Changing `fail-on-severity`, the `deny-licenses` list, or the trigger scope are each material changes:
update this spec first. **Promoting this check to a `main` required status check** is also a material,
deliberate change: update this spec's Quality Gates/Integration Points sections and
`spec/spec-process-cicd-ci.md`'s "Branch protection on `main`" section together, then re-apply branch
protection (`PUT /repos/davidouagne/datahub-yaml-source/branches/main/protection`) -- do not add it to
the required-checks list without updating both documents first, mirroring how `mypy`'s promotion to
required was recorded (`spec/spec-process-cicd-ci.md` v1.6, issue #13).

### Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-15 | Initial specification. `.github/workflows/dependency-review.yml` added (issue #57, part of the `#48` standardization epic), mirroring `datahub-healthdcat-ap-exporter`'s `dependency-review` job (there embedded in `ci.yml`; here a standalone workflow file, matching this repo's one-workflow-per-spec convention). `pull_request`-to-`main` trigger; `actions/dependency-review-action@v5` with `fail-on-severity: high` and `deny-licenses` covering GPL-2.0/3.0 and AGPL-3.0 in both `-only`/`-or-later` SPDX forms. Deliberately left out of `main`'s required status checks at this version -- issue #57's acceptance criteria did not ask for that, matching the sibling repo's own (unprotected-branch) posture for the same job. | David Ouagne |

## Related Specifications

- `spec/spec-process-cicd-audit.md` -- the scheduled, post-merge sibling of this pre-merge gate; both
  are SCA signals over the same dependency tree, disjoint in timing.
- `spec/spec-process-cicd-ci.md` -- owns `main`'s actual required-status-check set; this spec's Change
  Management points there for the not-yet-taken step of making this check required.
- `spec/spec-process-cicd-codeql.md` -- the other advisory, non-blocking security check already on this
  repo (SAST, not SCA); same "exists and reports, doesn't yet gate" posture.
- `spec/spec-process-cicd-dependabot.md` -- Dependabot PRs are themselves dependency-manifest changes and
  so also trigger this check.
