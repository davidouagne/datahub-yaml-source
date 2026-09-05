# Contributing

Thanks for considering a contribution to `datahub-yaml-source`.

## Development setup

Supported Python versions: 3.10, 3.11, 3.12 (the floor tracked in `setup.py`'s
`python_requires`, matching `acryl-datahub`'s own Python >=3.10 requirement).
CI (`.github/workflows/ci.yml`) runs the test suite on all three.

```bash
pip install -e ".[dev]"
```

This installs the connector in editable mode and registers the `yaml` source
type with `acryl-datahub` via a `datahub.ingestion.source.plugins` entry
point. Verify it's picked up with:

```bash
datahub check plugins
```

## Running the tests

```bash
pytest tests/unit                 # unit tests
pytest tests/integration          # integration test against a curated fixture,
                                   # golden-file checked
```

If you intentionally change the connector's output, refresh the integration
golden file and review the diff by hand before committing it:

```bash
pytest tests/integration/yaml_source/test_yaml_source_golden.py --update-golden-files
```

## Regenerating derived docs

`docs/sources/yaml/reference.md` and
`docs/sources/yaml/schema/yaml-metadata.schema.json` are generated from the
Pydantic models in `src/datahub_yaml_source/models.py`. Any change to those
models must be followed by:

```bash
python scripts/generate_json_schema.py
python scripts/generate_markdown_docs.py
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
file.

See `_PLANNING.md` for the architecture rationale (why SDK V2 vs. raw MCP per
kind, emission ordering, reference-resolution strategy).

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

Ruff and mypy are installed by the `dev` extra. Before pushing, run the same
checks CI runs (`.github/workflows/quality.yml`, contract in
`spec/spec-process-cicd-quality.md`):

```bash
ruff check .            # lint (blocking in CI)
ruff format --check .   # formatting (blocking in CI); drop --check to apply
mypy                    # type check over src/ (advisory in CI, not a gate)
```

`ruff check --fix .` auto-fixes most lint findings. `ruff` config
(`[tool.ruff]`, line length 100, target `py310`) and `mypy` config
(`[tool.mypy]`, `src/` only, non-strict) both live in `pyproject.toml`. mypy
currently has a known non-empty error baseline — see the spec — so a new mypy
error won't fail CI, but don't add to it.

## Submitting changes

1. Open an issue or discussion first for anything beyond a small fix, so the
   approach can be agreed before you invest time in it.
2. Keep pull requests focused — one logical change per PR.
3. Make sure `pytest tests/unit tests/integration` passes and that generated
   docs/schema are committed alongside any model change.
4. Describe *why* the change is needed, not just what it does — the commit
   message and PR description should stand on their own.

By contributing, you agree that your contributions will be licensed under the
project's [Apache License 2.0](LICENSE).
