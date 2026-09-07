---
title: CI/CD Workflow Specification - Code Scanning (CodeQL, default setup)
version: 1.0
date_created: 2026-09-07
last_updated: 2026-09-07
owner: David Ouagne
tags: [process, cicd, github-actions, automation, security, sast, codeql, code-scanning]
---

## Workflow Overview

**Purpose**: Run GitHub's CodeQL static analysis over the repository on every change to `main` and
on a weekly schedule, surfacing security findings in the repo's **Security > Code scanning** tab.
Adapted to a single maintainer: enabled through CodeQL **default setup** (GitHub-managed), so there
is no workflow file to keep in sync and no analysis config to maintain. Findings are advisory — they
do **not** gate merges at this spec version.

**Trigger Events**: Managed by GitHub default setup — push to the default branch (`main`), pull
requests targeting `main`, and a weekly cron. Not configurable per-event without switching to
advanced setup.

**Target Environments**: None. Analysis-only.

> **Status**: Enabled as **default setup** — there is deliberately **no** `.github/workflows/*.yml`
> for this. GitHub runs it as the dynamic workflow `dynamic/github-code-scanning/codeql`, visible
> under Actions as "CodeQL" but with no file in the tree. This document is the design contract for
> that configuration; it is kept in sync with the default-setup settings, not with a YAML file.

## Execution Flow Diagram

```mermaid
graph TD
    A[Trigger: push / PR to main / weekly cron] --> B["CodeQL Setup (GitHub-managed)"]
    B --> C["analyze /language:python"]
    B --> D["analyze /language:actions"]
    C --> E[Results uploaded to Security > Code scanning]
    D --> E

    style A fill:#e1f5fe
    style E fill:#fff3e0
```

## Configuration (authoritative pointers)

The configuration is not in the repo; it lives in GitHub's code-scanning default-setup settings for
`davidouagne/datahub-yaml-source`. This section records the decisions and their rationale. Read the
live values with:

```bash
gh api repos/davidouagne/datahub-yaml-source/code-scanning/default-setup
```

| Setting | Value | Rationale |
|---------|-------|-----------|
| `state` | `configured` | Default setup enabled. |
| `languages` | `python`, `actions` | `python` is the package source. `actions` is included on purpose: this repo's active work is hardening its own GitHub Actions workflows (`ci.yml`, `quality.yml`, `release.yml`), and CodeQL's Actions pack catches workflow script injection, over-broad `permissions`, and unpinned actions at zero extra cost. GitHub auto-detected both. |
| `query_suite` | `default` | Not `extended`. The `default` suite is the high-signal / low-noise set; `extended` adds many lower-severity/experimental queries that are noise for a solo maintainer. Revisit only if the threat model changes. |
| `threat_model` | `remote` | GitHub default — treat only remote (network) input as tainted, not local files/env. Appropriate for a library that parses user-supplied YAML paths but is not a network service. |
| `schedule` | `weekly` | Set by default setup; picks up newly-published CodeQL queries without a code change. |
| `runner_type` | `standard` | GitHub-hosted runner; no self-hosted requirement. |

### Enablement (how this was turned on)

```bash
gh api --method PATCH repos/davidouagne/datahub-yaml-source/code-scanning/default-setup \
  -f state=configured -f query_suite=default \
  -f 'languages[]=python' -f 'languages[]=actions'
```

Requires repo **admin** and a token with the `repo` scope. The PATCH returns a `run_id` for the
initial "CodeQL Setup" run; enablement is complete when that run concludes `success` and
`gh api .../code-scanning/analyses` lists a CodeQL analysis for each language.

## Requirements Matrix

### Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| REQ-001 | CodeQL analysis runs on every change to `main`. | High | A push/PR to `main` triggers the `dynamic/github-code-scanning/codeql` workflow; a fresh analysis appears in `code-scanning/analyses`. |
| REQ-002 | Both Python and workflow files are analysed. | High | `code-scanning/analyses` shows categories `/language:python` and `/language:actions`. |
| REQ-003 | No CodeQL workflow YAML is committed. | High | No file under `.github/workflows/` mentions CodeQL; the repo uses default setup only. |
| REQ-004 | Configuration is documented and re-derivable. | Medium | This spec records every non-default choice; live values readable via the `default-setup` API. |
| REQ-005 | Findings are advisory (do not block merge) at this version. | High | CodeQL is **not** in `main`'s required status checks (see `spec/spec-process-cicd-ci.md` and wayfinder map issue #1, Notes). |
| REQ-006 | Weekly scheduled re-analysis stays enabled. | Low | `schedule` is `weekly` in the `default-setup` response. |

### Security Requirements

| ID | Requirement | Implementation Constraint |
|----|-------------|---------------------------|
| SEC-001 | No custom permissions or secrets to manage. | Default setup's dynamic workflow is GitHub-managed; it needs `security-events: write` to upload results, granted automatically. The repo defines no secret for it. |
| SEC-002 | Analysis config cannot be silently weakened by a PR. | Default setup is changed only through the repo settings / `code-scanning/default-setup` API by an admin, not by editing a tracked file in a PR. |

### Performance Requirements

| ID | Metric | Target | Measurement Method |
|----|-------|--------|---------------------|
| PERF-001 | Added wall-clock on a PR to `main` | Under ~5 minutes for this codebase size | CodeQL run duration in the Actions tab. |
| PERF-002 | Maintenance cost | Zero recurring | No YAML, no pinned CodeQL action versions, no matrix to maintain. |

## Known Baseline (at v1.0)

The first analysis reported **2 open alerts**, both from `/language:python`; `/language:actions`
reported **0**.

| Alert | Rule | Severity | Location | Assessment |
|-------|------|----------|----------|------------|
| #1, #2 | `py/incomplete-url-substring-sanitization` | `warning` (security-severity: high) | `src/datahub_yaml_source/yaml_source_config.py:31` | `_https_clone_url` guards with `repo.startswith("github.com/")` / `repo.startswith("gitlab.com/")` on an already `strip()`/`rstrip("/")`-normalised string. `startswith` is an anchored prefix check, not the unanchored `in` / substring pattern this rule targets — these read as **false positives**. Left **open** and untriaged in the Security tab at this spec version; dismissing or fixing them is out of scope for the ticket that enabled CodeQL (wayfinder map issue #5) and is not tracked as required work. |

This baseline is recorded, not suppressed — consistent with how the mypy baseline is handled in
`spec/spec-process-cicd-quality.md`. There is no CodeQL config to add `paths-ignore` or query filters
(default setup does not support it); narrowing would require switching to advanced setup.

## Error Handling Strategy

| Error Type | Response | Recovery Action |
|------------|----------|------------------|
| CodeQL Setup run fails | Enablement incomplete; Security tab shows no CodeQL analysis | Re-run the setup run; confirm admin rights and `repo` token scope; check GitHub Actions is enabled for the repo. |
| A CodeQL analysis run fails on a PR | Reported in the Actions tab; **not** a required check, so merge is not blocked | Inspect the run log; transient infra failures resolve on re-run. |
| New CodeQL alert appears | Surfaced in Security > Code scanning; no merge gate at this version | Triage in the Security tab: fix, or dismiss with a reason. |

## Quality Gates

| Gate | Criteria | Bypass Conditions |
|------|----------|---------------------|
| Code scanning | CodeQL analysis completes and results upload to the Security tab | Never a merge gate at this spec version. Promoting CodeQL to a required check requires a spec update **and** a branch-protection change on `main` (see `spec/spec-process-cicd-ci.md`, and wayfinder map issue #1 "Not yet specified"). |

## Integration Points

### Dependent Workflows

| Workflow | Relationship | Trigger Mechanism |
|----------|---------------|---------------------|
| Branch protection on `main` | **Not** coupled at this version — CodeQL is intentionally excluded from required status checks (map issue #1, Notes). The branch-protection ticket (map issue #9) requires only `CI status` and `ruff`. | n/a |
| `spec/spec-process-cicd-ci.md` (CI), `spec/spec-process-cicd-quality.md` (Quality) | Siblings; disjoint responsibility. CI owns test/coverage, Quality owns lint/format/types, this owns SAST. Only CI and Quality gate `main`. | Same trigger events (push/PR to `main`) |

## Validation Criteria

- **VLD-001**: `gh api repos/davidouagne/datahub-yaml-source/code-scanning/default-setup` returns
  `state: configured`, `query_suite: default`, `languages` containing `python` and `actions`.
- **VLD-002**: `gh api repos/davidouagne/datahub-yaml-source/code-scanning/analyses` lists a CodeQL
  analysis for both `/language:python` and `/language:actions`.
- **VLD-003**: The repo's **Security > Code scanning** page shows CodeQL as an active tool.
- **VLD-004**: No file under `.github/workflows/` references CodeQL (default setup, not advanced).
- **VLD-005**: `main`'s branch-protection required checks do **not** include a CodeQL check.

## Change Management

### Update Process

1. **Specification Update**: Modify this document first.
2. **Configuration change**: Apply via the repo's Code security settings UI or the
   `code-scanning/default-setup` API (admin only).
3. **Verification**: Re-confirm the Validation Criteria.
4. **Deployment**: Commit the spec change; the configuration change takes effect immediately on save
   (no merge required, since there is no workflow file).

Switching from default to **advanced setup** (custom `codeql.yml`, `paths-ignore`, custom query
packs), enabling the `extended` query suite, or making CodeQL a **required** check on `main` are each
breaking changes: update this spec, and for the required-check case also update `main` branch
protection.

### Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-07 | Initial specification. CodeQL enabled via **default setup** (`state=configured`, `query_suite=default`, `languages=python,actions`, `threat_model=remote`, weekly schedule). No workflow file committed. Advisory only — not a required check on `main`. Recorded baseline: 2 open `py/incomplete-url-substring-sanitization` alerts (both likely false positives on `startswith` prefix guards in `yaml_source_config.py`), 0 from Actions analysis. | David Ouagne |

## Related Specifications

- `spec/spec-process-cicd-ci.md` — CI (install, test, coverage); a required check on `main`.
- `spec/spec-process-cicd-quality.md` — Ruff (blocking) + mypy (advisory); the `ruff` job is a
  required check on `main`. This spec is their SAST sibling; unlike them it gates nothing yet.
- `spec/spec-process-cicd-release.md` — Release pipeline; unrelated trigger surface.
