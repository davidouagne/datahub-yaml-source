---
title: CI/CD Process Specification - Dependency Updates (Dependabot)
version: 1.0
date_created: 2026-09-07
last_updated: 2026-09-07
owner: David Ouagne
tags: [process, cicd, github, automation, dependencies, dependabot, supply-chain]
---

## Process Overview

**Purpose**: Keep the project's Python dependencies and GitHub Actions pins current with low manual
overhead, without ever merging a dependency change unreviewed. Dependabot opens the PRs; a human
reviews and merges every one.

**Trigger**: Dependabot's own weekly schedule (Mondays). Not a GitHub Actions workflow — this is the
native Dependabot service, configured by `.github/dependabot.yml`. There is no file under
`.github/workflows/` for it, so this document is the design contract for `.github/dependabot.yml`
directly (same arrangement as `spec/spec-process-cicd-codeql.md`).

**Target Environments**: None. Produces pull requests only.

> **Status**: Implemented at `.github/dependabot.yml`. Changes to either that file or this document
> should keep the other in sync, per Change Management below.

## Execution Flow Diagram

```mermaid
graph TD
    A[Dependabot weekly scan - Monday] --> B{Updates available?}
    B -->|minor / patch| C[One grouped PR per ecosystem<br/>pip-minor-patch / actions-minor-patch]
    B -->|major| D[One individual PR per dependency]
    C --> E[ci.yml + quality.yml run on the PR]
    D --> E
    E --> F[Maintainer reviews & merges by hand<br/>no auto-merge]

    style A fill:#e1f5fe
    style F fill:#fff3e0
```

## Configuration (authoritative pointer: `.github/dependabot.yml`)

This section records the decisions and their rationale; the file is the source of truth.

| Setting | Value | Rationale |
|---------|-------|-----------|
| `version` | `2` | Current Dependabot config schema. |
| Ecosystems | `pip` (`/`) and `github-actions` (`/`) | `pip` covers `setup.py` + `pyproject.toml` at the repo root (`install_requires` + all extras, including `dev`). `github-actions` covers the `uses:` pins in `.github/workflows/*.yml`. |
| `schedule.interval` | `weekly` | One batch a week is enough churn for a solo maintainer; `daily` would just lengthen the manual queue. |
| `schedule.day` | `monday` | Predictable — the maintainer knows when to expect the PRs. |
| `groups` (per ecosystem) | `pip-minor-patch`, `actions-minor-patch`: `patterns: ["*"]`, `update-types: ["minor", "patch"]` | Collapse all non-breaking bumps into **one PR per ecosystem** to keep the manual merge queue short. Major updates are deliberately left **out** of the groups, so each breaking bump lands as its own PR and is reviewed in isolation. |
| `open-pull-requests-limit` | `5` per ecosystem | With grouping, steady state is ~1 grouped PR + a few majors; 5 is headroom without letting the queue balloon. |
| `labels` | `["dependencies"]` | Feeds the `⬆️ Dependencies` category in `.github/release.yml` (auto-generated release notes). The `dependencies` label is created in the repo (colour `#0366d6`), not left to Dependabot's implicit creation. |
| `commit-message.prefix` | `build` (pip), `ci` (github-actions); `include: scope` on pip | Matches the repo's conventional-commit history (`build:` for packaging/deps, `ci:` for workflow/tooling). |
| `ignore` | **none** | See below. |
| Auto-merge | **not configured** — deliberate | Recorded on wayfinder map issue #1: every dependency PR, patch and minor included, is merged by hand. No `dependabot`/automerge Action, no branch rule granting it. |

### No `ignore` for `acryl-datahub` majors

`setup.py` pins `acryl-datahub>=1.7.0,<1.7.0.5` on purpose — the `1.7.0.x` series takes undeprecated
breaks in the experimental `datahub.sdk.*` surface this connector builds on (documented inline in
`setup.py`). Dependabot will open a PR proposing to lift that ceiling. That PR is **wanted**: the
by-hand review it gets (like every dependency PR) is the gate, and lifting the cap is tracked as its
own migration task elsewhere. An `ignore` rule would only suppress a signal the maintainer wants
queued.

### What Dependabot will not touch

`release.yml` pins `pypa/gh-action-pypi-publish@release/v1` — a **branch** ref. Dependabot's
`github-actions` updater only bumps tag and SHA pins, not branch refs, so this pin is maintained by
hand (it is the action's publisher-recommended moving pointer).

## Requirements Matrix

### Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| REQ-001 | Python deps are monitored. | High | A `pip` update block with `directory: "/"` exists; Dependabot's "Last checked" for pip is current on the repo's Insights > Dependency graph > Dependabot tab. |
| REQ-002 | Workflow action pins are monitored. | High | A `github-actions` update block with `directory: "/"` exists and is shown as active. |
| REQ-003 | Non-breaking bumps do not flood the queue. | High | Minor/patch updates for an ecosystem arrive as a single grouped PR, not one per package. |
| REQ-004 | Breaking bumps are individually reviewable. | Medium | A major-version update appears as its own PR, outside the group. |
| REQ-005 | No dependency change merges unreviewed. | High | No auto-merge configuration exists anywhere in the repo; `main` has no rule that would auto-merge a Dependabot PR. |
| REQ-006 | Dependabot PRs are categorised in release notes. | Low | Dependabot PRs carry the `dependencies` label; `.github/release.yml` routes it to `⬆️ Dependencies`. |

### Security Requirements

| ID | Requirement | Implementation Constraint |
|----|-------------|---------------------------|
| SEC-001 | Dependabot security updates stay enabled. | Repo setting "Dependabot security updates" is on; a `dependabot.yml` presence does not disable it. Security PRs bypass the weekly schedule by design. |
| SEC-002 | No secret is exposed to Dependabot. | The config declares no `registries`; all indexes are public (PyPI, GitHub). |

## Error Handling Strategy

| Situation | Response | Recovery Action |
|-----------|----------|------------------|
| Grouped PR's CI fails (`ci.yml` / `quality.yml`) | PR stays open, red | Inspect which member bump broke it; comment `@dependabot recreate` after splitting, or bump the offending package's constraint by hand and close the PR. |
| A major bump PR is unwanted right now | Leave open or close | Closing tells Dependabot to stop re-opening that exact version; it will re-propose on the next major. Add a scoped `ignore` only if a bump must be suppressed long-term (spec update required). |
| `dependabot.yml` is itself malformed | Dependabot posts an error on the repo's Dependabot tab; no PRs are opened | Fix per the error; validate against GitHub's `dependabot.yml` schema. |

## Quality Gates

| Gate | Criteria | Bypass Conditions |
|------|----------|---------------------|
| CI on Dependabot PRs | `ci.yml` (`CI status`) and `quality.yml` (`ruff`) pass before merge | None — Dependabot PRs go through the same required checks as any PR to `main`. |
| Human review | Every Dependabot PR is read and merged by a maintainer | None. Auto-merge is out of scope for this spec version (map issue #1). |

## Integration Points

| Component | Relationship | Mechanism |
|-----------|---------------|-----------|
| `spec/spec-process-cicd-ci.md` (CI) | Gates Dependabot PRs | `ci.yml` triggers on `pull_request` to `main` |
| `spec/spec-process-cicd-quality.md` (Quality) | Gates Dependabot PRs | `quality.yml` triggers on `pull_request` to `main` |
| `.github/release.yml` | Consumes the `dependencies` label for note categorisation | `gh release create --generate-notes` in `release.yml` |
| Repo "Dependabot security updates" setting | Complementary — this file governs scheduled *version* updates; the setting governs on-demand *security* updates | GitHub repo setting, not this file |

## Validation Criteria

- **VLD-001**: `.github/dependabot.yml` parses (no error banner on the repo's Dependabot tab) and lists
  both a `pip` and a `github-actions` update block, each `directory: "/"`, `interval: weekly`.
- **VLD-002**: The first weekly run (or a manual "Check for updates") produces at most one grouped PR
  per ecosystem for outstanding minor/patch bumps.
- **VLD-003**: Every Dependabot PR carries the `dependencies` label and runs `CI status` + `ruff`.
- **VLD-004**: No auto-merge mechanism exists (no workflow calling `gh pr merge` on Dependabot PRs,
  no `dependabot` auto-merge Action, no branch rule enabling it).
- **VLD-005**: The `dependencies` label exists in the repo independently of Dependabot having run.

## Change Management

### Update Process

1. **Specification Update**: Modify this document first.
2. **Implementation**: Apply to `.github/dependabot.yml`.
3. **Verification**: Confirm the Validation Criteria (use the repo's "Check for updates" button to
   force a run rather than waiting for Monday).
4. **Deployment**: Merge; Dependabot picks up the new config on its next run.

Introducing auto-merge (even patch-only), adding a private `registries` block, or adding an `ignore`
rule are each material changes: update this spec, and for auto-merge also update `main` branch
protection and the decision on map issue #1.

### Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-07 | Initial specification. `.github/dependabot.yml` added: `pip` + `github-actions`, weekly (Monday), minor/patch grouped one-PR-per-ecosystem, majors individual, limit 5, `dependencies` label, `build`/`ci` commit prefixes. No `ignore` (acryl-datahub cap left visible), no auto-merge. `dependencies` label created (`#0366d6`). Pointer added to `spec/spec-process-cicd-ci.md` Dependent Workflows. | David Ouagne |

## Related Specifications

- `spec/spec-process-cicd-ci.md` — CI; gates every Dependabot PR (`CI status` required on `main`).
- `spec/spec-process-cicd-quality.md` — Ruff/mypy; `ruff` required on `main`, also gates Dependabot PRs.
- `spec/spec-process-cicd-release.md` — consumes the `dependencies` label via `.github/release.yml`.
- `spec/spec-process-cicd-codeql.md` — the other GitHub-native (non-workflow-file) process in this repo.
