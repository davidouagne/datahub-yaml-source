<!--
SOURCE OF TRUTH: this copy, in datahub-yaml-source, is authoritative.
The sibling repo datahub-healthdcat-ap-exporter carries an identical copy
that points back here (tracked in that repo's issue #65) -- kept in sync
by hand, not by automation (issue #48's Out of Scope).
-->

# CI/CD, Security, and Quality Standard

What "good" looks like for a repository maintained by this single maintainer, David Ouagne. Written
to describe the state that **actually exists** in this repo as of the date below -- every claim here
was checked against live repo settings (branch protection, security settings, GitHub Environments,
workflow files) rather than copied from a design spec, so it can't have drifted from what a design
document *intended*. For the detailed *why* behind any individual decision, follow the `spec/
spec-process-cicd-*.md` and `docs/adr/*.md` links inline -- this document is the map, not the
territory.

**Verified against live state on**: 2026-09-15, against `davidouagne/datahub-yaml-source` at commit
`f09383e` (main); §1/§2.1/§2.3/§2.4/§3.4 amended the same day, twice, after re-verification triggered by
direct repo-to-repo comparisons (`dependency-review` promoted to required; `ruff`/`mypy` merged into `CI
status` as `lint`/`typecheck`; `dco` added — see those sections). **Originating
epic**: issue #48 (tickets #49-#58); this document is the final ticket, #59, deliberately written last
so it describes the finished state rather than a moving target.

## 1. Governance

- **No required PR review, no `CODEOWNERS`.** `main`'s branch protection has no
  `required_pull_request_reviews` block at all (confirmed live:
  `gh api repos/.../branches/main/protection` -- the key is simply absent). No `CODEOWNERS` file exists
  in the repo. This is a deliberate decision, not an oversight: with a single maintainer, a review
  requirement would be self-blocking. Revisit if a second maintainer joins.
- **`enforce_admins` is `false`.** The maintainer keeps a direct-push escape hatch on `main` to avoid
  locking themselves out. Required status checks (below) still apply to any PR; this only affects
  whether the maintainer personally can bypass them via direct push.
- **DCO sign-off is checked, advisory-only.** A `dco` job (`commit-policy.yml`) verifies every
  non-merge PR commit carries a `Signed-off-by` trailer, matching the sibling repo's own `dco` job
  (`ADR-0002`-driven there). **Reversed from this document's original text**, which recorded DCO as
  "intentionally absent" per issue #48's scoping -- the maintainer revisited that decision after
  comparing this repo's checks against the sibling directly and asked for parity; see
  `spec/spec-process-cicd-commit-policy.md` v1.1 for the full reasoning. Not a required status check
  (Dependabot's own commits never carry the trailer and would always fail it). Conventional Commit
  enforcement (below) is a separate mechanism and *is* enforced (also advisory, not yet required).
- **`allow_auto_merge`** is `true` at the repo-settings level (required for Dependabot auto-merge,
  below, to function at all -- see `spec/spec-process-cicd-dependabot-auto-merge.md`).

## 2. CI/CD

### 2.1 Continuous Integration + Quality (`ci.yml`)

Triggers on push/PR to `main` and `workflow_dispatch`. One workflow file, four jobs feeding a single
aggregate gate named exactly `CI status` (the branch-protection context string):

- **`lint`**: `ruff check` + `ruff format --check`. Lint rule set: `E, F, I, UP, B, C4, SIM, RUF, ANN,
  PL` (`pyproject.toml` `[tool.ruff.lint] select`) -- `ANN`/`PL` scoped to `src/` only via
  `per-file-ignores` (tests/scripts are exempt from annotation-completeness and pylint-style rules;
  adopted issue #55).
- **`typecheck`**: `mypy`, `strict = true`, scoped to `src/` only (`pyproject.toml` `[tool.mypy] files =
  ["src"]`). The baseline was driven to **zero** when strict mode was adopted (issue #55) -- there is no
  grandfathered ignore list; every new type error fails the build.
- **`test`**: full unit + integration test suite across Python 3.10-3.12, enforces a coverage floor
  (`--cov-fail-under=80`).
- **`build`**: verifies a base-only (no optional-extras) install still registers the `yaml` DataHub
  ingestion source plugin.

**`lint`/`typecheck` used to be `ruff`/`mypy` in a separate `quality.yml` workflow, each individually
required on `main`.** Merged into this file and renamed to match the sibling repo's own job names, and
folded into the `CI status` aggregate instead of being separately required -- the maintainer asked for
this after comparing the two repos' required-check lists directly and finding they diverged for no
principled reason. Functionally identical: nothing that used to block merge stops blocking, since
`ci-status` still fails if either fails. `spec/spec-process-cicd-quality.md` is now a retired redirect
stub; its full tooling rationale lives in `spec/spec-process-cicd-ci.md`'s "Lint & Type-Check
Configuration" section.

Full contract: `spec/spec-process-cicd-ci.md`.

### 2.2 Coverage reporting (Codecov)

Codecov uploads from every `test` matrix leg, but is **informational only** -- `codecov.yml` sets both
`project` and `patch` statuses to `informational: true`. It never posts a blocking check; the actual
coverage gate is `ci.yml`'s own `--cov-fail-under=80`. Full contract: `spec/spec-process-cicd-codecov.md`.

### 2.3 Branch protection on `main` (live-verified)

```
required_status_checks.contexts = ["CI status", "dependency-review"]
required_status_checks.strict   = false
required_pull_request_reviews   = (absent -- none configured)
enforce_admins                  = false
restrictions                    = (absent -- none configured)
```

Two required checks, deliberately matching the sibling repo's own required-check list exactly. CodeQL
(§3.3) is **not** in this list -- advisory at this standard's current version, by deliberate choice
recorded in its own spec, not an oversight. This list changed twice since this document first published:
`dependency-review` was promoted from advisory (its original "matches the sibling's advisory posture"
justification went stale once the sibling's own `main` was separately protected, its companion ticket
`#65`); then `ruff`/`mypy` were folded into `CI status` (renamed `lint`/`typecheck`, `spec/
spec-process-cicd-ci.md` v1.12) and dropped from this list individually -- both changes triggered by the
maintainer comparing the two repos' live settings directly, a concrete instance of the discipline §3.3
and the closing section of this document both call for. `strict: false` means a PR does not need to be
rebased onto the latest `main` before merging -- accepted friction trade-off for a solo maintainer (see
`spec/spec-process-cicd-ci.md`'s Branch Protection section for the full rationale and residual-risk
discussion).

### 2.4 Commit and PR-title discipline (`commit-policy.yml`)

`commitlint` (via `@commitlint/config-conventional`) checks every commit message on a PR is a valid
Conventional Commit; `amannn/action-semantic-pull-request` checks the PR title itself is one too; `dco`
(§1) checks every commit carries a `Signed-off-by` trailer. All three advisory, not required status
checks. `commitlint`/`pr-title` exist specifically because release-please (§2.5) parses commit messages
to compute version bumps and changelog entries -- a malformed commit message is no longer just a style
nit, it would silently mis-compute a release. Full contract: `spec/spec-process-cicd-commit-policy.md`.

### 2.5 Release automation (`release.yml` + `release-please`)

Releases (version bump, changelog, PyPI publish) happen through a `release-please`-maintained release
PR, never a manually pushed tag (ADR-0001, issue #58). Mono-workflow, triggered by `push: branches:
[main]` (not a tag push -- a tag release-please's own token creates cannot trigger a separate
tag-triggered workflow) plus a `workflow_dispatch(publish_tag)` recovery path for a release whose
automated run failed after the tag was already created.

- `release-type: "simple"` (not `"python"`): this repo's `pyproject.toml` has no static `version` field
  for a `python`-type strategy to bump -- `hatch-vcs` derives the version from the git tag at build
  time, so release-please never touches `pyproject.toml`/`uv.lock` at all.
- Publish to PyPI via OIDC Trusted Publishing -- no stored API token. The `pypi` GitHub Environment
  gates the publish step behind a required-reviewer approval (the maintainer approves their own
  release) and restricts deployments to the `main` branch (live-verified:
  `deployment_branch_policies` lists exactly one policy, `{name: "main", type: "branch"}`).
- A `smoke` job (advisory, `continue-on-error: true`) installs the just-published version from PyPI
  and confirms the `yaml` plugin registers, automating what was previously only a manual check.

Full contract: `spec/spec-process-cicd-release.md`.

### 2.6 Dependency updates (`dependabot.yml` + `dependabot-auto-merge.yml`)

Dependabot watches two ecosystems (`uv`, `github-actions`), weekly (Monday), grouping all minor+patch
bumps per ecosystem into one PR each; major bumps arrive individually. Patch-level bumps (any
dependency) and minor-level bumps to dev-only dependencies **auto-merge** once required checks pass
(ADR-0003, issue #51); majors and minor bumps to production dependencies always wait for the maintainer.
Full contract: `spec/spec-process-cicd-dependabot.md` + `spec/spec-process-cicd-dependabot-auto-merge.md`.

## 3. Security

### 3.1 Repo-level GitHub security settings (live-verified)

| Setting | Status |
|---|---|
| Secret scanning | `enabled` |
| Secret scanning push protection | `enabled` |
| Secret scanning non-provider patterns | `disabled` |
| Secret scanning validity checks | `disabled` |
| Dependabot alerts (`vulnerability-alerts`) | `enabled` (HTTP 204 on the check endpoint) |
| Dependabot automated security-fix PRs (`automated-security-fixes`) | `disabled` |

Dependabot **alerts** (visibility into known vulnerabilities in the Security tab) and Dependabot
**security updates** (automatic on-demand PRs fixing them) are two independent GitHub settings --
issue #53 enabled the former; the latter remains off, matching what was actually asked for and not
conflating the two. Scheduled version updates (§2.6) and the weekly `pip-audit` scan (§3.2) already give
this repo two independent vulnerability-discovery paths without also needing on-demand auto-PRs.

### 3.2 Scheduled SCA scan (`audit.yml`, `pip-audit`)

Weekly (Monday) + `workflow_dispatch`, runs `pip-audit` against the committed, locked `uv.lock`. The job
only turns red if `pip-audit` itself fails to execute -- a real finding opens (or dedupes into) a
`dependencies`-labeled GitHub issue instead of failing CI. Full contract: `spec/spec-process-cicd-audit.md`.

### 3.3 Static analysis (CodeQL, default setup)

Enabled via GitHub's **default setup** (no workflow file in the repo -- configuration lives in GitHub's
own code-scanning settings, not a committed YAML file). Live-verified state:

```
state: configured
languages: actions, javascript, javascript-typescript, python, typescript
query_suite: default
threat_model: remote
schedule: weekly
```

**Note on languages**: this repo contains no JavaScript or TypeScript source (`git ls-files` matching
`*.js`/`*.ts`/`*.jsx`/`*.tsx` returns nothing) -- the `javascript`/`javascript-typescript`/`typescript`
entries reflect GitHub's own default-setup language auto-detection/analyzer bundling for repos with
GitHub Actions workflows, not actual JS/TS code in this repo. Recorded here because the spec this
standard was originally drafted against (`spec/spec-process-cicd-codeql.md` v1.0) documented only
`python, actions` -- this is exactly the kind of drift issue #59 exists to catch and correct rather than
silently re-assert. `spec/spec-process-cicd-codeql.md` should be refreshed to match on its own next
touch; not done as part of this document, which only records what's true, not re-derives every
consuming spec.

**Accepted baseline -- two open alerts, deliberately left untouched:**

| Rule | Severity | Location |
|---|---|---|
| `py/incomplete-url-substring-sanitization` | `high` | `src/datahub_yaml_source/yaml_source_config.py:32` (×2) |

Both are `_https_clone_url`'s `repo.startswith("github.com/")` / `.startswith("gitlab.com/")` guards on
an already-normalised (`strip()`/`rstrip("/")`) string -- `startswith` is an anchored prefix check, not
the unanchored substring pattern this rule targets, so these read as false positives. Documented and
left open rather than dismissed or fixed, per the original scoping decision (`spec/
spec-process-cicd-codeql.md` v1.0's Known Baseline, reaffirmed unchanged by issue #48's own Out of
Scope). CodeQL is advisory only (§2.3) -- these alerts do not block anything.

### 3.4 PR-time dependency review (`dependency-review.yml`)

Runs on every PR to `main`: `actions/dependency-review-action@v5`, `fail-on-severity: high`, and a
`deny-licenses` list covering `GPL-2.0`/`GPL-3.0`/`AGPL-3.0` (both `-only` and `-or-later` SPDX forms) --
appropriate for this repo's own Apache-2.0 license. **A required `main` status check** (promoted from
advisory shortly after this standard first published -- see §2.3 for why: the original "advisory,
matching the sibling" framing went stale once the sibling's own branch protection changed independently,
caught by direct repo-to-repo comparison rather than by re-reading this document).

**Known, verified limitation**: `deny-licenses` reliably denies a dependency whose GitHub-reported
license is a single SPDX identifier or an `OR`-expression containing one. It does **not** reliably deny
one whose license GitHub resolves to an `AND`-combined expression -- confirmed empirically against three
different real GPL-licensed PyPI packages during verification, all of which came back as `AND`-expressions
and were not denied, and confirmed by running the action's own matching logic offline. Upstream tool
behavior (the option itself is marked deprecated upstream), not a misconfiguration here. Full detail,
including the exact reproduction: `spec/spec-process-cicd-dependency-review.md`'s "Edge Cases & Known
Limitations" section.

### 3.5 Vulnerability disclosure (`SECURITY.md`)

Private GitHub "Report a vulnerability" flow only -- no public issue for a suspected vulnerability. No
contractual response SLA (single maintainer). No stable version line yet; only `main` and the latest
published tag are supported.

## 4. Pull request process

- `.github/PULL_REQUEST_TEMPLATE.md` -- a checklist covering Conventional Commit compliance, the test
  suite, the `models.py` → docs/schema regeneration trap (`AGENTS.md`'s "one rule that bites silently"),
  golden-file refresh when output intentionally changes, and lint/format/type cleanliness.
- No required review, no `CODEOWNERS` (§1).
- Every PR is gated by `CI status` (which since v1.12 includes `lint`/`typecheck`) and
  `dependency-review` (both required), and, advisory only, CodeQL and `dco`/`commitlint`/`pr-title`
  (§2.3, §2.4, §3.3).

## 5. Package publishing

- **PyPI Trusted Publishing (OIDC)** -- no API token stored as a secret anywhere in this repo. Trusted
  Publisher registered against this exact repo, workflow filename (`release.yml`), and environment name
  (`pypi`); unchanged by the release-please migration (§2.5) even though the workflow's *trigger* changed.
- **Human gate**: the `pypi` Environment's required-reviewer rule (the maintainer approves their own
  publish) sits immediately before the one irreversible step.
- **Build reproducibility**: `hatch-vcs` derives the published version purely from the git tag at build
  time (no static version string anywhere to drift out of sync).

## Related documents

- `spec/spec-process-cicd-ci.md`, `spec/spec-process-cicd-quality.md`, `spec/spec-process-cicd-codecov.md`
- `spec/spec-process-cicd-commit-policy.md`, `spec/spec-process-cicd-release.md`
- `spec/spec-process-cicd-dependabot.md`, `spec/spec-process-cicd-dependabot-auto-merge.md`
- `spec/spec-process-cicd-audit.md`, `spec/spec-process-cicd-dependency-review.md`, `spec/spec-process-cicd-codeql.md`
- `docs/adr/0001-release-please-for-release-automation.md`, `docs/adr/0002-migrate-to-uv.md`,
  `docs/adr/0003-dependabot-auto-merge-policy.md`
- `SECURITY.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `CONTRIBUTING.md`, `AGENTS.md`

## Keeping this document accurate

This is a snapshot, not a live view -- re-verify against actual repo/GitHub settings (not against the
`spec/*.md` files, which describe *intent* and can themselves drift) before trusting a specific claim
here for anything security-sensitive, the same discipline this document's own issue (#59) was written
under. §3.3's language-list note is a concrete example of a detail this approach caught that a
spec-only reading would have missed.
