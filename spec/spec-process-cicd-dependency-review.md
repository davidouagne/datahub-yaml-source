---
title: CI/CD Workflow Specification - Dependency Review (PR gate)
version: 1.2
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
| REQ-003 | A PR that introduces a dependency whose GitHub-reported license is a *single* SPDX identifier (or an `OR`-expression offering a choice that includes one) of GPL-2.0, GPL-3.0, or AGPL-3.0 (`-only` or `-or-later`) fails the check. **Does not reliably fire when GitHub reports an `AND`-combined expression** -- see Edge Cases & Known Limitations. | High | `deny-licenses` lists all six identifiers: `GPL-2.0-only`, `GPL-2.0-or-later`, `GPL-3.0-only`, `GPL-3.0-or-later`, `AGPL-3.0-only`, `AGPL-3.0-or-later`; mechanism verified directly against the action's own matching function (VLD-003). |
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
| A newly introduced dependency's GitHub-reported license is an `AND`-combined SPDX expression that includes a denied license as one of its components (e.g. `GPL-2.0-or-later AND GPL-3.0-or-later`) | **The check does not fail** -- see Edge Cases & Known Limitations below. | Accepted residual risk at this spec version; not a configuration error to "fix" from this side. A maintainer reviewing a PR that adds an unfamiliar dependency should still sanity-check its license by hand, the same practice this check was meant to reduce the need for but cannot fully replace. |

## Edge Cases & Known Limitations

**`deny-licenses` does not catch `AND`-combined SPDX license expressions, which GitHub's Python
ecosystem license detector returns for most real-world PyPI packages -- confirmed empirically, not
theoretical.**

During VLD-003 verification (throwaway PR #70, closed without merging), three different real,
genuinely GPL-licensed PyPI packages were added one at a time and checked via `gh api
repos/davidouagne/datahub-yaml-source/dependency-graph/compare/{base}...{head}`:

| Package | PyPI-declared license | GitHub dependency-graph `license` field |
|---------|------------------------|-------------------------------------------|
| `pylint` | GPL-2.0 (classifier) | `GPL-2.0-or-later AND GPL-3.0-or-later` |
| `chess` (python-chess) | GPL-3.0+ (classifier) | `GPL-1.0-or-later AND GPL-3.0 AND GPL-3.0-only AND GPL-3.0-or-later AND Python-2.0` |
| `gnureadline` | `GPL-3.0-or-later` (clean SPDX id, declared directly in PyPI metadata, not just a classifier) | `BSD-3-Clause AND GPL-1.0-or-later AND GPL-3.0 AND GPL-3.0-only AND GPL-3.0-or-later` |

All three came back as `AND`-combined expressions -- even `gnureadline`, whose own package metadata
declares a single clean SPDX id. GitHub's detector evidently scans the full source distribution for
license-bearing text (multiple files, notices, vendored fragments) rather than trusting the declared
metadata field alone, and folds everything found into one `AND` expression.

`actions/dependency-review-action`'s `deny-licenses` matching (`src/spdx.ts`,
`spdx.satisfiesAny(candidateExpr, denyList)`, backed by the `@onebeyond/spdx-license-satisfies` npm
package) was exercised directly, offline, with the exact same function and denylist this workflow
configures:

```
GPL-3.0-only                                                          -> satisfiesAny(deny) = true
GPL-3.0-or-later                                                      -> satisfiesAny(deny) = true
AGPL-3.0-only                                                         -> satisfiesAny(deny) = true
MIT                                                                   -> satisfiesAny(deny) = false
MIT OR GPL-3.0-only                                                   -> satisfiesAny(deny) = true
GPL-2.0-or-later AND GPL-3.0-or-later                                 -> satisfiesAny(deny) = false
```

This confirms the mechanism itself is correctly configured (a clean single-license or `OR`-expression
GPL/AGPL dependency **is** denied) and explains *why* the three real-package tests above never failed
the check: SPDX `AND` semantics mean "the code must be used in compliance with every listed license
simultaneously," and `satisfiesAny` asks "would using it under just this one listed license alone
satisfy that requirement" -- which an `AND`-combination can never answer yes to for a single license,
even when every individual component of the `AND` expression is itself on the deny list. This is
upstream `dependency-review-action` behavior (also noted in its own README: `deny-licenses` is marked
deprecated for possible removal, tracked at `actions/dependency-review-action#938`), not something
fixable by reconfiguring this workflow's inputs.

**Practical impact**: this check reliably blocks a dependency whose license GitHub resolves to a clean
single SPDX identifier or an `OR`-expression including one of the six denied licenses. It does **not**
reliably block one whose license GitHub resolves to an `AND`-expression -- which, per the three-for-three
sample above, appears to be the common case for real GPL-licensed PyPI packages, not an edge case. The
check remains valuable (it does catch the clean cases, and vulnerability detection -- REQ-002 -- is
unaffected by any of this), but a maintainer should not treat a passing `dependency-review` check as
proof that no GPL/AGPL code was introduced.

## Quality Gates

| Gate | Criteria | Bypass Conditions |
|------|----------|----------------------|
| `dependency-review` check | No new/changed dependency in the PR has a known vulnerability at severity `high`+, and none is licensed under a denied license | None built into the workflow itself. **A required `main` status check as of v1.2** (see Integration Points) -- a failing check blocks the "Merge pull request" button, same as `ruff`/`mypy`/`CI status`. |

**Wired into branch protection as of v1.2.** `main`'s `required_status_checks.contexts` is
`["CI status", "ruff", "mypy", "dependency-review"]` (live-verified: `gh api
repos/davidouagne/datahub-yaml-source/branches/main/protection -q
'.required_status_checks.contexts'`). At v1.0/v1.1 this check was deliberately left advisory, on the
premise that it matched sibling repo `datahub-healthdcat-ap-exporter`'s own posture for the same job
(that repo's `main` had no branch protection at all when issue #48's original comparison research was
written, 2026-09-07). That premise went stale: the sibling's own companion ticket
(`datahub-healthdcat-ap-exporter`#65) has since protected its `main` with `required_status_checks.contexts
= ["CI status", "dependency-review"]` -- `dependency-review` *is* required there. Caught by the
maintainer comparing the two repos directly (not by re-reading this spec, which is exactly the kind of
drift a "matches the sibling" justification is prone to once the sibling itself changes). Promoted here
to match, closing the gap rather than leaving the documentation's justification stale a second time.

## Integration Points

| Component | Relationship | Mechanism |
|-----------|---------------|--------------|
| `spec/spec-process-cicd-audit.md` | Sibling security signal over the same dependency tree; that one is a scheduled re-scan of already-merged `uv.lock`, this one is a pre-merge gate on the diff | Independent triggers (`schedule`/`workflow_dispatch` vs. `pull_request`); no direct coupling |
| `spec/spec-process-cicd-ci.md` | `main`'s required-status-check set (`CI status`, `ruff`, `mypy`, `dependency-review`) | This workflow's check **is** a member of that set as of v1.2 (see Quality Gates note) |
| GitHub dependency-graph API | Supplies the base..head dependency diff `dependency-review-action` evaluates | Parses `pyproject.toml`/`uv.lock`; requires the `uv` migration (issue #49) to have landed |
| `spec/spec-process-cicd-dependabot.md` | Indirect -- a Dependabot PR is itself a dependency-manifest change, so it also triggers this check | Same `pull_request` trigger surface |

## Validation Criteria

- **VLD-001**: `gh api repos/davidouagne/datahub-yaml-source/dependency-graph/sbom` lists resolved
  packages -- confirms GitHub can parse this repo's manifest (REQ-004).
- **VLD-002**: A throwaway PR adding a dependency pinned to a version with a known `high`-or-above
  severity advisory shows the `dependency-review` check-run as failed, with the flagged package/advisory
  named in its summary. **Confirmed** (PR #70, closed unmerged): `Pillow==9.0.0` failed the check,
  flagging 21 real advisories including two `critical`-severity CVEs (GHSA-8vj2-vxx3-667w,
  GHSA-3f63-hfp8-52jq).
- **VLD-003**: The `deny-licenses` matching mechanism denies a dependency whose GitHub-reported license
  is a single SPDX identifier, or an `OR`-expression containing one, from the six-identifier deny list.
  **Confirmed offline** against the action's actual matching function (`satisfiesAny` from
  `@onebeyond/spdx-license-satisfies`) -- see Edge Cases & Known Limitations for the exact cases run and
  their results, and for the confirmed gap on `AND`-combined expressions (three real-package live-PR
  attempts, none of which triggered a failure, all traced to this same root cause rather than a
  workflow misconfiguration).
- **VLD-004**: A PR that only touches non-dependency files, or bumps a dependency without introducing a
  new high-or-above vulnerability or denied license, shows the `dependency-review` check-run as passed.
- **VLD-005**: `gh api repos/davidouagne/datahub-yaml-source/branches/main/protection -q
  '.required_status_checks.contexts'` contains `dependency-review` (as of v1.2) -- confirms the
  "required, blocking" status recorded in Quality Gates is accurate at this spec version, not stale
  documentation. **Confirmed**: `["CI status","ruff","mypy","dependency-review"]`.

## Change Management

### Update Process

1. **Specification Update**: Modify this document first.
2. **Implementation**: Apply to `.github/workflows/dependency-review.yml`.
3. **Verification**: Confirm the Validation Criteria, including a real throwaway PR of each violation
   type (VLD-002, VLD-003).
4. **Deployment**: Merge; the check applies to every PR opened or updated afterward.

Changing `fail-on-severity`, the `deny-licenses` list, or the trigger scope are each material changes:
update this spec first. **Demoting this check back to advisory** would likewise be a material, deliberate
change requiring the same two-document update in reverse.

### Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-15 | Initial specification. `.github/workflows/dependency-review.yml` added (issue #57, part of the `#48` standardization epic), mirroring `datahub-healthdcat-ap-exporter`'s `dependency-review` job (there embedded in `ci.yml`; here a standalone workflow file, matching this repo's one-workflow-per-spec convention). `pull_request`-to-`main` trigger; `actions/dependency-review-action@v5` with `fail-on-severity: high` and `deny-licenses` covering GPL-2.0/3.0 and AGPL-3.0 in both `-only`/`-or-later` SPDX forms. Deliberately left out of `main`'s required status checks at this version -- issue #57's acceptance criteria did not ask for that, matching the sibling repo's own (unprotected-branch) posture for the same job. | David Ouagne |
| 1.1 | 2026-09-15 | Verification pass (throwaway PR #70, closed unmerged, per issue #57's acceptance criteria): confirmed REQ-002 live against `Pillow==9.0.0` (21 real advisories, 2 critical). While verifying REQ-003, discovered and documented a real limitation: three different genuinely GPL-licensed PyPI packages (`pylint`, `chess`, `gnureadline`) all came back from GitHub's dependency-graph API as `AND`-combined SPDX expressions rather than a clean single identifier, and `deny-licenses`' `satisfiesAny` matching (confirmed by running the action's actual matching function offline) never denies an `AND`-combined expression even when every component is on the deny list -- upstream tool behavior (the option is itself marked deprecated upstream, `actions/dependency-review-action#938`), not a misconfiguration here. Added the new "Edge Cases & Known Limitations" section, revised REQ-003/VLD-003 to state what is and isn't actually guaranteed, and added an Error Handling Strategy row for this scenario. No workflow-file change -- `deny-licenses` is left as specified (it still correctly denies the clean/`OR`-expression cases, and remains what issue #57 asked for); this is a documentation-accuracy correction, not a behavior change. | David Ouagne |
| 1.2 | 2026-09-15 | **Promoted `dependency-review` to a required `main` status check.** `main`'s `required_status_checks.contexts` changed from `["CI status", "ruff", "mypy"]` to `["CI status", "ruff", "mypy", "dependency-review"]` via `PUT /repos/davidouagne/datahub-yaml-source/branches/main/protection`. Trigger: the maintainer, comparing this repo against the sibling directly, found the sibling's `main` now requires `["CI status", "dependency-review"]` -- the "matches the sibling's advisory posture" justification recorded in v1.0/v1.1 had gone stale (the sibling's own companion ticket, `datahub-healthdcat-ap-exporter`#65, protected its `main` sometime after issue #48's 2026-09-07 comparison research was written, and this spec was never revisited to notice). Rather than re-assert a now-false "matches sibling" framing, promoted this check here too and updated Quality Gates/Integration Points/VLD-005 to describe the new, correct state, plus this version history entry so the reasoning (and the fact that it drifted once already) is preserved. No workflow-file change -- `dependency-review.yml` itself is unaffected; only branch protection and this spec changed. | David Ouagne |

## Related Specifications

- `spec/spec-process-cicd-audit.md` -- the scheduled, post-merge sibling of this pre-merge gate; both
  are SCA signals over the same dependency tree, disjoint in timing.
- `spec/spec-process-cicd-ci.md` -- owns `main`'s actual required-status-check set, which as of v1.2
  includes this workflow's `dependency-review` check; update that spec's "Branch protection on `main`"
  section alongside any future change here.
- `spec/spec-process-cicd-codeql.md` -- the other advisory, non-blocking security check already on this
  repo (SAST, not SCA); same "exists and reports, doesn't yet gate" posture.
- `spec/spec-process-cicd-dependabot.md` -- Dependabot PRs are themselves dependency-manifest changes and
  so also trigger this check.
