# Contributing

Thanks for considering a contribution to `datahub-yaml-source`.

## Development setup

Supported Python versions: 3.11, 3.12 (the floor tracked in
`pyproject.toml`'s `requires-python`; 3.10 was dropped in issue #111, since
the dev tooling's security fixes require 3.11). CI
(`.github/workflows/ci.yml`) runs the test suite on both.

This project is managed with [uv](https://docs.astral.sh/uv/). Install it
once, then:

```bash
uv sync --group dev --extra git --extra s3
```

This creates/updates `.venv`, installs the connector in editable mode with
the dev tooling and both optional extras, and registers the `yaml` source
type with `acryl-datahub` via a `datahub.ingestion.source.plugins` entry
point. Verify it's picked up with:

```bash
uv run datahub check plugins
```

## Running the tests

```bash
uv run pytest tests/unit          # unit tests
uv run pytest tests/integration   # integration test against a curated fixture,
                                   # golden-file checked
```

If you intentionally change the connector's output, refresh the integration
golden file and review the diff by hand before committing it:

```bash
uv run pytest tests/integration/yaml_source/test_yaml_source_golden.py --update-golden-files
```

## Regenerating derived docs

`docs/sources/yaml/reference.md` and
`docs/sources/yaml/schema/yaml-metadata.schema.json` are generated from the
Pydantic models in `src/datahub_yaml_source/models.py`. Any change to those
models must be followed by:

```bash
uv run python scripts/generate_json_schema.py
uv run python scripts/generate_markdown_docs.py
```

`tests/unit/test_json_schema_generation.py` and
`tests/unit/test_markdown_docs_generation.py` fail if these artifacts are out
of sync with the models, so this step is not optional.

## Adding a new `kind:` or aspect

A new document kind or a new field typically touches: the Pydantic model in
`models.py`, the relevant builder in `src/datahub_yaml_source/builders/`,
`urns.py` for any new URN helper, `loader.py` / `yaml_source.py` /
`yaml_source_report.py` for a brand-new kind, the regenerated docs above, unit
tests for the model and builder, and an addition to the integration fixture
tree under `tests/integration/yaml_source/resources/` with a refreshed golden
file. If the new kind or aspect needs a newer DataHub server than the
supported range's floor, add its entry to the Minimum server version table in
the same PR (see "Supported DataHub versions" below).

See `_PLANNING.md` for the architecture rationale (why SDK V2 vs. raw MCP per
kind, emission ordering, reference-resolution strategy).

## Supported DataHub versions

A *Supported DataHub version* is a DataHub **server** (GMS) minor this source
is verified against (`CONTEXT.md`, `docs/adr/0007-datahub-version-support-policy.md`).
The range is the `acryl-datahub` requirement in `pyproject.toml`, compared
per minor; it only ever contains verified minors. CI checks the client side
at both ends of that requirement (`test (highest, …)` from the lock,
`test (lowest, 3.11)` with every direct dependency at its floor). The server
side is checked locally, by hand, with the Version check below. It is never
run in CI.

### Version check

```bash
scripts/verify-datahub-version.sh 1.7.0
```

Prerequisites: Docker with about 8 GB of RAM, and ports 8080, 9002, 3306,
9092 and 9200 free. **Stop any other DataHub quickstart first**
(`docker compose -p datahub stop` keeps its data). The script refuses to
start if a server already answers on 8080. On Windows, run it from Git Bash,
not WSL's `bash`.

The script starts the server under a compose project of its own
(`dhys-verify-<version>`, with renamed volumes) and removes it at the end
(`--keep` leaves it running). It then ingests
`tests/integration/yaml_source/resources` through `datahub-rest` in
`mode: SYNC` and reads every emitted aspect back
(`scripts/version_check.py`). Count about ten minutes. Don't run
`datahub docker quickstart --version …` by hand for this: the quickstart
compose hard-codes its volume names (`datahub_*`), so a server of another
version would start on your local instance's data.

It exits 0 only if both of these hold:

- the ingestion report has no failure and no warning, source or sink;
- every aspect read back still contains what was sent. The server may add
  values, never drop or change them. Timeseries aspects are compared by
  their latest value, and a `PATCH` by the state it produces.

The baseline is the run's own emitted MCPs, so there is no reference file
to regenerate. The only tolerated deviations are the skips the Minimum server
version table (`src/datahub_yaml_source/minimum_server_version.py`) predicts
for that server.

### Inspecting a server by hand

```bash
scripts/datahub-local.sh 1.8.0 up            # empty server, UI on :9002
scripts/datahub-local.sh 1.8.0 down          # stop, data kept
scripts/datahub-local.sh 1.8.0 down --purge  # remove, volumes included
```

This uses the same isolation as the Version check, under the compose project
`dhys-local-<version>`, one version at a time. `--project
dhys-verify-<version>` reaches a server left by
`verify-datahub-version.sh --keep`.

### Widening the supported DataHub range

A new server minor (1.8, then 1.9…) enters the range only through a widening
PR, reviewed by hand, that passed the Version check. Patch bumps
(`1.7.0.x → 1.7.0.y`) are not concerned: Dependabot classifies them
`semver-patch`, so they stay auto-merged without a Version check.

1. In the widening PR (opened by Dependabot or by hand), raise the cap to
   the next minor, e.g. `acryl-datahub>=1.7.0.11,<1.9` to admit 1.8, then
   run `uv lock`. The cap is always the last verified minor.
2. Run the Version check against the new server:
   `scripts/verify-datahub-version.sh 1.8.0`.
3. Read the result:
   - **Exit 0**: the server keeps everything this source emits.
   - **Report failure or warning**: the server rejects something. This is
     an incompatibility to fix.
   - **Read-back difference**: the server dropped or changed something it
     was sent. Either adapt the code to the incompatibility you observed, or
     leave the minor out of the range. There is no exception list.
4. Tick "Version check passed on X.Y" in the PR template.

Two kinds of break can come with a widening:

- **Client-side**: the still-experimental `datahub.sdk.*` surface changes.
  The `test (highest, …)` CI legs catch it. Absorb it in the builders.
- **Server-side**: the new server rejects or loses an aspect. Only the
  Version check catches it.

If absorbing a client break forces dropping the old API, the floor rises
past the previous minor, and that minor's servers leave the range. That is a
**breaking change**: mark the commit `!` with a `BREAKING CHANGE:` footer.

The **Minimum server version** table
(`src/datahub_yaml_source/minimum_server_version.py`) changes in the PR that
introduces a kind or aspect needing a newer server than the range floor,
not in a widening PR. A widening PR touches it only if the Version check
shows an existing aspect missing on the new minor. A field is never gated:
it enters once every supported minor keeps it.

## Code style

- No SQL parsing, no live connection: this source's entire job is translating
  declarative YAML into DataHub metadata. Keep new code consistent with that
  scope.
- Prefer DataHub's SDK V2 (`datahub.sdk.*`) where a wrapper exists for the
  entity type; fall back to `MetadataChangeProposalWrapper` otherwise. Never
  use the legacy MCE API.
- A malformed or unresolvable document should produce a warning on the
  ingestion report and be skipped, not crash the whole run, unless
  `fail_on_unresolved_reference` is set.

### Lint, format, and types

Ruff and mypy are installed by the `dev` dependency group. Before pushing,
run the same checks CI runs (the `lint`/`typecheck` jobs in
`.github/workflows/ci.yml`, contract in `spec/spec-process-cicd-ci.md`):

```bash
uv run ruff check .            # lint (blocking in CI)
uv run ruff format --check .   # formatting (blocking in CI); drop --check to apply
uv run mypy                    # type check over src/ (blocking in CI)
```

`ruff check --fix .` auto-fixes most lint findings. `ruff` config
(`[tool.ruff]`, line length 100, target `py311`, `select` includes `ANN`/`PL`
scoped to `src/` via `per-file-ignores`) and `mypy` config (`[tool.mypy]`,
`src/` only, `strict = true`) both live in `pyproject.toml`. The mypy
baseline is zero — `mypy` must exit clean before a PR can merge. Fix a new error
with a real annotation/guard; a `# type: ignore[<code>]` (mypy) or
`# noqa: <code>` (ruff) is a last resort and needs a one-line reason.

## Submitting changes

1. Open an issue or discussion first for anything beyond a small fix, so the
   approach can be agreed before you invest time in it.
2. Keep pull requests focused — one logical change per PR.
3. Make sure `uv run pytest tests/unit tests/integration` passes and that generated
   docs/schema are committed alongside any model change.
4. Describe *why* the change is needed, not just what it does — the commit
   message and PR description should stand on their own.
5. Use a [Conventional Commit](https://www.conventionalcommits.org/) message
   (`type: subject` or `type(scope): subject`, e.g. `fix: handle empty
   containers`) for every commit. `commit-policy.yml` checks each one in CI
   (`commitlint`, a required check on `main`)
   (`spec/spec-process-cicd-commit-policy.md`); `commitlint.config.mjs`
   configures the accepted types: `@commitlint/config-conventional`'s
   standard list (`build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`,
   `refactor`, `revert`, `style`, `test`) plus `deps`, reserved for
   Dependabot's production dependency bumps. The PR title is not checked: it
   never reaches `main`'s history (next point).
6. Keep the branch history clean. `main` only accepts **rebase merge** (no
   merge commit, no squash; linear history required — ADR-0005): every
   branch commit lands on `main` as-is and release-please reads each one to
   compute the version and the changelog. Tidy the branch (interactive
   rebase) before opening the PR so every commit is atomic and its message
   exact, and catch up with `main` by rebasing ("Update with rebase"), not
   by merging `main` into the branch.
7. Sign off every commit (`git commit -s`, or `-S` combined with GPG
   signing) with a `Signed-off-by:` trailer — the `dco` job checks for it
   (a required check on `main`, so a PR with an unsigned commit cannot merge). Uses your `git config user.name`/`user.email`
   automatically.

By contributing, you agree that your contributions will be licensed under the
project's [Apache License 2.0](LICENSE).
