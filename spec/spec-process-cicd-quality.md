---
title: CI/CD Workflow Specification - Code Quality (Ruff + mypy) [RETIRED]
version: 1.6
date_created: 2026-09-05
last_updated: 2026-09-15
owner: David Ouagne
tags: [process, cicd, github-actions, automation, python, lint, format, typing, ruff, mypy, retired]
---

## RETIRED — merged into `spec/spec-process-cicd-ci.md`

As of v1.6, this workflow no longer exists as a separate file. `.github/workflows/quality.yml`'s `ruff`
and `mypy` jobs were moved into `.github/workflows/ci.yml`, renamed `lint` and `typecheck` to match the
sibling repo `datahub-healthdcat-ap-exporter`'s own job names — prompted by the maintainer comparing the
two repos' branch-protection settings directly and asking for the same required-check surface in the
same place in both. `main`'s required status checks changed from `["CI status", "ruff", "mypy",
"dependency-review"]` to `["CI status", "dependency-review"]`: `lint`/`typecheck` are no longer
individually required, but still block merge transitively through `CI status`, so this was a
consolidation, not a weakening of the gate.

**All of this spec's substantive content — the Ruff/mypy configuration tables, the mypy-baseline-zero
story (issue #13), and the issue #55 `ANN`/`PL` fix breakdown — was reproduced in
`spec/spec-process-cicd-ci.md`'s "Lint & Type-Check Configuration" section, not lost.** Go there for the
current, accurate version of everything this document used to describe.

This file is kept only so its version history (below) remains a readable audit trail, and so nothing
that ever linked to `spec/spec-process-cicd-quality.md` resolves to a 404. Do not edit this document
going forward except to keep this notice accurate — all future changes to lint/type-check tooling belong
in `spec/spec-process-cicd-ci.md`.

## Version History (preserved for the record)

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-05 | Initial specification. Ruff (blocking: `check` + `format --check`) and mypy (advisory, `continue-on-error`) added as `.github/workflows/quality.yml`; `[tool.ruff]` / `[tool.mypy]` introduced in a new `pyproject.toml`; `ruff`/`mypy` pinned in `setup.py`'s `dev` extra. One-off `ruff format` + safe `ruff check --fix` applied across `src/`, `tests/`, `scripts/`. Recorded mypy baseline: 31 errors / 11 files. | David Ouagne |
| 1.1 | 2026-09-05 | Added `fetch-depth: 0` to both `actions/checkout` steps: `pyproject.toml` gained a `[build-system]` + `[tool.setuptools_scm]` (issue #3), so the editable install now needs full history + tags to resolve a real version. | David Ouagne |
| 1.2 | 2026-09-07 | **mypy promoted to blocking** (issue #13). Baseline driven 31 → 0 with real fixes (no `# type: ignore`, no baseline file); one genuine bug fixed on the way (CUSTOM assertion `field=`). Job renamed `mypy (advisory)` → `mypy`, `continue-on-error` removed. `types-PyYAML` added to the `dev` extra. `mypy` added to `main`'s required status checks alongside `ruff`. | David Ouagne |
| 1.3 | 2026-09-07 | Ruff dev-dependency range widened to `>=0.12,<0.17` (Dependabot #21). Added `extend-exclude = ["*.md"]` to `[tool.ruff]`: 0.16's `ruff format` reformats Python blocks inside Markdown, which would rewrite `_PLANNING.md`'s hand-shaped snippets. No `.py` file changed under 0.16. | David Ouagne |
| 1.4 | 2026-09-14 | Migrated from `pip`/`setup.py` to `uv`/`pyproject.toml` (`datahub-yaml-source`#49): both jobs install via `uv sync --frozen --group dev` and run tools via `uv run`; `ruff`/`mypy` now live in `pyproject.toml`'s `dev` dependency group instead of `setup.py`'s `dev` extra. Version derivation moved from `setuptools-scm` to `hatch-vcs`. `astral-sh/setup-uv`'s cache (keyed on `uv.lock`) replaces the pip cache keyed on `setup.py`. No change to rule sets, mypy config, or blocking status. | David Ouagne |
| 1.5 | 2026-09-15 | Issue #55: `[tool.ruff.lint] select` gained `ANN`/`PL` (scoped to `src/` via `per-file-ignores` on `tests/**`/`scripts/**`); `[tool.mypy]` switched from an individually-set non-strict baseline to `strict = true` (still `files = ["src"]`), plus a `tests.*` override (currently a no-op — `files` already excludes `tests/`) mirroring the sibling repo. All 48 `ruff` + 18 `mypy` violations this surfaced were fixed directly in `src/` — real annotations/refactors in every case except a handful of individually-justified `# noqa`/`# type: ignore` comments for genuinely dynamic values, this connector's existing lazy-import architecture, and one third-party invariant-`Generic` false positive. Neither addition changed required-check names (REQ-007) or job structure. A code-review pass (still pre-merge) caught two more issues: `pyproject.toml`'s `requests` dependency comment still claimed a lazy import this same change removed (corrected); and a `builders/container.py` `assert dpi is not None` relied on `ContainerRef.platform` being non-empty, which pydantic's plain `str` doesn't actually enforce — replaced with `if dpi is not None:`. A second code-review pass caught that `mcp_workunit`'s new `_Aspect` type hint (`builders/common.py`) was imported from the private `datahub._codegen.aspect` module instead of the public `datahub.metadata.schema_classes` re-export every other DataHub-facing import in this codebase uses for the same symbol — switched to the public path. A third code-review pass flagged the two remaining `assert ... is not None` narrowings as silently compiled away under `python -O`: both converted to the `if x is None: raise AssertionError(...)` form. | David Ouagne |
| 1.6 | 2026-09-15 | **Retired.** `.github/workflows/quality.yml` deleted; its `ruff`/`mypy` jobs merged into `.github/workflows/ci.yml` as `lint`/`typecheck`, prompted by the maintainer comparing this repo's required-check surface against the sibling repo directly and asking for parity. Full content migrated to `spec/spec-process-cicd-ci.md`'s new "Lint & Type-Check Configuration" section (verbatim, job-name references updated). This document reduced to a redirect stub; see `spec/spec-process-cicd-ci.md` for everything going forward. | David Ouagne |

## Related Specifications

- `spec/spec-process-cicd-ci.md` — the current, authoritative home for everything this document used to
  describe.
