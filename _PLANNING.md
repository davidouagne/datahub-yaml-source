# YAML Metadata Source Connector - Planning Document

**Created**: 2026-07-13
**Status**: IMPLEMENTED

## Overview

A standalone DataHub ingestion source plugin that reads a directory tree of declarative
YAML files ("metadata as code") and emits the full range of DataHub entities they
describe: data platforms, tags, glossary terms, structured properties, domains,
containers, datasets (with schema/FK/lineage), data products, pipelines (DataFlow/
DataJob with fine-grained lineage), pipeline run history (DataProcessInstance),
data quality assertions, and raw time-series aspects (e.g. dataset profiles).

This is **not** a source for one external system — it's a generic "authoring format"
source, closest in spirit to DataHub's built-in `datahub-business-glossary` and
`datahub-lineage-file` sources, but generalized to (almost) the entire DataHub entity
model. The format already exists and was reverse-engineered from a real example repo
at `C:\Users\4087446\Projects\aphp\datahub-sample` (AP-HP health-data-platform metadata).

No SQL connection and no external API are involved — the source purely parses local
files, so it does not fit the `sql` / `api` / `nosql` categories in the standard
skill classification. Architecturally it is closest to an **API-style source**
(`StatefulIngestionSourceBase`), just with a filesystem "client" instead of an HTTP
client.

## Research Summary

### Source Classification

- **Type**: Other (declarative file-based / metadata-as-code)
- **Interface**: Local filesystem, multi-document YAML (`---`-separated)
- **Standards File**: `standards/patterns.md`, `standards/api.md` (closest architecture), `standards/containers.md`, `standards/lineage.md` (partially — see note below)
- **Reference format**: `C:\Users\4087446\Projects\aphp\datahub-sample` (8 `assets.yml` files across layered directories: `setup/`, `raw-layer/`, `semantic-layer/`, `transform-layer/`, `sharing-layer/`, `quality-layer/`, `dataproduct-layer/`, `observability-layer/`)

**Key simplification vs. a typical connector**: lineage is **fully hand-declared** in
the YAML (`upstreamLineage`, `fineGrainedLineages`, `dataJobInputOutput`). There is no
SQL to parse and no `SqlParsingAggregator` needed — we just translate the declared
references into `UpstreamLineageClass` / `FineGrainedLineageClass` directly.

### Similar DataHub Connectors

| Connector                  | Relevance | Key Patterns                                                                 |
| --------------------------- | --------- | ----------------------------------------------------------------------------- |
| `datahub-business-glossary` | High      | YAML file → GlossaryTerm/GlossaryNode entities, no live connection           |
| `datahub-lineage-file`      | High      | YAML file → lineage edges onto existing URNs, no live connection            |
| `file` (generic MCE/MCP)    | Medium    | Reads raw metadata files; shows the "no platform of its own" emitter pattern |
| Any API source (`api.md`)   | Medium    | `StatefulIngestionSourceBase`, config/report/source file split, stateful removal |

## Entity Mapping

This source covers **13 entity "kinds"** (discriminated by a `kind:` field on every
YAML document) plus a separate **raw-aspect passthrough** format (discriminated by an
`aspectName:` field, used today only for `DATASET_PROFILE`).

| `kind:` value        | DataHub Entity                    | Notes                                                                                   |
| -------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------- |
| `DATA_PLATFORM`       | `dataPlatformInfo` on `dataPlatform` | Registers custom platforms (e.g. `pathling`) not in DataHub's core enum                |
| `TAG`                 | `Tag` (SDK V2)                     | name + description                                                                       |
| `GLOSSARY_NODE`       | `GlossaryNode`                     | id, name, definition                                                                      |
| `GLOSSARY_TERM`       | `GlossaryTerm`                     | id, name, definition, optional `parentNode`                                              |
| `STRUCTURED_PROPERTY` | `StructuredPropertyDefinition`     | qualifiedName, cardinality, valueType, allowedValues, `entityTypes`, `settings`, `typeQualifier` |
| `DOMAIN`              | `Domain`                           | id, name, description                                                                    |
| `CONTAINER`           | `Container` (via `gen_containers()`) | platform/instance/database/(schema), `parentContainer`, `subTypes`, `owners`, `tags`   |
| `DATASET`             | `Dataset` (SDK V2)                 | schema fields (+ `foreignKeys`), `container`, `properties`, `subTypes`, `tags`, `glossaryTerms`, `owners`, `domains`, `upstreamLineage` |
| `DATA_PRODUCT`        | `DataProduct`                      | description, `domains`, `glossaryTerms`, `tags`, `owners`, `structuredProperties`, `assets` (raw URNs) |
| `DATA_FLOW`           | `DataFlow` (SDK V2)                | orchestrator/flowId/cluster, `project`, `externalUrl`, `domains`, `owners`               |
| `DATA_JOB`            | `DataJob` (SDK V2)                 | jobId + `dataFlow` ref, `inputDatasets`/`outputDatasets`, `fineGrainedLineages`           |
| `DATA_PROCESS_INSTANCE` | `DataProcessInstance`             | `parentTemplate` (DataJob ref), `inputs`/`outputs`, `runEvents` (status/timestamp/attempt) |
| `ASSERTION`           | `Assertion`                       | discriminated `assertion.type`: `FRESHNESS` / `SQL` / `FIELD`                             |

| Raw aspect doc                       | DataHub Entity | Notes                                                                 |
| -------------------------------------- | -------------- | ------------------------------------------------------------------- |
| `aspectName: DATASET_PROFILE`          | `Dataset`      | `dataset: {platform,name,env}` + full `DatasetProfile` aspect payload (time-series) |

### URN / Reference Resolution

Every kind can reference entities defined in a **different file**, so the source must
do a **two-pass** load:

1. **Parse pass** — walk the configured root directory, read every `*.yml`/`*.yaml`
   file as a multi-document YAML stream, and validate each document against a
   discriminated Pydantic model keyed on `kind` (or `aspectName`). Collect everything
   into one in-memory `ParsedRepository` (lists per kind, keyed by natural id where
   relevant: tag name, glossary term/node id, domain id, container key tuple, dataset
   platform+name+env, data flow orchestrator+flowId+cluster, data job flow+jobId).
2. **Emit pass** — emit workunits in a **fixed topological order** so parents always
   precede children (`containers.md` requirement):
   `DATA_PLATFORM → TAG → GLOSSARY_NODE → GLOSSARY_TERM → STRUCTURED_PROPERTY → DOMAIN
   → CONTAINER (topologically sorted by parentContainer) → DATASET → DATA_PRODUCT →
   DATA_FLOW → DATA_JOB → DATA_PROCESS_INSTANCE → ASSERTION → raw-aspect docs`.

References to other entities inside a document (e.g. `container:`, `parentContainer:`,
`tags:`, `glossaryTerms:`, `domains:`, `dataFlow:`) are structural — they carry enough
fields (platform/database/schema/env, or a natural id/name) to build the target URN
deterministically without needing the target to have been emitted yet. Unresolvable
references (e.g. a `domains: "xyz"` id that was never declared as a `DOMAIN` document)
are **soft errors**: report a warning and skip only that reference, never fail the
whole file.

## Architecture Decisions

### Base Class Selection

**Chosen**: `StatefulIngestionSourceBase` + `TestableSource` (the `api.md` pattern).

**Rationale**: There is no SQL/JDBC interface and no SQLAlchemy dialect, so the SQL
base classes don't apply. The "client" is a local directory walker instead of an HTTP
client, but the shape of the problem (config → discover items → build typed models →
emit workunits → support stateful stale-entity removal) is identical to an API source.

### Package Layout (standalone plugin, this repo)

```
datahub-yaml-source/
├── setup.py                                  # own entry point + deps (pyyaml, acryl-datahub)
├── src/
│   └── datahub_yaml_source/
│       ├── __init__.py                       # exports YamlSource
│       ├── yaml_source.py                    # main Source class, get_workunits_internal()
│       ├── yaml_source_config.py             # YamlSourceConfig (REQUIRED separate file)
│       ├── yaml_source_report.py             # YamlSourceReport (REQUIRED separate file)
│       ├── models.py                         # Pydantic discriminated-union document models, one per kind
│       ├── loader.py                         # directory walk + multi-doc YAML parsing → ParsedRepository
│       ├── urns.py                           # shared URN / ContainerKey builders, reference resolution
│       └── builders/
│           ├── platform.py                   # DATA_PLATFORM → dataPlatformInfo
│           ├── tag.py                        # TAG → SDK V2 Tag
│           ├── glossary.py                   # GLOSSARY_NODE / GLOSSARY_TERM
│           ├── structured_property.py        # STRUCTURED_PROPERTY
│           ├── domain.py                     # DOMAIN
│           ├── container.py                  # CONTAINER (gen_containers, topological sort)
│           ├── dataset.py                    # DATASET (SDK V2 Dataset, schema, FKs, lineage)
│           ├── data_product.py                # DATA_PRODUCT
│           ├── data_flow_job.py               # DATA_FLOW / DATA_JOB (SDK V2, fine-grained lineage)
│           ├── data_process_instance.py       # DATA_PROCESS_INSTANCE (run events)
│           ├── assertion.py                  # ASSERTION (FRESHNESS/SQL/FIELD)
│           └── raw_aspect.py                 # aspectName-keyed passthrough (DATASET_PROFILE, extensible)
└── tests/
    ├── unit/
    │   └── test_yaml_source.py
    │   └── test_loader.py
    │   └── test_builders_*.py
    └── integration/
        └── yaml_source/
            ├── test_yaml_source_golden.py
            ├── resources/                    # small curated fixture tree mirroring datahub-sample's shape
            │   ├── setup/assets.yml
            │   ├── raw-layer/assets.yml
            │   ├── dataproduct-layer/assets.yml
            │   └── ...
            └── yaml_source_mces_golden.json
```

### SDK Generation vs. Raw MCP (per `main.md` / `patterns.md`)

SDK V2 does **not** yet cover every entity this format needs. Use SDK V2 wherever it
exists; fall back to `MetadataChangeProposalWrapper` (Gen 2, acceptable per
`patterns.md`) for the rest — never Gen 1 MCE.

| Kind                  | Emission mechanism                                                             |
| --------------------- | ------------------------------------------------------------------------------- |
| CONTAINER             | `gen_containers()` (per `containers.md` Pattern 1)                             |
| DATASET               | `datahub.sdk.Dataset` (SDK V2)                                                  |
| DATA_FLOW / DATA_JOB  | `datahub.sdk.DataFlow` / `datahub.sdk.DataJob` (SDK V2)                        |
| TAG                   | `datahub.sdk.Tag` (SDK V2)                                                      |
| DATA_PLATFORM         | Raw MCP: `DataPlatformInfoClass` onto `urn:li:dataPlatform:<name>`             |
| GLOSSARY_NODE/TERM    | Raw MCP: `GlossaryNodeInfoClass` / `GlossaryTermInfoClass` (+ `GlossaryRelatedTermsClass` for hierarchy) |
| STRUCTURED_PROPERTY   | Raw MCP: `StructuredPropertyDefinitionClass`                                    |
| DOMAIN                | Raw MCP: `DomainPropertiesClass`                                                |
| DATA_PRODUCT          | Raw MCP: `DataProductPropertiesClass` (+ `Domains`/`GlobalTags`/`GlossaryTerms`/`Ownership`/`StructuredProperties` aspects) |
| DATA_PROCESS_INSTANCE | Raw MCP: `DataProcessInstancePropertiesClass`, `DataProcessInstanceRunEventClass`, relationships/input-output aspects |
| ASSERTION             | Raw MCP: `AssertionInfoClass` (discriminated by `assertion.type`)               |
| Raw-aspect docs       | Generic passthrough: look up aspect class by name in `datahub.metadata.schema_classes`, `model_validate` the payload, emit MCP |

### Config Structure

`YamlSourceConfig` inherits `StatefulIngestionConfigBase` + `EnvConfigMixin`. It has
**no `PlatformInstanceConfigMixin`** at the top level — this source doesn't have one
platform, it *declares* platforms per-entity via `DATA_PLATFORM` documents and
per-container/dataset `platform:` fields.

```python
class YamlSourceConfig(StatefulIngestionConfigBase, EnvConfigMixin):
    path: str = Field(
        description="Root directory to scan recursively for YAML metadata files."
    )
    file_pattern: str = Field(
        default="**/*.yml",
        description="Glob pattern (relative to `path`) for files to parse. "
        "Both *.yml and *.yaml are scanned regardless of this pattern's extension.",
    )
    fail_on_unresolved_reference: bool = Field(
        default=False,
        description="If true, a reference to a tag/domain/glossary term/container "
        "that was never declared raises an error instead of a warning.",
    )
    stateful_ingestion: Optional[StatefulStaleMetadataRemovalConfig] = Field(default=None)
```

Example recipe:

```yaml
source:
  type: yaml
  config:
    path: /path/to/aphp-metadata-repo
    env: PROD
sink:
  type: datahub-rest
  config:
    server: http://localhost:8080
```

### Capabilities to Implement

| Capability            | Priority | Implementation Notes                                                |
| ---------------------- | -------- | --------------------------------------------------------------------- |
| SCHEMA_METADATA        | Required | From `DATASET.schema.fields`                                        |
| CONTAINERS             | Required | From `CONTAINER` docs, topologically ordered                        |
| LINEAGE_COARSE/FINE    | Required | Fully declared in YAML — no parsing, direct translation             |
| OWNERSHIP              | Required | `owners:` present on nearly every kind                               |
| TAGS                   | Required | `TAG` docs + `tags:` references                                      |
| GLOSSARY               | Required | `GLOSSARY_NODE`/`GLOSSARY_TERM` + `glossaryTerms:` references         |
| DOMAINS                | Required | `DOMAIN` docs + `domains:` references                                |
| DATA_PRODUCTS          | Required | `DATA_PRODUCT` docs (assets are raw URNs, no resolution needed)      |
| DATA_FLOW / DATA_JOB   | Required | Pipeline metadata + fine-grained lineage                             |
| DATA_PROCESS_INSTANCE  | Optional | Run history — nice-to-have, can ship after core kinds                |
| ASSERTION              | Optional | Data-quality checks — independent of core entity graph                |
| PLATFORM registration  | Required | `DATA_PLATFORM` docs (see `platform_registration.md`)                 |
| DELETION_DETECTION     | Optional | Stateful ingestion — natural fit since re-running reflects file deletions |
| STRUCTURED_PROPERTIES  | Optional | Definitions + values attached via `structuredProperties:` on entities |

## Known Limitations

| Limitation                                                                 | Impact                                              | Workaround                                                                 |
| ----------------------------------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------- |
| No live connection — purely reflects whatever is checked into the YAML files | Metadata can drift from the real systems              | Out of scope; this connector's job is the YAML, not the underlying systems |
| Cross-file references require loading the **entire** tree into memory before emitting | Memory grows with repo size (acceptable for metadata-as-code scale, not big-data scale) | `performance.md`: fine at expected scale (hundreds–low thousands of docs); document the limit, add `FileBackedDict` only if it becomes a real problem |
| `DATA_PLATFORM` custom platforms only get a logo if `logoUrl` is a reachable HTTP(S) URL | Broken icons for platforms with local-only assets     | Document requirement in recipe comments per `platform_registration.md`     |
| Raw-aspect passthrough kind is only implemented for `DATASET_PROFILE` at MVP | Other custom aspect emissions not yet generic          | Design the passthrough generically from day 1; add kinds as needed          |

## Testing Strategy

Per `standards/testing.md`:

- **Unit tests** (`tests/unit/`): one file per builder module — parsing/validation of
  each Pydantic model (valid + invalid documents), URN construction, reference
  resolution (including the "unresolved reference → warning, not crash" behavior),
  and topological container ordering. No trivial "field exists" tests — test actual
  parsing/URN-building logic and error paths.
- **Integration tests** (`tests/integration/yaml_source/`): a curated fixture
  directory (trimmed version of the AP-HP sample, covering **every kind** including
  at least 2 datasets with FKs, a container hierarchy at least 2 levels deep, a data
  product with `assets`, a data flow/job pair with fine-grained lineage, one
  `DATA_PROCESS_INSTANCE`, one `ASSERTION` of each type, and one raw
  `DATASET_PROFILE` doc) run through `datahub ingest` against a file sink, validated
  against a golden file (`--update-golden-files` to generate/refresh).
- No Docker needed — the "backend" is just files in the repo, so integration tests
  are fully deterministic and fast.

## Implementation Order

1. `models.py` — Pydantic discriminated-union models for all 13 kinds + raw-aspect doc, with unit tests for parsing/validation
2. `loader.py` — directory walk, multi-doc YAML parsing, `ParsedRepository` aggregation, with unit tests (missing files, malformed YAML, duplicate ids)
3. `urns.py` — URN/ContainerKey builders + reference resolver (with soft-error reporting), unit tested
4. `yaml_source_config.py`, `yaml_source_report.py`
5. Builders in dependency order: platform → tag → glossary → structured_property → domain → container (+ topological sort) → dataset (schema, FKs, lineage)
6. `yaml_source.py` orchestrating the two-pass emit order; register in `setup.py` entry points
7. Remaining builders: data_product, data_flow_job, data_process_instance, assertion, raw_aspect
8. Unit tests for every builder (≥80% coverage)
9. Integration test fixture tree + golden file
10. Documentation (`docs/sources/yaml/yaml.md` + `yaml_recipe.yml`) per `registration.md`

## Approval

- [x] User approved this plan on: 2026-07-13
- [x] Approval message: "j'approuve le plan"
