# CI/CD, Security, and Quality: `datahub-healthdcat-ap-exporter` vs `datahub-yaml-source`

> **Note on convention**: this repository had no existing "research notes" location
> (`docs/` only contains `agents/` and `sources/` subfolders). This `docs/research/`
> directory is a new convention introduced for this file — relocate it if a different
> home is preferred.

Research date: 2026-09-14. Both repositories are owned by `davidouagne` and public.
All findings below are traced to a specific file, line/section, or API call — see
[Sources](#sources). Where GitHub content was in French (mainly
`datahub-healthdcat-ap-exporter`), this report translates/paraphrases the substance
in English; direct quotes are marked as French in place.

## Summary

| Axis | `datahub-healthdcat-ap-exporter` | `datahub-yaml-source` |
|---|---|---|
| **CI/CD** | Wider pipeline (lint, strict mypy, tests+coverage, build+smoke test, dependency-review, DCO/commitlint/PR-title checks, release-please + PyPI release automation) — but **`main` has no branch protection at all**, so none of it technically blocks a merge. | Narrower pipeline (tests+coverage, minimal-install check, ruff, mypy, tag-triggered PyPI release) — `main` **does** have branch protection, but the live required checks are only `CI status` + `ruff`; `mypy` is documented as blocking but is **not** actually in the required-checks list. |
| **Security** | Dependabot alerts + secret scanning + push protection all **enabled** at the repo-settings level; weekly `pip-audit` job that opens an issue on findings; `dependency-review-action` blocks high-severity/copyleft-licensed PRs; CodeQL **not configured** (default setup `state: not-configured`). One open Dependabot alert (setuptools, medium). | CodeQL default setup **is** enabled (python + actions) with a documented baseline (2 open, likely-false-positive alerts) — but repo-level secret scanning, push protection, and Dependabot alerts/security-updates are all **disabled**; no `pip-audit`/`safety`/SCA step in CI; no `SECURITY.md`. |
| **Quality** | `mypy --strict` enforced in CI (not just present); ruff with a broader rule set (adds `PL`); Codecov patch-coverage gate (80%) plus project auto-baseline; DCO + Conventional Commits + PR-title linting enforced in CI; PR template with a checklist. No CODEOWNERS in either repo. | ruff + mypy both run in CI with a deliberately narrower ruff rule set and a non-strict mypy config; coverage gate is a local `pytest --cov-fail-under=80`, Codecov is explicitly informational-only; CONTRIBUTING.md is thorough but there's no PR template, no commit-message linting, no DCO check. |

Bottom line: `datahub-healthdcat-ap-exporter` has the more elaborate and more
security-conscious pipeline on paper (and in workflow files), but its `main`
branch is currently **unprotected**, so all of that is advisory in practice.
`datahub-yaml-source` has an actually-enforced branch-protection gate, but that
gate is narrower than its own documentation claims, and several repo-level
security toggles (secret scanning, push protection, Dependabot alerts) are off.

---

## CI/CD

### `datahub-healthdcat-ap-exporter`

- **Workflows** (`.github/workflows/`, listed via `mcp__github__get_file_contents` on `owner=davidouagne repo=datahub-healthdcat-ap-exporter path=/.github/workflows`): `audit.yml`, `ci.yml`, `commit-policy.yml`, `dependabot-auto-merge.yml`, `release.yml`.
- **`ci.yml`** triggers on `push`/`pull_request` to `main` (`.github/workflows/ci.yml` lines 3-6). Jobs:
  - `lint`: `ruff check .`, `ruff format --check .`, plus an **advisory** `pip-audit` step (`continue-on-error: true`) (lines 17-46).
  - `typecheck`: `uv run mypy src/dh_healthdcat` (lines 48-63) — config is `[tool.mypy] strict = true` (`pyproject.toml`, "strict = true" line).
  - `test`: matrix Python 3.10/3.11/3.12, `pytest --cov=dh_healthdcat --cov-report=xml`, then Codecov upload via OIDC (`use_oidc: true`) on the 3.12 leg only, with **`fail_ci_if_error: true`** (lines 65-92) — i.e., unlike the sibling repo, a Codecov upload failure fails this CI job.
  - `build`: builds the wheel, installs it into a fresh venv, runs a CLI smoke test and an "embedded data" smoke test (vocab + SHACL shapes packaging) (lines 94-119).
  - `dependency-review`: runs only on `pull_request`, using `actions/dependency-review-action@v5` with `fail-on-severity: high` and a GPL/AGPL license deny-list (lines 121-133).
- **Test matrix**: Python 3.10, 3.11, 3.12 (`ci.yml` `strategy.matrix.python-version`), OS: `ubuntu-latest` only.
- **Coverage gate**: `codecov.yml` sets `patch: target: 80%` (blocking-looking, not `informational`) and `project: target: auto, threshold: 0%` — i.e. Codecov itself is configured to post a real pass/fail status, not an informational one (contrast with `datahub-yaml-source`'s `codecov.yml`, which explicitly marks both as `informational: true`). However, whether this actually blocks a PR depends on branch protection requiring the Codecov check — see below, branch protection is absent.
- **Release automation** (`.github/workflows/release.yml`): a single mono-workflow using `googleapis/release-please-action@v5` to manage version bumps/changelog from Conventional Commits, then on `release_created`: build sdist/wheel, `twine check`, attach to the GitHub Release, publish to PyPI via OIDC Trusted Publishing (`environment: pypi`, `id-token: write` only, no stored token), then a best-effort (`continue-on-error: true`) post-publish smoke install from PyPI. Also supports a manual `workflow_dispatch` rebuild/republish path for a tag whose automated run failed after tagging (`release.yml` header comment, lines 1-14).
- **Dependabot auto-merge** (`.github/workflows/dependabot-auto-merge.yml`): patch bumps everywhere, and minor bumps for dev-only dependencies, are **auto-merged** via `gh pr merge --auto` once required checks are green (whole file). This is a real difference from `datahub-yaml-source`, which explicitly rejects auto-merge.
- **Commit/PR hygiene as CI gates** (`.github/workflows/commit-policy.yml`): DCO sign-off check on every non-merge commit in a PR, `commitlint` against `commitlint.config.mjs`, and a semantic-PR-title check (`amannn/action-semantic-pull-request@v6`) — all enforced in CI, not just documented.
- **Branch protection on `main`**: `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/branches/main/protection` → **`404 Branch not protected`**. So despite the extensive `ci.yml`/`commit-policy.yml` gate surface, **none of it is enforced by GitHub at merge time** — a repo admin (the sole maintainer) can merge over red checks. Merge strategy is restricted to merge-commit only: `gh api repos/davidouagne/datahub-healthdcat-ap-exporter -q '.allow_squash_merge,.allow_merge_commit,.allow_rebase_merge'` → `false / true / false`, consistent with `CONTRIBUTING.md`'s "no squash, no rebase-merge" rule (CONTRIBUTING.md, "Historique de branche propre" section).

### `datahub-yaml-source`

- **Workflows** (`.github/workflows/`, local read): `ci.yml`, `quality.yml`, `release.yml`.
- **`ci.yml`** triggers on `push`/`pull_request` to `main` plus `workflow_dispatch` (`.github/workflows/ci.yml` lines 7-12). Jobs:
  - `test`: matrix Python 3.10/3.11/3.12, `pytest tests/unit tests/integration --cov=datahub_yaml_source --cov-report=xml --cov-fail-under=80` (lines 34-68) — coverage gate is a hard `pytest` failure, not Codecov. Then uploads to Codecov via OIDC with `fail_ci_if_error: false` and `if: always()` (lines 76-82) — a Codecov outage or fork PR (no OIDC token) never fails the job.
  - `minimal-install-check`: installs the package with no extras and verifies the `yaml` ingestion plugin still registers, and that `boto3`/`git` are not eagerly imported (lines 84-128).
  - `ci-status`: aggregate job (`needs: [test, minimal-install-check]`) whose check-run name (`CI status`, with a space) is what branch protection actually requires (lines 130-143).
- **`quality.yml`**: `ruff check --output-format=github .` + `ruff format --check --diff .` (job `ruff`, documented as the blocking, branch-protection-required check), and `mypy` (job `mypy`, comment says "Blocking (issue #13)... a new type error now fails the build" — `.github/workflows/quality.yml` lines 54-58). **However**, live branch protection (see below) does not actually require the `mypy` context, contradicting this comment and `CONTRIBUTING.md` line 88 ("mypy ... blocking in CI").
- **Test matrix**: Python 3.10, 3.11, 3.12, `ubuntu-latest` only (`ci.yml` matrix; `spec/spec-process-cicd-ci.md` REQ-006 explicitly excludes Windows from the required path because the golden-file test degrades there).
- **Coverage gate**: hard-coded `--cov-fail-under=80` in `ci.yml` (line 68); `codecov.yml` explicitly sets both `project` and `patch` status to `informational: true` (codecov.yml lines 13-20) — Codecov is reporting-only by design here, unlike the exporter repo's blocking-looking `codecov.yml`.
- **Release automation** (`.github/workflows/release.yml`): triggered by pushing a `v*.*.*` tag (not by merges to `main`). Re-runs the full test suite against the tagged commit, builds sdist+wheel, verifies the built artifact filename matches the tag (guards against a dirty tree/`setuptools-scm` local-version leak), `twine check --strict`, publishes to PyPI via OIDC Trusted Publishing gated behind a `pypi` GitHub Environment with a required-reviewer protection rule (comment, lines 83-89), then creates a GitHub Release with `gh release create --generate-notes`.
- **Dependabot**: opens PRs but auto-merge is explicitly rejected by design (`.github/dependabot.yml` header comment, lines 1-5: "No auto-merge: every Dependabot PR is reviewed and merged by hand").
- **Branch protection on `main`**: `gh api repos/davidouagne/datahub-yaml-source/branches/main/protection` → `required_status_checks.contexts = ["CI status", "ruff"]`, `strict: false`, `enforce_admins: false`, no required reviews, no restrictions. **`mypy` is not in the live `contexts` list**, even though `spec/spec-process-cicd-ci.md` §"Branch protection on `main`" (version history 1.6) and `CONTRIBUTING.md` (line 88) both describe `mypy` as a required/blocking check. This is a documentation/reality gap, not a "not accessible" gap — I have the live value from the API.

---

## Security

### `datahub-healthdcat-ap-exporter`

- **Dependabot** (`.github/dependabot.yml`): `uv` and `github-actions` ecosystems, weekly (Monday), `open-pull-requests-limit: 5`, groups (`dev-dependencies` all patterns/dev type; `prod-minor-patch` for production minor/patch), a 3-day `cooldown.default-days`, `assignees: ["davidouagne"]`. Distinctive vs. the sibling repo: **auto-merge is wired up** for patch bumps everywhere and minor bumps for dev-only deps (`.github/workflows/dependabot-auto-merge.yml`, whole file).
- **Repo-level security settings** (`gh api repos/davidouagne/datahub-healthdcat-ap-exporter -q '.security_and_analysis'`): `secret_scanning: enabled`, `secret_scanning_push_protection: enabled`, `secret_scanning_non_provider_patterns: disabled`, `secret_scanning_validity_checks: disabled`, `dependabot_security_updates: disabled`.
- **Dependabot alerts** (basic vulnerability alerts, distinct from the auto-PR "security updates" setting above): **enabled** — `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/vulnerability-alerts` returns HTTP 204 (empty body, exit 0), which per GitHub's API means alerts are on. Confirmed populated: `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/dependabot/alerts` lists **1 open alert** — `setuptools` (transitive, via `uv.lock`), `GHSA-h35f-9h28-mq5c` / `CVE-2026-59890`, severity `medium`.
- **CodeQL / SAST**: **not configured**. `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/code-scanning/default-setup` → `"state": "not-configured"`. No CodeQL workflow file exists either (`.github/workflows` listing above has no CodeQL/`codeql` file). This is a real gap relative to `datahub-yaml-source`.
- **Custom weekly SCA job** (`.github/workflows/audit.yml`): runs `pip-audit` against the locked `uv.lock` every Monday at 06:00 UTC and on `workflow_dispatch`; by design the `audit` job itself only turns red if `pip-audit` fails to run (not merely finds a vulnerability) — a real finding instead opens/dedupes a `dependencies`-labeled GitHub issue via the `open-issue` job (`audit.yml`, header comment and `open-issue` job).
- **PR-time SCA/license gate**: `dependency-review-action@v5` in `ci.yml`'s `dependency-review` job, `fail-on-severity: high`, plus a `deny-licenses` list covering GPL-2.0/3.0 and AGPL-3.0 variants (`ci.yml` lines 121-133) — this is a real blocking-on-paper mechanism for new-dependency vulnerabilities and copyleft licenses on every PR (again, moot without branch protection requiring it — see CI/CD section).
- **`SECURITY.md`**: present (`SECURITY.md`, French). Says the project has no stable version line yet; only `main` and the latest tag are supported; vulnerabilities should be reported via GitHub's private "Report a vulnerability" flow, not a public issue; no contractual response SLA (single maintainer).
- **Secret-scanning alerts**: none currently open — `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/secret-scanning/alerts` returns `[]`.
- **Dependency pinning**: mixed and deliberately tightened in places — most `uses:` actions are pinned to a major-version tag (`@v7`), but the two most sensitive release-time actions are pinned to a **full commit SHA** with the version as a trailing comment: `actions/download-artifact@3e5f45b2c...  # v8.0.1` and `pypa/gh-action-pypi-publish@dc37677b2e1c...  # v1.14.2` (`release.yml`, `publish` job). `rdflib==7.6.0` is pinned to an exact version in `pyproject.toml` (comment explains it must match `acryl-datahub[rdf]`'s own pin); everything else uses `>=`/range bounds. A full resolved lockfile (`uv.lock`, 696 KB) is committed, giving fully reproducible installs — something `datahub-yaml-source` does not have.

### `datahub-yaml-source`

- **Dependabot** (`.github/dependabot.yml`, local read): `pip` and `github-actions` ecosystems, weekly (Monday), `open-pull-requests-limit: 5`, minor/patch grouped per ecosystem, majors individual, labeled `dependencies`. Auto-merge is explicitly **not** configured, by design (header comment, lines 1-5): every Dependabot PR is reviewed and merged by hand.
- **Repo-level security settings** (`gh api repos/davidouagne/datahub-yaml-source -q '.security_and_analysis'`): `secret_scanning: disabled`, `secret_scanning_push_protection: disabled`, `secret_scanning_non_provider_patterns: disabled`, `secret_scanning_validity_checks: disabled`, `dependabot_security_updates: disabled`.
- **Dependabot alerts**: **disabled**. `gh api repos/davidouagne/datahub-yaml-source/dependabot/alerts` → `403 "Dependabot alerts are disabled for this repository."`; `gh api repos/davidouagne/datahub-yaml-source/vulnerability-alerts` → `404 "Vulnerability alerts are disabled."` This means, unlike the exporter repo, there is currently no automated GitHub-native visibility into known-vulnerable dependencies for this repo.
- **CodeQL / SAST**: **enabled** via GitHub default setup (no workflow file by design). `gh api repos/davidouagne/datahub-yaml-source/code-scanning/default-setup` → `{"state":"configured","languages":["actions","python"],"query_suite":"default","threat_model":"remote","schedule":"weekly"}`, matching `spec/spec-process-cicd-codeql.md` exactly. Live alerts confirmed via `gh api repos/davidouagne/datahub-yaml-source/code-scanning/alerts`: **2 open**, both `py/incomplete-url-substring-sanitization` at `security_severity_level: high`, matching the documented baseline in `spec/spec-process-cicd-codeql.md` ("Known Baseline at v1.0", lines 101-112), which assesses them as likely false positives on anchored `str.startswith()` checks in `src/datahub_yaml_source/yaml_source_config.py:31`, left open/untriaged by design. No CodeQL check is in branch protection's required-contexts list (confirmed live, matching spec REQ-005/VLD-005).
- **No SCA tooling in CI**: no `pip-audit`, `safety`, or `dependency-review-action` step anywhere in `ci.yml`/`quality.yml`/`release.yml` (full file reads). `spec/spec-process-cicd-ci.md` "Security Controls" section explicitly states: "Vulnerability Scanning: Not currently in scope for this workflow; ... a candidate future addition, not a current requirement" (lines 233-234).
- **`SECURITY.md`**: **not found**. No such file at the repo root (`ls` of the working directory shown above lists no `SECURITY.md`).
- **Secret-scanning alerts**: not accessible/not applicable — the feature is disabled (see above), so there is nothing to list; `gh api .../secret-scanning/alerts` returns 404 "Secret scanning is disabled on this repository."
- **Dependency pinning**: `setup.py` uses version ranges throughout (`acryl-datahub>=1.7.0.9,<1.8`, `pyyaml>=6.0`, `pydantic>=2.4.0,<3.0.0`, `requests>=2.28.0,<3`, dev extras similarly ranged — `setup.py` lines 63-110), each range's rationale documented inline. GitHub Actions are pinned to major-version tags only (`actions/checkout@v7`, `actions/setup-python@v7`, `codecov/codecov-action@v5`, `pypa/gh-action-pypi-publish@release/v1` — the last is a **branch** ref, not a tag, called out in `spec/spec-process-cicd-dependabot.md` "What Dependabot will not touch" as maintained by hand since Dependabot won't bump a branch ref). There is **no committed lockfile** — installs are reproducible only insofar as the version ranges in `setup.py` stay narrow; CI does key its pip cache off `setup.py` (`cache-dependency-path: setup.py` in `ci.yml`/`quality.yml`) but that is a cache key, not a resolved lock.

---

## Quality

### `datahub-healthdcat-ap-exporter`

- **Linting/formatting**: Ruff, configured in `pyproject.toml` `[tool.ruff]`/`[tool.ruff.lint]`, `select = ["E","F","W","I","UP","B","SIM","C4","RUF","PL"]` — notably includes the `PL` (pylint-style) family that `datahub-yaml-source` deliberately excludes, with two explicit `ignore`s (`PLC0415` for intentional deferred imports, `PLR0913`/`PLR0917` for wide-but-intentional argument lists). Enforced in CI as a real blocking step: `ci.yml` `lint` job runs `ruff check .` and `ruff format --check .` with no `continue-on-error` (only the accompanying `pip-audit` step in that job is advisory).
- **Type-checking**: `mypy --strict` (`pyproject.toml` `[tool.mypy] strict = true`), scoped to `src/dh_healthdcat`, with overrides relaxing `disallow_untyped_defs` for `tests.*` and `ignore_missing_imports`/`implicit_reexport` for a few third-party modules (`datahub.*`, `pyshacl.*`, `rdflib.*`). Run as its own CI job (`typecheck`), no `continue-on-error` — this is strict mode and enforced, a stronger type-checking posture than the sibling repo's non-strict config.
- **Pre-commit hooks**: `.pre-commit-config.yaml` runs `check-yaml`/`end-of-file-fixer`/`trailing-whitespace` plus local `ruff check --fix`/`ruff format` hooks that shell out to `uv run ruff` so the local hook version always matches `uv.lock` (file header comment). `datahub-yaml-source` has no `.pre-commit-config.yaml` at all.
- **Test suite**: `pytest` + `pytest-cov`, 9 test files under `tests/unit/` (`test_cli_push_config.py`, `test_config.py`, `test_mapping_dataset.py`, `test_pipeline.py`, `test_push.py`, `test_push_state.py`, `test_reader_dataproduct.py`, `test_selection.py`, `test_vocabularies.py` — listed via `gh api .../git/trees?recursive=true`), totalling **107** `def test_...` functions (counted directly from each file's fetched content). All fixtures are offline/fake-backed (`CONTRIBUTING.md`, "Lancer les tests" section; `tests/fixtures/fake_datahub.py`, `tests/fixtures/fake_hdh.py`).
- **Coverage**: Codecov `patch` target 80% (`codecov.yml`), status **not** marked informational (contrast with the sibling repo) — see the CI/CD section for the caveat that no branch protection currently enforces this either way.
- **Code review / process gates**: `.github/PULL_REQUEST_TEMPLATE.md` present, with a checklist (DCO sign-off, Conventional Commit format, clean rebased history, `uv run pytest` passing, `docs/mapping.md` updated when field mappings change, SHACL vocabulary values re-verified when `mapping/vocab/*.yml` changes). **No CODEOWNERS file** (`gh api repos/davidouagne/datahub-healthdcat-ap-exporter/contents/.github/CODEOWNERS` and `/CODEOWNERS` both 404). Commit hygiene (DCO + Conventional Commits + semantic PR title) is enforced in CI, not just documented (`.github/workflows/commit-policy.yml`).
- **Static analysis beyond lint/types**: none beyond Ruff's `PL`/`B`/`SIM` rule families and `mypy --strict`; no separate complexity tool (e.g., no `radon`/`xenon` found in `pyproject.toml` dev group).

### `datahub-yaml-source`

- **Linting/formatting**: Ruff, `[tool.ruff]`/`[tool.ruff.lint]` in `pyproject.toml`, `select = ["E","F","I","UP","B","C4","SIM","RUF"]` — deliberately excludes annotation-completeness (`ANN`) and pylint (`PL`) "to keep the signal high" (`pyproject.toml` comment, lines 36-40). Enforced in CI as the repo's one truly-required-and-live gate: `quality.yml` `ruff` job, and it **is** in the live branch-protection `contexts` list (confirmed via API above).
- **Type-checking**: `mypy`, non-strict (`[tool.mypy]` in `pyproject.toml`: `check_untyped_defs`, `warn_unused_ignores`, `warn_redundant_casts` — no `strict = true`), scoped to `src` only (tests/scripts excluded, "until the src/ signal is clean" per comment). CONTRIBUTING.md and the `quality.yml` job comment both describe this as a blocking CI gate ("mypy must exit clean before a PR can merge" — CONTRIBUTING.md line 95), but as noted in the CI/CD section, the live branch-protection `contexts` list does **not** include `mypy` — a real gap between documentation and the current GitHub configuration for this specific repo (the workflow job itself has no `continue-on-error`, so it still fails its own run and shows red on the PR; it just isn't wired into the branch-protection required-checks list yet).
- **Test suite**: `pytest` + `pytest-cov`, 16 files under `tests/unit/` and `tests/integration/` combined, approximately **207** `def test_...` occurrences (local `grep -c` across `tests/unit tests/integration`, counting both module-level and class-method test functions — an approximate figure, not a `pytest --collect-only` count). Includes a golden-file integration test (`tests/integration/yaml_source/`) and drift-detection tests that fail if generated docs/schema go stale relative to `models.py` (`tests/unit/test_json_schema_generation.py`, `test_markdown_docs_generation.py`).
- **Coverage**: local `coverage.xml` in the working tree (a stale local artifact from a prior test run, not necessarily reflective of the current `main` state) shows `line-rate="0.9737"` (97.37%) — well above the enforced `--cov-fail-under=80` CI floor. Codecov itself is explicitly informational (`codecov.yml`), so the number shown on the badge/PR comment does not gate merges; the `pytest --cov-fail-under=80` step in `ci.yml` is the actual gate.
- **Code review / process gates**: **no PR template found** (no `.github/PULL_REQUEST_TEMPLATE.md` or `.github/PULL_REQUEST_TEMPLATE/` locally). **No CODEOWNERS file** either (checked locally and via `gh api .../contents/.github/CODEOWNERS` and `/CODEOWNERS`, both 404). No commit-message linting or DCO enforcement in CI. `required_pull_request_reviews` is explicitly `none` in branch protection ("no second reviewer exists" — `spec/spec-process-cicd-ci.md` line 203, confirmed absent from the live protection payload, which has no `required_pull_request_reviews` key at all).
- **Static analysis beyond lint/types**: none found; no complexity/SCA tool in the `dev` extra of `setup.py`.

---

## Gaps / could not verify

- **`datahub-healthdcat-ap-exporter` — actual Codecov project/patch pass-fail history**: `codecov.yml` configures thresholds, but I did not (and could not, without a Codecov API token) query codecov.io itself for the current pass/fail state of those statuses on recent PRs; only the *configuration* is verified from the file.
- **`datahub-healthdcat-ap-exporter` — CODEOWNERS at other conventional paths**: checked `.github/CODEOWNERS` and `/CODEOWNERS` (both 404 via the GitHub Contents API); did not separately check `docs/CODEOWNERS`, which is a valid third location GitHub supports, though it is a very unusual placement and no evidence in `CONTRIBUTING.md` suggests it's used.
- **Both repos — GitHub code search test counts**: `gh api search/code -f q='def test_ repo:...'` returned `0` for both repos, which looks like a GitHub code-search indexing/eligibility quirk (the Search API frequently under-indexes or excludes small/recently-active repos) rather than a real absence of matches — I did not rely on it and instead counted test functions by fetching/grepping each test file directly. Flagging in case the discrepancy matters for future automation relying on that endpoint.
- **`datahub-yaml-source` — Dependabot "Last checked" / actual weekly-run history**: I verified the config file and that alerts/security-updates are off at the repo-settings level, but did not (and via the token available, likely cannot without the `admin:repo_hook`-gated Insights UI) confirm Dependabot's scheduled-update run history for this specific repo — the `dependabot/alerts` 403 only tells us the *alerts* feature is off, not whether the version-update schedule in `.github/dependabot.yml` is actually running.
- **`admin:repo_hook` scope**: one `gh api` call (`.../dependabot/alerts` on `datahub-yaml-source`) returned a scope hint suggesting `admin:repo_hook` would unlock more, but the actual 403 body ("Dependabot alerts are disabled for this repository") is a definitive, complete answer — the scope hint appears to be generic GitHub API boilerplate on this error type, not evidence of missing access to a different, unretrieved fact.
- **Neither repo — organization-level security policies**: both repos are under a personal account (`davidouagne`), so there is no org-level security policy/rule layer to check separately from the repo-level `security_and_analysis` block already retrieved.
- **`datahub-healthdcat-ap-exporter` — full `docs/` and `shapes/` contents**: I did not exhaustively fetch every file in `docs/` (e.g. `docs/mapping.md`) or `shapes/ehds/`, since they are product/mapping documentation rather than CI/CD, security, or quality-tooling artifacts within this report's scope.

---

## Sources

### Local filesystem (`datahub-yaml-source`, working directory)
- `AGENTS.md`
- `.github/workflows/ci.yml`
- `.github/workflows/quality.yml`
- `.github/workflows/release.yml`
- `.github/dependabot.yml`
- `.github/release.yml`
- `codecov.yml`
- `pyproject.toml`
- `setup.py`
- `CONTRIBUTING.md`
- `spec/spec-process-cicd-ci.md`
- `spec/spec-process-cicd-dependabot.md`
- `spec/spec-process-cicd-codeql.md`
- `coverage.xml` (local artifact, line-rate field)
- Directory listing of the working tree (`find . -maxdepth 3 ...`) — used to confirm absence of `SECURITY.md`, `CODEOWNERS`, PR template, and lockfile at the root
- `grep -rc "^def test_\|^    def test_" tests/unit tests/integration` — approximate test-function count

### GitHub API / MCP tool calls (`datahub-healthdcat-ap-exporter`)
- `mcp__github__get_file_contents owner=davidouagne repo=datahub-healthdcat-ap-exporter path=/` (root listing)
- `mcp__github__get_file_contents ... path=/.github` and `path=/.github/workflows` (listings)
- `mcp__github__get_file_contents ... path=/pyproject.toml`
- `mcp__github__get_file_contents ... path=/.pre-commit-config.yaml`
- `mcp__github__get_file_contents ... path=/SECURITY.md`
- `mcp__github__get_file_contents ... path=/.github/dependabot.yml`
- `mcp__github__get_file_contents ... path=/codecov.yml`
- `mcp__github__get_file_contents ... path=/CONTRIBUTING.md`
- `mcp__github__get_file_contents ... path=/.github/workflows/ci.yml`
- `mcp__github__get_file_contents ... path=/.github/workflows/audit.yml`
- `mcp__github__get_file_contents ... path=/.github/workflows/commit-policy.yml`
- `mcp__github__get_file_contents ... path=/.github/workflows/dependabot-auto-merge.yml`
- `mcp__github__get_file_contents ... path=/.github/workflows/release.yml`
- `mcp__github__get_file_contents ... path=/.github/PULL_REQUEST_TEMPLATE.md`
- `mcp__github__get_file_contents ... path=/README.md`
- `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/branches/main/protection` → 404 "Branch not protected"
- `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/code-scanning/default-setup` → `state: not-configured`
- `gh api repos/davidouagne/datahub-healthdcat-ap-exporter -q '.security_and_analysis, .visibility, ... .allow_squash_merge, .allow_merge_commit, .allow_rebase_merge'`
- `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/dependabot/alerts` → 1 open alert (setuptools)
- `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/vulnerability-alerts` → HTTP 204 (enabled)
- `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/secret-scanning/alerts` → `[]`
- `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/contents/.github/CODEOWNERS` and `/CODEOWNERS` → both 404
- `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/git/trees/<sha>?recursive=true` (tests/ listing)
- `gh api repos/davidouagne/datahub-healthdcat-ap-exporter/contents/tests/unit/<file>.py -q '.content'` (base64-decoded, grepped for `def test_`) for all 9 test files
- `gh api search/code -f q='def test_ repo:davidouagne/datahub-healthdcat-ap-exporter'` → `0` (see Gaps)

### GitHub API (`datahub-yaml-source`, settings not visible locally)
- `gh api repos/davidouagne/datahub-yaml-source/branches/main/protection` → `contexts: ["CI status","ruff"]`, `strict:false`, `enforce_admins:false`
- `gh api repos/davidouagne/datahub-yaml-source/code-scanning/default-setup` → `state: configured`, `languages:[actions,python]`
- `gh api repos/davidouagne/datahub-yaml-source/code-scanning/alerts` → 2 open, `py/incomplete-url-substring-sanitization`, `high`
- `gh api repos/davidouagne/datahub-yaml-source -q '.security_and_analysis, ...'`
- `gh api repos/davidouagne/datahub-yaml-source/dependabot/alerts` → 403 "Dependabot alerts are disabled"
- `gh api repos/davidouagne/datahub-yaml-source/vulnerability-alerts` → 404 "Vulnerability alerts are disabled"
- `gh api repos/davidouagne/datahub-yaml-source/secret-scanning/alerts` → 404 "Secret scanning is disabled"
- `gh api repos/davidouagne/datahub-yaml-source/contents/.github/CODEOWNERS` and `/CODEOWNERS` → both 404
- `gh api search/code -f q='def test_ repo:davidouagne/datahub-yaml-source'` → `0` (see Gaps)
