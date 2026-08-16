# datahub-yaml-source

[![CI](https://github.com/davidouagne/datahub-yaml-source/actions/workflows/ci.yml/badge.svg)](https://github.com/davidouagne/datahub-yaml-source/actions/workflows/ci.yml)

A standalone [DataHub](https://datahubproject.io/) ingestion source plugin that
reads a directory tree of declarative YAML "metadata as code" files and emits
the DataHub entities they describe (platforms, tags, glossary, domains,
containers, datasets with schema/lineage, data products, pipelines, pipeline
run history, and data quality assertions).

See [docs/sources/yaml/yaml.md](docs/sources/yaml/yaml.md) for a narrative
introduction, [docs/sources/yaml/reference.md](docs/sources/yaml/reference.md)
for a generated field-by-field reference of every `kind`, and
[docs/sources/yaml/yaml_recipe.yml](docs/sources/yaml/yaml_recipe.yml) for an
example recipe. See [_PLANNING.md](_PLANNING.md) for the architecture
decisions behind this connector.

A [JSON Schema](docs/sources/yaml/schema/yaml-metadata.schema.json) for the
document format (autocomplete/validation in VS Code, IntelliJ, ...) is also
generated from the Pydantic models -- see the "Editor autocomplete and
validation" section in `yaml.md`.

Both `reference.md` and the JSON Schema are generated from
`src/datahub_yaml_source/models.py`; regenerate them after changing a model:

```bash
python scripts/generate_json_schema.py
python scripts/generate_markdown_docs.py
```

## Installation

```bash
pip install -e .
```

This registers the `yaml` source type with `acryl-datahub` via a
`datahub.ingestion.source.plugins` entry point. Verify it's picked up with:

```bash
datahub check plugins
```

## Usage

```bash
datahub ingest -c docs/sources/yaml/yaml_recipe.yml
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/unit                 # unit tests
pytest tests/integration          # integration test against a curated fixture,
                                   # golden-file checked
```

To regenerate the integration golden file after an intentional output change:

```bash
pytest tests/integration/yaml_source/test_yaml_source_golden.py --update-golden-files
```
