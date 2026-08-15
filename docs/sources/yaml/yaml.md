# YAML Metadata Source

## Overview

Reads a directory tree of declarative YAML "metadata as code" files and emits the
DataHub entities they describe. This is not a connector for one external system —
it's a generic authoring format, closest in spirit to DataHub's built-in
`datahub-business-glossary` and `datahub-lineage-file` sources, generalized to
most of the DataHub entity model.

Every YAML document declares its own platform, environment, and (where relevant)
platform instance, so a single tree of files can describe entities spanning many
different source systems (e.g. `postgres`, `duckdb`, `dbt`, `s3`) without the
source itself connecting to any of them.

## Capabilities

- Data platforms (registers custom platforms not built into DataHub)
- Tags, glossary terms/nodes (incl. related-term relationships), structured
  property definitions, domains (nestable via `parentDomain`)
- Containers (databases, schemas, ...), with automatic parent/child ordering
- Datasets: schema (columns, types, foreign keys), containers, tags, glossary
  terms, ownership, domains, applications, custom properties
- **Cross-cutting metadata uniformly on every kind that DataHub's entity
  registry permits it for**: `owners`, `tags`, `glossaryTerms`, `domains`,
  `applications`, `links` (institutional memory), `deprecation`,
  `structuredProperties`, `subTypes`. Which of these a given `kind` accepts is
  listed in that kind's own section of [reference.md](reference.md) — an
  unrecognized or not-applicable field is reported as a warning (or a hard
  error under `fail_on_unresolved_reference`), never silently dropped.
- Table-level and column-level lineage (`upstreamLineage`), fully hand-declared
  in the YAML — no SQL parsing is involved
- Column-level metadata: `tags`, `glossaryTerms`, `deprecation`, and
  `structuredProperties` on an individual `schema.fields[]` entry (e.g. tagging
  a single column as PII), emitted on that column's `schemaField` entity
- Data products
- Pipelines (`DataFlow`/`DataJob`) with fine-grained lineage, job-to-job DAG
  edges (`inputDataJobs`), and optional parent containers
- Pipeline run history (`DataProcessInstance`, including incremental run events)
- Data quality assertions (freshness, volume, SQL, field-level, schema, custom)
- A small set of raw DataHub aspects that don't have their own `kind` (dataset
  profiles, usage statistics, operations, assertion/process-instance run events)

## Prerequisites

- A local directory (e.g. a checked-out git repository) containing `*.yml` /
  `*.yaml` files in the format described below. The source only reads from the
  local filesystem — no network access or credentials are required.

## Required Permissions

This source has no connection of its own, so there are no source-system
permissions to configure. The only requirement is that the DataHub ingestion
process has read access to the directory configured in `path`.

## Document Format

Every file may contain multiple YAML documents separated by `---`. Each document
is either:

- an **entity document**, identified by a `kind:` field, or
- a **raw aspect document**, identified by an `aspectName:` field (no `kind`)

### Editor autocomplete and validation (JSON Schema)

A [JSON Schema](schema/yaml-metadata.schema.json) describing every `kind` and
the raw aspect passthrough format is generated directly from the Pydantic
models in `datahub_yaml_source/models.py` (`scripts/generate_json_schema.py`)
— it can't drift from what the connector actually accepts.

To get autocomplete, inline validation, and hover documentation while
authoring `*.yml` files in VS Code (via the
[YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml))
or IntelliJ, add a modeline at the top of the file:

```yaml
# yaml-language-server: $schema=/path/to/datahub-yaml-source/docs/sources/yaml/schema/yaml-metadata.schema.json
kind: DATASET
...
```

(Use a relative path from the YAML file to the schema if both live in the same
repository checkout.)

Regenerate the schema after changing any model in `models.py`:

```bash
python scripts/generate_json_schema.py
```

A test (`test_checked_in_schema_is_up_to_date_with_models`) fails CI if the
checked-in schema and the models have drifted apart.

### Entity kinds

| `kind`                 | DataHub entity                       | Key fields                                                                             |
| ----------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------- |
| `DATA_PLATFORM`         | Data platform                         | `name`, `displayName`, `type`, `logoUrl`, `datasetNameDelimiter`                        |
| `TAG`                   | Tag                                    | `name`, `description`                                                                    |
| `GLOSSARY_NODE`         | Glossary node                          | `id`, `name`, `definition`, `parentNode`                                                 |
| `GLOSSARY_TERM`         | Glossary term                          | `id`, `name`, `definition`, `parentNode`                                                 |
| `STRUCTURED_PROPERTY`   | Structured property definition         | `qualifiedName`, `valueType`, `cardinality`, `allowedValues`, `entityTypes`, `settings`  |
| `DOMAIN`                | Domain                                 | `id`, `name`, `description`                                                              |
| `APPLICATION`           | Application                            | `id`, `name`, `description`                                                              |
| `CONTAINER`             | Container (database/schema/...)        | `platform`, `database`, `schema`, `parentContainer`, `subTypes`, `owners`                |
| `DATASET`               | Dataset (table/view/...)               | `platform`, `name`, `schema` (fields + foreignKeys), `container`, `upstreamLineage`, `viewProperties`, `applications`, ... |
| `DATA_PRODUCT`          | Data product                           | `id`, `name`, `domains`, `assets`, `structuredProperties`                                |
| `DATA_FLOW`             | Pipeline                               | `orchestrator`, `flowId`, `cluster`, `name`                                              |
| `DATA_JOB`              | Pipeline task                          | `jobId`, `dataFlow`, `inputDatasets`, `outputDatasets`, `fineGrainedLineages`             |
| `DATA_PROCESS_INSTANCE` | Pipeline run                           | `id`, `parentTemplate`, `inputs`, `outputs`, `runEvents`                                  |
| `ASSERTION`             | Data quality assertion                 | `id`, `assertion` (discriminated by `assertion.type`: `FRESHNESS` / `VOLUME` / `SQL` / `FIELD` / `DATA_SCHEMA` / `CUSTOM`), `assertionActions` |

### Raw aspect documents

For a handful of aspects that don't map to their own `kind` (mostly time-series
data), use `aspectName:` instead of `kind:`:

| `aspectName`                      | Entity reference field       |
| ---------------------------------- | ----------------------------- |
| `DATASET_PROFILE`                  | `dataset:`                    |
| `DATASET_USAGE_STATISTICS`         | `dataset:`                    |
| `OPERATION`                        | `dataset:`                    |
| `ASSERTION_RUN_EVENT`              | `assertionUrn:` (full URN)    |
| `DATA_PROCESS_INSTANCE_RUN_EVENT`  | `dataProcessInstanceUrn:` (full URN) |

All remaining fields in the document become the aspect's payload.

### View definitions

`viewProperties:` on a `DATASET` records the view's SQL (`viewLogic`, `viewLanguage`,
`materialized`, `formattedViewLogic`). It's usually paired with `subTypes: View`.
No lineage is inferred from `viewLogic` — the connector never parses SQL, so declare
`upstreamLineage:` explicitly if the view has upstream tables.

### Cross-references and dangling references

Fields like `tags:`, `glossaryTerms:`, `domains:`, `applications:`, and
`container:`/`parentContainer:` reference other entities by name/id, which may be
declared in a completely different file. The source loads the entire directory tree
before emitting anything, so these references resolve regardless of file order.

If a reference points at something that was never declared anywhere in the tree
(e.g. a typo in a tag name), the source still emits the association using the
deterministically-computed URN, but reports a warning — set
`fail_on_unresolved_reference: true` to turn that into a hard error instead.

### Unrecognized fields

A field that's either misspelled or not valid for its `kind` (DataHub's entity
registry doesn't permit that aspect on that entity type — e.g. `glossaryTerms:`
on a `TAG`) is also reported as a warning rather than silently ignored, naming
the file, the `kind`, and the field. `fail_on_unresolved_reference: true` turns
this into a hard error too. Check that kind's field table in
[reference.md](reference.md) to see exactly which fields it accepts.

### Container hierarchy ordering

Containers are always emitted with parents before children (required for
DataHub's browse-path generation), regardless of the order they appear in the
YAML files.

### Container URN computation (important)

**A container's URN is a GUID computed from `platform` + `database` + `schema`
only** — it is not derived from `name`. Any two `CONTAINER`/`container:`/
`parentContainer:` blocks with the same values for those three fields resolve
to the exact same URN, regardless of which file declares them, what `name`
each usage gives it, or what they say for `instance`/`env`.

```text
guid_input = {
  "platform": "<platform>",     # raw platform name, NOT a platform URN
  "database": "<database>",     # only if set
  "schema":   "<schema>",       # only if set
  # "instance" and "env" are NEVER part of the hash.
}
guid = md5(json.dumps(guid_input, sort_keys=True, separators=(",", ":")))
urn  = f"urn:li:container:{guid}"
```

This was confirmed against three real container GUIDs from a production
DataHub instance (a database container, its schema container, and a dataset's
`container:` reference to that same schema) — see
`test_container_urn_matches_known_production_guid_*` and
`test_container_urn_ignores_instance_entirely` in `tests/unit/test_urns.py`.

**Neither `instance` nor `env` ever affects the container URN.** `instance`
is only used to set the separate `dataPlatformInstance` *aspect*
(display/filtering) — it is never part of a container's identity. `env`
similarly doesn't distinguish containers across environments (`PROD` vs `DEV`
resolve to the same URN) — this is DataHub's own convention, not a bug:
containers represent structural concepts (a database, a schema) that aren't
duplicated per environment.

⚠️ Getting this exactly right took a few iterations: a description of a
legacy Java/Kotlin pipeline suggested `instance` should be included (wrapped
as a platform URN, or defaulted from `platform` when absent) — both turned
out to contradict real, confirmed production GUIDs once checked. **Always
trust a real, confirmed production GUID over a secondhand description of the
code that (supposedly) produced it**, if the two disagree.

**Practical consequence**: since `instance` and `env` don't matter, a
container is fully identified by `platform` + `database` + `schema` alone —
you're free to set (or omit) `instance`/`env` inconsistently across
`CONTAINER`/`container:`/`parentContainer:` references to the same logical
container without breaking the link.

## Example

See [yaml_recipe.yml](yaml_recipe.yml) for a fully-commented example recipe, and
`tests/integration/yaml_source/resources/` in this repository for a complete
worked example covering every supported `kind`.

For a complete, field-by-field reference of every `kind` (required/optional,
types, defaults), see the generated [reference.md](reference.md).

## Troubleshooting

- **"Unknown kind '...'"** / **"Unsupported raw aspectName '...'"**: the
  document's `kind`/`aspectName` isn't one of the values listed above — check
  for typos.
- **Dangling reference warnings**: a `tags:`/`glossaryTerms:`/`domains:`/
  `container:` value doesn't match any declared `TAG`/`GLOSSARY_TERM`/`DOMAIN`/
  `CONTAINER` document. The association is still emitted; fix the typo or add
  the missing declaration to silence the warning.
- **Container hierarchy looks wrong in the UI**: double-check that
  `parentContainer` on the child matches the parent's own top-level fields
  exactly (`platform`, `instance`, `database`, `env`) — a mismatch (e.g. an
  `instance` set on one but not the other) produces two different container
  URNs instead of a parent/child relationship.
