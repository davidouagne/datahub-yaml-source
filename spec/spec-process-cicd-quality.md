---
title: CI/CD Workflow Specification - Code Quality (Ruff + mypy)
version: 1.0
date_created: 2026-09-05
last_updated: 2026-09-05
owner: David Ouagne
tags: [process, cicd, github-actions, automation, python, lint, format, typing, ruff, mypy]
---

## Workflow Overview

**Purpose**: On every push and pull request, enforce a single lint + format standard for all
first-party Python (`src/`, `tests/`, `scripts/`) via Ruff, and surface (without gating) static
type-checking findings from mypy over the package source. Complements `spec/spec-process-cicd-ci.md`,
which owns install/test/coverage; this workflow owns style and typing only.

**Trigger Events**: Push to `main`; pull request targeting `main`; manual dispatch.

**Target Environments**: None (library/plugin package). CI-only.

> **Status**: Implemented at `.github/workflows/quality.yml`. This document is the design contract
> that file must satisfy; changes to either should keep the other in sync, per Change Management below.

## Execution Flow Diagram

```mermaid
graph TD
    A[Trigger: push / PR to main / manual] --> B[ruff: check + format --check]
    A --> C["mypy (advisory, continue-on-error)"]

    style A fill:#e1f5fe
    style B fill:#e8f5e8
    style C fill:#fff3e0
```

## Jobs & Dependencies

| Job Name | Purpose | Blocking? | Dependencies | Execution Context |
|----------|---------|-----------|--------------|-------------------|
| `ruff` | `ruff check` (lint) + `ruff format --check` (format) over the repo. Its job name is the stable required-check string for branch protection on `main`. | Yes | None | Linux runner, Python 3.12 |
| `mypy (advisory)` | Run mypy over `src/` using the `[tool.mypy]` config in `pyproject.toml`. Reports findings in the run log; never fails the workflow (`continue-on-error: true`). | No | None | Linux runner, Python 3.12 |

## Requirements Matrix

### Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| REQ-001 | Lint all first-party Python with Ruff. | High | `ruff check .` exits 0; any violation fails the `ruff` job. |
| REQ-002 | Enforce a single auto-format. | High | `ruff format --check .` reports no file would be reformatted. |
| REQ-003 | Lint/format config is version-controlled and single-source. | High | `[tool.ruff]` lives in `pyproject.toml`; no competing `ruff.toml`/`setup.cfg` lint config exists. |
| REQ-004 | Tool versions match between CI and a local `pip install -e ".[dev]"`. | Medium | `ruff` and `mypy` are pinned in `setup.py`'s `dev` extra; the workflow installs only that extra, no ad-hoc tool install. |
| REQ-005 | Run mypy over the package source and surface its output. | Medium | `mypy` runs against `files = ["src"]`; findings appear in the job log. |
| REQ-006 | mypy never blocks merge (for now). | High | The `mypy` job is `continue-on-error: true`; a non-zero mypy exit does not fail the workflow or any required check. |
| REQ-007 | The blocking check has one stable name for branch protection. | High | The blocking job is named exactly `ruff`; renaming it is a breaking change requiring a branch-protection update (see `spec/spec-process-cicd-ci.md` REQ-007 for the analogous `ci-status`). |

### Security Requirements

| ID | Requirement | Implementation Constraint |
|----|-------------|---------------------------|
| SEC-001 | No more repo access than reading source. | `permissions: contents: read`; no write/packages/deployments scope. |
| SEC-002 | No secrets. | The workflow references no repository or organization secret. |

### Performance Requirements

| ID | Metric | Target | Measurement Method |
|----|-------|--------|---------------------|
| PERF-001 | Wall-clock for the `ruff` job | Under 3 minutes | Checkout to job completion, excluding queue wait. |
| PERF-002 | Superseded runs on the same ref are cancelled | Redundant runs cancelled | `concurrency` group with `cancel-in-progress: true`. |
| PERF-003 | Dependency install reuses cached wheels when `setup.py` is unchanged | Cache hit reported | `actions/setup-python` pip cache keyed on `setup.py`. |

## Input/Output Contracts

### Inputs

```yaml
branches: [main]     # push trigger scope
# Pull requests targeting `main` also trigger, regardless of source branch.
# Environment Variables: none required.
# Secrets: none required.
```

### Outputs

```yaml
ruff_result: status   # pass/fail of lint + format-check; consumed by branch protection
mypy_result: status   # advisory; surfaced in logs, not consumed as a gate
```

## Execution Constraints

- **Timeout**: Each job bounded to 10 minutes.
- **Concurrency**: One in-flight run per ref (`quality-${{ github.workflow }}-${{ github.ref }}`).
- **Runner**: Standard hosted Linux runner. Single Python version (3.12) — lint and format results are
  not Python-version-sensitive at the project's `target-version` (`py310`), so no matrix.
- **Network**: Outbound to the Python package index only, for dependency installation.
- **Permissions**: Read-only `contents` (SEC-001).

## Tooling Configuration (authoritative pointers)

The exact configuration lives in `pyproject.toml`; this section records the decisions and their rationale.

### Ruff

| Setting | Value | Rationale |
|---------|-------|-----------|
| `line-length` | `100` | A deliberate loosening from the 88 default; the pre-existing code sat well above 88 and 100 keeps the one-off reformat from rewrapping nearly every signature. |
| `target-version` | `py310` | Matches `setup.py`'s `python_requires` floor (driven by `acryl-datahub>=1.7.0`). |
| `lint.select` | `E`, `F`, `I`, `UP`, `B`, `C4`, `SIM`, `RUF` | pycodestyle/pyflakes errors, import sorting, pyupgrade, bugbear, comprehensions, simplify, Ruff-native. Deliberately excludes `ANN` (annotation completeness — that is mypy's job, advisory) and `PL` (too opinionated for a solo maintainer). |
| `lint.per-file-ignores` | `__init__.py` → `F401`; `tests/**` → `E501` | Re-export modules use unused imports on purpose; test fixtures embed full DataHub URNs and JSON blobs as string literals that are not meaningfully breakable. The formatter still enforces 100 cols on everything it can reflow. |
| `lint.isort.known-first-party` | `["datahub_yaml_source"]` | Correct first/third-party split in a `src/` layout. |

Two `# noqa: E501` are carried in `src/datahub_yaml_source/models.py`: one on an aligned ASCII
capability matrix in a comment block (reflowing destroys the alignment) and one on a single-line class
docstring whose text is consumed verbatim by `scripts/generate_json_schema.py` (splitting it would
inject `\n` into the emitted JSON Schema).

**Generator coupling**: `scripts/generate_markdown_docs.py` renders the type column of
`docs/sources/yaml/reference.md` from the Pydantic field annotations in `models.py`. Ruff's `UP`
rules rewrote `Optional[X]`/`List[X]` to `X | None`/`list[X]`; `_render_type` was updated to treat
`types.UnionType` identically to `typing.Union` so the generated docs are byte-identical before and
after the reformat. Any future change to the `UP` rule set must be followed by regenerating the
schema + docs (per `AGENTS.md`) and confirming no drift.

### mypy

| Setting | Value | Rationale |
|---------|-------|-----------|
| `files` | `["src"]` | Package source only. `tests/` and `scripts/` are out of scope until the `src/` signal is clean. |
| `python_version` | `"3.10"` | Assume the semantics of the supported floor. |
| `check_untyped_defs` | `true` | Type-check bodies of unannotated functions — most of the value on a codebase with sparse annotations. |
| `warn_unused_ignores`, `warn_redundant_casts` | `true` | Low-noise staleness detectors. |
| overrides: `datahub.*`, `deepdiff.*` | `ignore_missing_imports = true` | `acryl-datahub` ships partial/absent type information; without this the log is dominated by import errors rather than findings about our code. |
| `strict` | *not set* | Advisory job; a strict baseline would be noise, not signal. Tightening toward strict is tracked as fog on the wayfinder map. |

### Known mypy baseline

At v1.0 of this spec, `mypy` reports **31 errors across 11 files** (chiefly `arg-type` mismatches
where our models pass `list[str]` / `str | None` into `acryl-datahub` SDK constructors that expect
`list[str | SomeUrn]` / `str`). This is recorded, not suppressed: the job is advisory precisely so
this baseline is visible and can be driven down before mypy is promoted to blocking. There is no
mypy baseline/ignore file and no `# type: ignore` sweep.

## Error Handling Strategy

| Error Type | Response | Recovery Action |
|------------|----------|------------------|
| Lint violation | Fail the `ruff` job | Run `ruff check --fix .` locally; hand-fix what `--fix` won't. |
| Formatting difference | Fail the `ruff` job | Run `ruff format .` locally and commit. |
| mypy error(s) | Logged; job still succeeds (`continue-on-error`) | Address opportunistically; drives the baseline in this spec down over time. |
| Dependency install failure | Fail the affected job | Investigate resolution against `setup.py`. |

## Quality Gates

| Gate | Criteria | Bypass Conditions |
|------|----------|---------------------|
| Lint | `ruff check .` clean | None; rule-set changes require updating this spec. |
| Format | `ruff format --check .` clean | None. |
| Types | mypy run completes and output is captured | Never a gate at this spec version; promotion requires a spec update. |

## Integration Points

### Dependent Workflows

| Workflow | Relationship | Trigger Mechanism |
|----------|---------------|---------------------|
| Branch protection on `main` | Consumes the `ruff` check as a required status check | GitHub branch protection API (see the branch-protection ticket on wayfinder map issue #1) |
| `spec/spec-process-cicd-ci.md` (CI) | Sibling; disjoint responsibility (install/test/coverage). Both gate `main`. | Same trigger events |

## Validation Criteria

- **VLD-001**: On a branch with a deliberate lint violation, the `ruff` job fails.
- **VLD-002**: On a branch with an unformatted file, the `ruff` job fails with a diff in the log.
- **VLD-003**: On a branch that adds a new mypy error, the workflow still concludes successfully and
  the `mypy (advisory)` job shows the error in its log.
- **VLD-004**: No job in this workflow references a secret.
- **VLD-005**: `pip install -e ".[dev]"` on a clean checkout provides `ruff` and `mypy` at the
  versions the workflow runs.

## Change Management

### Update Process

1. **Specification Update**: Modify this document first.
2. **Review & Approval**: Standard pull-request review.
3. **Implementation**: Apply changes to `.github/workflows/quality.yml` and/or `pyproject.toml` /
   `setup.py`.
4. **Testing**: Confirm the Validation Criteria on a trial PR.
5. **Deployment**: Merge once the trial run conforms.

Renaming the `ruff` job, or promoting `mypy` to blocking, additionally requires updating the branch
protection configuration for `main`.

### Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-05 | Initial specification. Ruff (blocking: `check` + `format --check`) and mypy (advisory, `continue-on-error`) added as `.github/workflows/quality.yml`; `[tool.ruff]` / `[tool.mypy]` introduced in a new `pyproject.toml`; `ruff`/`mypy` pinned in `setup.py`'s `dev` extra. One-off `ruff format` + safe `ruff check --fix` applied across `src/`, `tests/`, `scripts/`. Recorded mypy baseline: 31 errors / 11 files. | David Ouagne |

## Related Specifications

- `spec/spec-process-cicd-ci.md` — CI (install, test, coverage). This workflow is its style/typing sibling; both are required checks on `main` (the `mypy` job excepted).
