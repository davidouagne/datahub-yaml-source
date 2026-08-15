# YAML Metadata Source Connector - Planning Document

**Created**: 2026-07-13
**Last updated**: 2026-08-15
**Status**: IMPLEMENTED — initial build and the coverage-extension both shipped
**Extension spec**: [`docs/specs/entity-aspect-coverage-gaps.md`](docs/specs/entity-aspect-coverage-gaps.md)

This document merges what was originally two files: the initial-build plan (2026-07-13) and the
coverage-extension plan (`_PLANNING-v2.md`, 2026-08-15, now folded in here). Both are fully
implemented; this is the as-built record of the whole connector, not a forward-looking plan.

## Overview

A standalone DataHub ingestion source plugin that reads a directory tree of declarative
YAML files ("metadata as code") and emits the full range of DataHub entities they
describe: data platforms, tags, glossary terms, structured properties, domains,
applications, containers, datasets (schema/FK/lineage/column-level metadata), charts,
dashboards, data products, pipelines (DataFlow/DataJob with fine-grained lineage),
pipeline run history (DataProcessInstance), saved/observed queries, data quality
assertions and incidents, knowledge-base documents, and a handful of raw time-series
aspects (dataset profiles, usage statistics, operations).

This is **not** a source for one external system — it's a generic "authoring format"
source, closest in spirit to DataHub's built-in `datahub-business-glossary` and
`datahub-lineage-file` sources, but generalized to (almost) the entire DataHub entity
model. The format was originally reverse-engineered from a real example repo at
`C:\Users\4087446\Projects\aphp\datahub-sample` (AP-HP health-data-platform metadata).

No SQL connection and no external API are involved — the source purely parses local
files, so it does not fit the `sql` / `api` / `nosql` categories in the standard
skill classification. Architecturally it is closest to an **API-style source**
(`StatefulIngestionSourceBase`), just with a filesystem "client" instead of an HTTP
client.

**Cross-cutting metadata (owners, tags, glossary terms, domains, applications, links,
deprecation, structured properties, sub-types) is a property of the format, declared
once per `kind` via inheritance from small `Has*` mixins, rather than assembled ad hoc
per builder.** This is the single biggest architectural change since the initial build
— see "Cross-cutting aspect architecture" below — and it's what let 5 new entity kinds
get added with a marginal cost of roughly 3 files each instead of the ~20-file sprawl a
new aspect used to require.

## Research Summary

### Source Classification

- **Type**: Other (declarative file-based / metadata-as-code)
- **Interface**: Local filesystem, multi-document YAML (`---`-separated)
- **Standards File**: `standards/patterns.md`, `standards/api.md` (closest architecture), `standards/containers.md`, `standards/lineage.md` (partially)
- **Reference format**: `C:\Users\4087446\Projects\aphp\datahub-sample` (layered directories: `setup/`, `raw-layer/`, `semantic-layer/`, `transform-layer/`, `sharing-layer/`, `quality-layer/`, `dataproduct-layer/`, `observability-layer/`)

**Key simplification vs. a typical connector**: lineage is **fully hand-declared** in
the YAML (`upstreamLineage`, `fineGrainedLineages`, `dataJobInputOutput`). There is no
SQL to parse and no `SqlParsingAggregator` needed — declared references translate
directly into `UpstreamLineageClass` / `FineGrainedLineageClass`.

### Similar DataHub Connectors

| Connector                  | Relevance | Key Patterns                                                                 |
| --------------------------- | --------- | ----------------------------------------------------------------------------- |
| `datahub-business-glossary` | High      | YAML file → GlossaryTerm/GlossaryNode entities, no live connection           |
| `datahub-lineage-file`      | High      | YAML file → lineage edges onto existing URNs, no live connection            |
| `file` (generic MCE/MCP)    | Medium    | Reads raw metadata files; shows the "no platform of its own" emitter pattern |
| Any API source (`api.md`)   | Medium    | `StatefulIngestionSourceBase`, config/report/source file split, stateful removal |

## Entity Mapping

The connector covers **24 entity kinds** (discriminated by a `kind:` field on every YAML
document) plus a **raw-aspect passthrough** format (discriminated by an `aspectName:`
field). 14 kinds shipped in the initial build; `CHART`, `DASHBOARD`, `QUERY`, `INCIDENT`,
and `DOCUMENT` were added in the coverage extension (Phase 4); `MLMODEL`, `MLMODEL_GROUP`,
`MLFEATURE_TABLE`, `MLFEATURE`, and `MLPRIMARY_KEY` in Phase 5A. `SEMANTIC_MODEL`,
`METRIC`, `SERVICE`, `API`, `REPOSITORY`, `AI_AGENT`, and `AGENT_SKILL` are planned for
Phases 5B/5C (not yet shipped).

| `kind:` value | DataHub entity | Own aspects / notes | Emission mechanism |
| --- | --- | --- | --- |
| `DATA_PLATFORM` | `dataPlatform` | Registers custom platforms not in DataHub's core enum | Raw MCP (`DataPlatformInfoClass`) |
| `TAG` | `tag` | name, description, colorHex | SDK V2 `Tag` |
| `GLOSSARY_NODE` | `glossaryNode` | id, name, definition, parentNode | SDK V2 `GlossaryNode` |
| `GLOSSARY_TERM` | `glossaryTerm` | id, name, definition, parentNode, related-term relationships, term source | SDK V2 `GlossaryTerm` |
| `STRUCTURED_PROPERTY` | `structuredProperty` | qualifiedName, cardinality, valueType, allowedValues, entityTypes, settings, typeQualifier | Raw MCP (`StructuredPropertyDefinitionClass`) |
| `DOMAIN` | `domain` | id, name, description, nested via `parentDomain` (topologically sorted) | Raw MCP (`DomainPropertiesClass`) + `common_aspect_mcps()` |
| `APPLICATION` | `application` | id, name, description | Raw MCP (`ApplicationPropertiesClass`) + `common_aspect_mcps()` |
| `CONTAINER` | `container` | platform/instance/database/(schema), `parentContainer`, topologically ordered | `gen_containers()` + follow-up MCPs for the aspects it doesn't natively take |
| `DATASET` | `dataset` | schema fields (+ `foreignKeys`, column-level tags/terms/deprecation/structuredProperties), `container`, `upstreamLineage`, `viewProperties` | SDK V2 `Dataset` + `common_sdk_kwargs()` |
| `CHART` | `chart` | platform, name, chartUrl, chartType, container, inputDatasets | SDK V2 `Chart` + `common_sdk_kwargs()` |
| `DASHBOARD` | `dashboard` | platform, name, dashboardUrl, container, charts, nested dashboards, inputDatasets | SDK V2 `Dashboard` + `common_sdk_kwargs()` |
| `QUERY` | `query` | id, statement, language, source, subjects (dataset or column) | Raw MCP (`queryProperties`, `querySubjects`) + `common_aspect_mcps()` |
| `INCIDENT` | `incident` | id, type, entities, status, priority, assignees, source, notes | Raw MCP (`incidentInfo`, `incidentNotes`) + `common_aspect_mcps()` |
| `DOCUMENT` | `document` | id, title, text (native) or platform+externalUrl (external), parentDocument, relatedAssets/relatedDocuments | SDK V2 `Document.create_document()` / `create_external_document()` + `common_sdk_kwargs()` |
| `MLFEATURE` | `mlFeature` | featureNamespace, name, dataType, sources (dataset or column) | Raw MCP (`MLFeaturePropertiesClass`) + `common_aspect_mcps()` |
| `MLPRIMARY_KEY` | `mlPrimaryKey` | featureNamespace, name, dataType, sources (required) | Raw MCP (`MLPrimaryKeyPropertiesClass`) + `common_aspect_mcps()` |
| `MLFEATURE_TABLE` | `mlFeatureTable` | platform, name, mlFeatures, mlPrimaryKeys | Raw MCP (`MLFeatureTablePropertiesClass`) + `common_aspect_mcps()` |
| `MLMODEL_GROUP` | `mlModelGroup` | platform, name, container | SDK V2 `MLModelGroup` + `common_sdk_kwargs()` (narrowed `native=`, no `subtype=`/`applications=`/`container=` kwarg) |
| `MLMODEL` | `mlModel` | platform, name, modelGroup, mlFeatures, container, hyperParameters, type, full model card (intendedUse, ethicalConsiderations, caveatsAndRecommendations, trainingData, evaluationData, factorPrompts, metrics, sourceCode) | SDK V2 `MLModel` + `common_sdk_kwargs()` (same narrowed `native=`); model-card aspects always via `extra_aspects=` (valid only on `mlModel`, not a shared mixin) |
| `DATA_PRODUCT` | `dataProduct` | id, name, assets (raw URNs) | Raw MCP (`DataProductPropertiesClass`) + `common_aspect_mcps()` |
| `DATA_FLOW` | `dataFlow` | orchestrator/flowId/cluster, project, externalUrl, container | SDK V2 `DataFlow` + `common_sdk_kwargs()` |
| `DATA_JOB` | `dataJob` | jobId + `dataFlow` ref, inputDatasets/outputDatasets, inputDataJobs (DAG edges), fineGrainedLineages | SDK V2 `DataJob` + `common_sdk_kwargs()` (no `HasSubTypes` — its own `type` field already maps to that aspect) |
| `DATA_PROCESS_INSTANCE` | `dataProcessInstance` | id, `parentTemplate` (DataJob ref), inputs/outputs, runEvents | Raw MCP (properties, relationships, input/output, run events) |
| `ASSERTION` | `assertion` | id, `assertion` (discriminated by `assertion.type`: `FRESHNESS`/`VOLUME`/`SQL`/`FIELD`/`DATA_SCHEMA`/`CUSTOM`), assertionNote, assertionActions | Raw MCP (`AssertionInfoClass`) + `common_aspect_mcps()` |

### Raw aspect documents

For aspects that don't map to their own `kind` (mostly time-series data), use
`aspectName:` instead of `kind:`:

| `aspectName`                      | Entity reference field       |
| ---------------------------------- | ----------------------------- |
| `DATASET_PROFILE`                  | `dataset:`                    |
| `DATASET_USAGE_STATISTICS`         | `dataset:`                    |
| `OPERATION`                        | `dataset:`                    |
| `ASSERTION_RUN_EVENT`              | `assertionUrn:` (full URN)    |
| `DATA_PROCESS_INSTANCE_RUN_EVENT`  | `dataProcessInstanceUrn:` (full URN) |

The passthrough is implemented generically (look up the aspect class by name in
`datahub.metadata.schema_classes`, `model_validate` the payload, emit an MCP) —
`raw_aspect.py`'s per-aspect builder registry exists because nested payloads need real
aspect classes, not raw dicts, not because the mechanism itself is aspect-specific.

### URN / Reference Resolution

Every kind can reference entities defined in a **different file**, so the source does a
**two-pass** load:

1. **Parse pass** — walk the configured root directory, read every `*.yml`/`*.yaml`
   file as a multi-document YAML stream, and validate each document against a
   discriminated Pydantic model keyed on `kind` (or `aspectName`). Collect everything
   into one in-memory `ParsedRepository` (one list per kind).
2. **Emit pass** — emit workunits in a **fixed topological order** so parents always
   precede children: `DATA_PLATFORM → TAG → GLOSSARY_NODE → GLOSSARY_TERM →
   STRUCTURED_PROPERTY → DOMAIN (topologically sorted by parentDomain) → APPLICATION →
   CONTAINER (topologically sorted by parentContainer) → DATASET → CHART → DASHBOARD →
   QUERY → INCIDENT → DOCUMENT → DATA_PRODUCT → DATA_FLOW → DATA_JOB →
   DATA_PROCESS_INSTANCE → ASSERTION → raw-aspect docs`.

References to other entities inside a document (`container:`, `parentContainer:`,
`tags:`, `glossaryTerms:`, `domains:`, `applications:`, `dataFlow:`, ...) are
structural — they carry enough fields (platform/database/schema/env, or a natural
id/name) to build the target URN deterministically without needing the target to have
been emitted yet. `ReferenceIndex` answers "was this actually declared somewhere in the
tree?" for `tags`/`glossaryTerms`/`domains`/`applications`/`structuredProperties`/
`containers` — an unresolved reference in one of those categories is a **soft error**:
report a warning (or fail hard under `fail_on_unresolved_reference`) and still emit the
association using the computed URN. References to datasets, charts, dashboards, and
documents (e.g. `inputDatasets:`, a dashboard's `charts:`, a document's
`relatedDocuments:`) are never cross-validated this way — those entities are commonly
declared in systems outside this connector's own tree.

## Architecture

### Base Class Selection

**Chosen**: `StatefulIngestionSourceBase` + `TestableSource` (the `api.md` pattern).

**Rationale**: There is no SQL/JDBC interface and no SQLAlchemy dialect, so the SQL
base classes don't apply. The "client" is a local directory walker instead of an HTTP
client, but the shape of the problem (config → discover items → build typed models →
emit workunits → support stateful stale-entity removal) is identical to an API source.

### Package Layout

```
datahub-yaml-source/
├── setup.py                                  # own entry point + deps (pyyaml, acryl-datahub>=1.7.0)
├── src/
│   └── datahub_yaml_source/
│       ├── __init__.py                       # exports YamlSource
│       ├── yaml_source.py                    # main Source class, get_workunits_internal(), @capability decorators
│       ├── yaml_source_config.py             # YamlSourceConfig
│       ├── yaml_source_report.py             # YamlSourceReport (per-kind counters, dangling_references, unknown_fields)
│       ├── models.py                         # Pydantic discriminated-union document models + the 9 Has* mixins
│       ├── loader.py                         # directory walk + multi-doc YAML parsing → ParsedRepository
│       ├── urns.py                           # URN / ContainerKey builders, ReferenceIndex
│       └── builders/
│           ├── common.py                     # common_sdk_kwargs() / common_aspect_mcps() -- the cross-cutting aspect engine
│           ├── platform.py                   # DATA_PLATFORM
│           ├── tag.py                        # TAG
│           ├── glossary.py                   # GLOSSARY_NODE / GLOSSARY_TERM
│           ├── structured_property.py        # STRUCTURED_PROPERTY
│           ├── domain.py                     # DOMAIN (+ topological sort)
│           ├── application.py                # APPLICATION
│           ├── container.py                  # CONTAINER (gen_containers, topological sort)
│           ├── dataset.py                    # DATASET (schema, FKs, lineage, view properties, column-level metadata)
│           ├── chart.py                      # CHART
│           ├── dashboard.py                  # DASHBOARD
│           ├── query.py                      # QUERY
│           ├── incident.py                   # INCIDENT
│           ├── document.py                   # DOCUMENT
│           ├── ml.py                         # MLFEATURE_TABLE / MLFEATURE / MLPRIMARY_KEY / MLMODEL_GROUP / MLMODEL
│           ├── data_product.py               # DATA_PRODUCT
│           ├── data_flow_job.py              # DATA_FLOW / DATA_JOB (fine-grained lineage, job-to-job DAG edges)
│           ├── data_process_instance.py      # DATA_PROCESS_INSTANCE (run events)
│           ├── assertion.py                  # ASSERTION (FRESHNESS/VOLUME/SQL/FIELD/DATA_SCHEMA/CUSTOM)
│           └── raw_aspect.py                 # aspectName-keyed passthrough
└── tests/
    ├── unit/                                 # test_models.py, test_loader.py, test_urns.py,
    │                                         # test_builders_{core,dataset,extended,flow_job,bi}.py, test_yaml_source.py,
    │                                         # test_json_schema_generation.py, test_markdown_docs_generation.py
    └── integration/
        └── yaml_source/
            ├── test_yaml_source_golden.py
            ├── resources/                    # curated fixture tree, one layer per subdirectory,
            │                                 # covering every kind and every cross-cutting aspect
            └── yaml_source_mces_golden.json
```

### Cross-cutting aspect architecture

`owners`, `tags`, `glossaryTerms`, `domains`, `applications`, `links` (institutional
memory), `deprecation`, `structuredProperties`, and `subTypes` are declared once via
nine small mixins in `models.py`, mirroring the shape DataHub's own SDK V2 uses
(`HasOwnership`, `HasTags`, `HasTerms`, `HasDomain`, `HasInstitutionalMemory`,
`HasSubtype` in `datahub/sdk/_shared.py`):

```python
class HasOwners(BaseModel):            owners: Optional[OwnersField] = None
class HasTags(BaseModel):              tags: Optional[StringList] = None
class HasTerms(BaseModel):             glossaryTerms: Optional[StringList] = None
class HasDomain(BaseModel):            domains: Optional[str] = None
class HasApplications(BaseModel):      applications: Optional[StringList] = None
class HasLinks(BaseModel):             links: Optional[List[LinkDoc]] = None
class HasDeprecation(BaseModel):       deprecation: Optional[DeprecationDoc] = None
class HasStructuredProps(BaseModel):   structuredProperties: Optional[Dict[str, Any]] = None
class HasSubTypes(BaseModel):          subTypes: Optional[SubTypesField] = None
```

Each kind inherits exactly the mixins DataHub's entity registry
(`metadata-models/src/main/resources/entity-registry.yml`) permits for that entity type
— per-kind validity is *static*: a field that isn't valid on a kind simply isn't a field
on that Pydantic model. `glossaryTerms` on a `TAG` doesn't get rejected by an allowlist
check; it doesn't exist as a field at all. The matrix below is the verified derivation
of the class declarations (● = permitted):

| | Owners | Tags | Terms | Domain | Applications | Links | Deprecation | StructProps | SubTypes |
|---|---|---|---|---|---|---|---|---|---|
| `DATASET` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `CHART` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `DASHBOARD` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `CONTAINER` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `DATA_FLOW` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `DATA_JOB` | ● | ● | ● | ● | ● | ● | ● | ● | (via own `type` field) |
| `DATA_PRODUCT` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `DOCUMENT` | ● | ● | ● | ● | | ● | | ● | ● |
| `MLMODEL` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `MLMODEL_GROUP` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `MLFEATURE_TABLE` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `MLFEATURE` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `MLPRIMARY_KEY` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `GLOSSARY_TERM` | ● | ● | | ● | ● | ● | ● | ● | ● |
| `GLOSSARY_NODE` | ● | ● | | ● | | ● | | ● | ● |
| `APPLICATION` | ● | ● | | ● | | ● | | ● | ● |
| `DOMAIN` | ● | | | | | ● | ● | ● | |
| `TAG` | ● | | | | | | ● | | |
| `ASSERTION` | ● | ● | | | | | | | |
| `QUERY` | | | | | | | | | ● |
| `INCIDENT` | | ● | | | | | | | |
| `SchemaField` (column) | | ● | ● | | | | ● | ● | |

`schemaField` (column-level metadata) is not a `kind:` of its own — it's a nested
`schema.fields[]` entry on `DATASET`, and only the 4 aspects the PII-tagging use case
needs are wired (tags, glossaryTerms, deprecation, structuredProperties), even though
the registry permits more (ownership, domains, subTypes, documentation,
businessAttributes) — no current use case for those.

**Emission split**: the nine common aspects don't all reach DataHub the same way, so
`builders/common.py` has two dispatchers rather than one:

```python
def common_sdk_kwargs(doc, index, report, context, *, native=FULL_NATIVE_KWARGS) -> dict:
    """Cross-cutting aspects for an SDK V2-backed kind: returns owners=/tags=/terms=/
    domain=/links=/subtype= (only the subset the target SDK class natively supports --
    see `native=`) plus an `extra_aspects` list for the rest (applications, deprecation,
    structuredProperties always go here; anything the doc has but the SDK class doesn't
    natively support falls back here too)."""

def common_aspect_mcps(entity_urn, doc, index, report, context, *, skip=frozenset()) -> Iterable[MetadataWorkUnit]:
    """Same aspects as standalone follow-up MCPs, for raw-MCP kinds (DOMAIN, APPLICATION,
    DATA_PRODUCT, ASSERTION, QUERY, INCIDENT) and for CONTAINER's follow-ups after
    gen_containers()."""
```

Both dispatch on `isinstance(doc, HasTags)` etc., so a kind automatically gets whatever
it inherited and nothing else. `native=` exists because not every SDK V2 entity class
implements the same subset: `Tag`/`GlossaryNode`/`GlossaryTerm` each support a different
combination (verified via `__mro__`), and `Document`'s factory functions have no `links=`
kwarg at all. Three aspects **never** go through an SDK constructor kwarg regardless of
kind: `applications` (no SDK support), `deprecation` (no SDK support), and
`structuredProperties` (the SDK's own `structured_properties=` kwarg routes through
`set_structured_property()`, which stamps a non-deterministic `datetime.now()` audit
stamp and silently drops all but one value for a MULTIPLE-cardinality property — always
built directly as `StructuredPropertiesClass` and passed via `extra_aspects=` instead).

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
        description="If true, a reference to a tag/domain/glossary term/container/"
        "application/structuredProperty that was never declared, or a field that's "
        "either misspelled or not valid for its kind, raises an error instead of a "
        "warning.",
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

### Capabilities

Declared via `@capability` on `YamlSource`, each backed by real fixture output:

| Capability | Produced by |
| --- | --- |
| `SCHEMA_METADATA` | `DATASET.schema.fields` |
| `CONTAINERS` | `CONTAINER` docs, topologically ordered |
| `LINEAGE_COARSE` / `LINEAGE_FINE` | Fully declared in YAML (`upstreamLineage`, `fineGrainedLineages`) — no parsing |
| `OWNERSHIP` | `owners:` on every kind that permits it |
| `TAGS` | `TAG` docs + `tags:` references |
| `DOMAINS` | `DOMAIN` docs + `domains:` references |
| `GLOSSARY_TERMS` | `GLOSSARY_*` docs + `glossaryTerms:` references |
| `DESCRIPTIONS` | `description:` on nearly every kind |
| `PLATFORM_INSTANCE` | `instance:` on datasets/containers/charts/dashboards → `dataPlatformInstance` aspect |
| `DATA_PROFILING` | `aspectName: DATASET_PROFILE` passthrough |
| `USAGE_STATS` | `aspectName: DATASET_USAGE_STATISTICS` passthrough |
| `OPERATION_CAPTURE` | `aspectName: OPERATION` passthrough |
| `DELETION_DETECTION` | Stateful ingestion |
| `TEST_CONNECTION` | Path-exists/is-directory check |

Data products, pipelines (`DATA_FLOW`/`DATA_JOB`), assertions/incidents, and the BI
kinds (`CHART`/`DASHBOARD`/`QUERY`/`DOCUMENT`) are all emitted but have no dedicated
`SourceCapability` enum value to decorate with — DataHub's capability enum simply
doesn't have one for each entity type.

## Decisions

### D1 — Granular per-aspect mixins, not one flat mixin + runtime allowlist

An early sketch used a single `CommonMetadataMixin` carrying all nine fields, plus a
`COMMON_ASPECTS_BY_KIND` allowlist checked at runtime. **Chosen instead**: one small
mixin per aspect (above), each kind inheriting exactly the ones DataHub's entity
registry permits.

**Why**: this is the shape DataHub's own SDK V2 uses, so the format's model layer and
the SDK it targets read the same way. Per-kind validity becomes *static*: the generated
`reference.md` and JSON schema show a field only where it is genuinely valid, with no
second allowlist to keep in sync with the class declarations.

The allowlist still exists, but only as the *derivation* of the class declarations,
recorded as the matrix comment in `models.py` citing `entity-registry.yml` at the
pinned version.

### D2 — Unknown / non-permitted fields: warning by default, hard failure on request

Every entity doc model gets `model_config = ConfigDict(extra="allow")`. The loader
inspects `model_extra` after validation and reports anything there via
`report.report_unknown_fields(...)` — a counter alongside `dangling_references` —
which `fail_on_unresolved_reference: true` escalates to a hard error.

**Why**: consistent with the connector's existing "one bad document warns and is
skipped, it never takes down the run" philosophy, while fixing the original design's
core gap — a misspelled or non-applicable field used to be *silently* dropped.
`extra="forbid"` was rejected as too risky against the real AP-HP repo, where a stray
field is currently ignored without consequence and would become a hard failure
overnight.

### D3 — Named platform instances (`dataPlatformInstanceProperties`) deferred

The `dataPlatformInstance` *aspect* keeps being emitted exactly as before; instances
simply continue to render unnamed in the UI. Neither a nested `instances:` block nor a
`DATA_PLATFORM_INSTANCE` kind was built. Left in Future Considerations.

### D4 — Doc generator learns about the mixins

Pydantic orders `model_fields` with inherited fields first, so the mixins would push
`kind`/`name`/`platform` below `owners`/`tags`/… in every generated table.
`scripts/generate_markdown_docs.py` renders each kind's *own* fields first, then a short
"Plus these common metadata fields" subsection linking to one shared section documented
once — turning what would have been an accidental ordering regression into the
single-declaration-point documentation improvement the coverage-extension spec asked
for.

## Corrections found during implementation (C1-C8)

Each was found by checking an assumption against the actually-installed SDK or a real
pipeline run, not by re-reading the spec more carefully:

| # | Assumption | Reality | Consequence |
|---|---|---|---|
| C1 | `gen_containers()` takes no `domain`/`structuredProperties` → needs follow-up MCPs for everything | Its signature **does** include `domain_urn=` and `structured_properties=` | Container follow-ups are only needed for `terms`, `links`, `deprecation`, `applications` |
| C2 | `DATA_FLOW` needs new plumbing for `container` and `glossaryTerms` | `DataFlow.__init__` already accepts `parent_container`, `terms`, `links`, `structured_properties`, `extra_aspects` | Both become constructor kwargs, near-free |
| C3 | `DATA_JOB` needs `externalUrl`/`properties`/`container` | `DataJob.__init__` accepts `external_url`, `custom_properties`, `terms`, `links`, `domain`, `structured_properties` — but **no `parent_container`** | Only `container` needs special handling: `extra_aspects=[ContainerClass(container=...)]` |
| C4 | "Don't call `set_structured_property()`" (non-deterministic timestamp) | True — **and** the `structured_properties=` constructor kwarg on every SDK V2 entity routes straight into it | The kwarg is unusable for golden-file work; always build `StructuredPropertiesClass` directly and pass via `extra_aspects=` |
| C5 | `subTypes` fix = "pass the full list" | `subtype=` is a single `str`; `set_subtype()` stores `typeNames=[subtype]`, and `_set_extra_aspects()` runs *before* `set_subtype()` in `__init__` | Multi-subtype needs `subtype=None` + `SubTypesClass(typeNames=[...])` via `extra_aspects` — passing both would let `subtype=` silently win |
| C6 | `DeprecationClass.note` / `RowCountTotalClass.parameters` are `Optional` (per the generated Python stub) | Both are **required, non-nullable** in their Avro schema (`Deprecation.pdl`) — `None` parses fine but crashes `MetadataChangeProposalWrapper.validate()` at emit time, taking down the whole ingestion run | Fixed: `note=dep.note or ""`; `value` required for `VOLUME` assertions and `parameters` always constructed |
| C7 | `AssertionNoteClass` is a normal registered aspect | Not a registered top-level aspect (no `get_aspect_name()`) in `acryl-datahub==1.6.0.13` — **is** one in `1.7.0.3` | Dropped, then restored once the floor moved to `1.7.0.3` |
| C8 | Every SDK V2 entity stamps a deterministic `time=0` audit stamp when none is given | `Document.create_document()`/`create_external_document()` stamp `datetime.now()` on `created`/`lastModified` if `created_time`/`last_modified_time` are omitted — the only SDK V2 entity in this connector that does | Pinned to the Unix epoch explicitly in `builders/document.py` for golden-file determinism |

Two more traps, not spec-related:

- `DataFlow`'s and `Dataset`'s `parent_container=` default to a private `Unset`
  sentinel, not `None`. Passing `None` explicitly still calls `_set_container(None)`,
  which emits an unwanted empty `browsePathsV2` aspect. Fixed by only including the
  kwarg in the dict at all when a container is actually declared (`chart.py`,
  `dashboard.py`, `data_flow_job.py`, `dataset.py` all follow this pattern).
- A self-introduced bug caught before it shipped: `TagDoc` was initially given a
  `HasLinks` mixin that contradicted the verified entity-registry matrix (`tag` doesn't
  support `institutionalMemory`) — caught by writing the matrix comment in `models.py`
  *before* the class declarations and checking each one against it.

## Known Limitations

| Limitation | Impact | Handling |
| --- | --- | --- |
| No live connection — purely reflects whatever is checked into the YAML files | Metadata can drift from the real systems | Out of scope; this connector's job is the YAML, not the underlying systems |
| Cross-file references require loading the **entire** tree into memory before emitting | Memory grows with repo size (acceptable at metadata-as-code scale, not big-data scale) | Fine at expected scale (hundreds–low thousands of docs); add a `FileBackedDict` only if it becomes a real problem |
| `DATA_PLATFORM` custom platforms only get a logo if `logoUrl` is a reachable HTTP(S) URL | Broken icons for platforms with local-only assets | Documented in recipe comments |
| `extra="allow"` means typos are warnings, not errors | A misspelled field still ingests silently-but-noisily unless `fail_on_unresolved_reference` is set | D2, deliberate; documented in `yaml.md` |
| Named platform instances still unsupported | Instances render unnamed in the UI | D3, deferred to Future Considerations |
| `DOCUMENT` MCPs need a recent-enough GMS | Rejected outright on an older target deployment | Real-GMS confirmation still pending — see Open Questions |
| `schemaField` annotations need those URNs indexed by the target GMS | Column tags may not surface in the UI even though the MCPs succeed | Real-GMS confirmation still pending — see Open Questions |

## Testing Strategy

- **Unit tests** (`tests/unit/`): one file per builder/module area — parsing/validation
  of each Pydantic model (valid + invalid documents, mixin composition, unknown-field
  warnings), URN construction, reference resolution (including "unresolved reference →
  warning, not crash"), and topological container/domain ordering.
- **Integration tests** (`tests/integration/yaml_source/`): a curated fixture tree
  covering every kind and every cross-cutting aspect at least once, run through
  `datahub ingest` against a file sink, validated against a golden file.
- No Docker needed — the "backend" is just files in the repo, so integration tests are
  fully deterministic and fast.

| Area | File |
| --- | --- |
| Mixin composition, unknown-field warning, new field parsing | `tests/unit/test_models.py` |
| Per-aspect emission from the shared helpers | `tests/unit/test_builders_core.py`, `test_builders_dataset.py`, `test_builders_extended.py`, `test_builders_flow_job.py`, `test_builders_bi.py` |
| URN helpers | `tests/unit/test_urns.py` |
| Kinds parsed and dispatched | `tests/unit/test_loader.py` |
| Generated-artifact sync | `tests/unit/test_json_schema_generation.py`, `test_markdown_docs_generation.py` (fail if regeneration is skipped — not optional) |
| End-to-end | `tests/integration/yaml_source/` fixture tree + `yaml_source_mces_golden.json` |

Bar: ≥80% coverage on new/changed builder code (currently 97% overall, no file below
83%).

## Implementation History

### Initial build — 2026-07-13

1. `models.py` — Pydantic discriminated-union models for the original 13 kinds + raw-aspect doc.
2. `loader.py` — directory walk, multi-doc YAML parsing, `ParsedRepository` aggregation.
3. `urns.py` — URN/ContainerKey builders + reference resolver.
4. `yaml_source_config.py`, `yaml_source_report.py`.
5. Builders in dependency order: platform → tag → glossary → structured_property →
   domain → container (+ topological sort) → dataset (schema, FKs, lineage).
6. `yaml_source.py` orchestrating the two-pass emit order; registered in `setup.py`
   entry points.
7. Remaining builders: data_product, data_flow_job, data_process_instance, assertion,
   raw_aspect.
8. Unit tests for every builder.
9. Integration test fixture tree + golden file.
10. Documentation (`docs/sources/yaml/yaml.md` + `yaml_recipe.yml`).

### Coverage extension — 2026-08-15

Implements `docs/specs/entity-aspect-coverage-gaps.md`, in four independently-shippable
phases (Phase 1 landed alone — it touches every existing builder plus the golden file,
and mixing it with feature work would have made the diff unreadable):

- **Phase 1 — cross-cutting parity + refactor**: the nine `Has*` mixins, `common_sdk_kwargs()`/
  `common_aspect_mcps()`, every existing builder rewritten to consume them, the multi-subtype
  bug (C5) fixed, seven new `@capability` decorators, nested domains
  (`DomainDoc.parentDomain` + `topological_sort_domains()`), `GlossaryTermDoc`'s related-term
  fields, `TagDoc.colorHex`/`DisplayPropertiesDoc`, and D2's unknown-field warning.
  **Checkpoint met**: the refactor step alone produced an empty golden-file diff before any
  new fixture content was added.
- **Phase 2 — pipeline & assertion completeness** (done opportunistically once C1-C3 showed
  it was cheap): `DataJobDoc.inputDataJobs` (job-to-job DAG edges), `DATA_JOB`
  `externalUrl`/`properties`/`container`, `DATA_FLOW.container`, assertion types `VOLUME`/
  `DATA_SCHEMA`/`CUSTOM`, `assertionNote`/`assertionActions`.
- **Phase 3 — column-level metadata**: `SchemaFieldDoc` gains `HasTags`/`HasTerms`/
  `HasStructuredProps`/`HasDeprecation`; `build_dataset()` emits `schemaField` MCPs after
  the dataset's own workunits, reusing `common_aspect_mcps()` with a context string naming
  the column — no new aspect-construction code needed.
- **Phase 4 — five new entity kinds**, one commit each: `CHART` (`f4ed4cc`), `DASHBOARD`
  (`c63997a`, needs `CHART` first for its `charts:` field), `QUERY` (`24490ef`), `INCIDENT`
  (`19bafcd`), `DOCUMENT` (`664d5c2`, last — gated on the `Document.create_*()` factory
  quirks in C8). Explicitly out of scope for all five (documented, not silently dropped):
  `incidentExternalLinks` (needs a DataHub `connection` entity, absent from this connector),
  `chartQuery`, `embed`, `inputFields`, `editable*Properties` (UI-owned), `*UsageStatistics`
  (would use the existing `aspectName:` raw passthrough mechanism instead, on demand).

Design deviations from the plan as originally approved: `common_sdk_kwargs()` needed a
`native=` parameter partway through Phase 1 (the plan assumed every SDK V2 entity class
implements the same six mixins uniformly; `Tag`/`GlossaryNode`/`GlossaryTerm` each
implement a different subset). `DataJobDoc` deliberately does **not** get `HasSubTypes`
despite the registry permitting `subTypes` on `dataJob` — its pre-existing `type` field
already maps to that exact aspect, and adding both would have given authors two
differently-named fields for the same thing (and crashed on a duplicate `subtype=`
keyword).

### ML / semantic / software-catalog entities — Phase 5, 2026-08-15

Promotes `SEMANTIC_MODEL`/`METRIC`/`SERVICE`/`API`/`REPOSITORY`/`AI_AGENT`/`AGENT_SKILL` and the
5 ML entities (`MLMODEL`/`MLMODEL_GROUP`/`MLFEATURE_TABLE`/`MLFEATURE`/`MLPRIMARY_KEY`) out of Future
Considerations, where they'd been deferred as "brand new in this DataHub release; premature to
encode" and "no current AP-HP use case". 12 kinds, delivered as 3 commits (one per family, not one
per kind as Phase 4 was — validated with the user given the larger batch size): **5A — ML entities**,
5B — semantic layer, 5C — software/AI catalog (5B/5C not yet started).

- **Phase 5A — ML entities**, one commit. All 5 kinds and their aspects verified to exist in both
  `entity-registry.yml` and the installed `acryl-datahub==1.7.0.3` before writing any code — one
  near-miss caught immediately: the AI_AGENT aspect class is `AIAgentInfoClass` (AI capitalized), not
  `AiAgentInfoClass`; a naive `hasattr` check with the wrong casing would have wrongly concluded the
  entity wasn't supported.
  - `MLMODEL`/`MLMODEL_GROUP` use the SDK V2 `datahub.sdk.mlmodel.MLModel`/
    `datahub.sdk.mlmodelgroup.MLModelGroup` wrappers, but **neither exposes `subtype=`,
    `applications=`, or `container=` as a constructor kwarg** (verified by signature inspection,
    despite the registry permitting all three on both entities) — `native=` for these two is
    narrowed to `{owners, tags, terms, domain, links}`; `subTypes`/`applications`/`container` all go
    via `extra_aspects=`, same as every other narrowed-`native=` kind.
  - `MLFEATURE_TABLE`/`MLFEATURE`/`MLPRIMARY_KEY` have no SDK V2 wrapper — raw MCP, same shape as
    `QUERY`/`INCIDENT`. `MLFeatureDoc.sources`/`MLPrimaryKeyDoc.sources` reuse `QuerySubjectRef`
    as-is (a `DatasetRef` with optional `fieldPath`) rather than inventing a new type — the shape
    (dataset, or one of its columns) is identical to what `QUERY.subjects` already needed.
  - **`MLModelDoc` carries the full "model card"** (`intendedUse`, `ethicalConsiderations`,
    `caveatsAndRecommendations`, `trainingData`, `evaluationData`, `factorPrompts`, `metrics`,
    `sourceCode`) per explicit user request — these 8 aspects are valid *only* on `mlModel` (verified
    against the registry, not shared with `mlModelGroup`), so they're plain fields on `MLModelDoc`,
    not a new `Has*` mixin (D1 mixins are for aspects shared *across* kinds). `cost` was deliberately
    excluded even under "full model card" — a financial discriminated-union aspect outside the usual
    model-card concept, with no expressed use case.
  - **New finding (C9)**: `MLModelPropertiesClass.type`/`.hyperParameters`/`.mlFeatures` have no
    matching SDK constructor kwarg at all (only `hyper_params=`, a differently-typed field the SDK
    does expose, which was not used here since the YAML wants a plain `Dict[str, scalar]`). Same
    "SDK partially covers an aspect it already owns" situation as `DataJobDoc.inputDataJobs` (Phase 2)
    — set directly via `model._ensure_model_props()` after construction, before `as_workunits()`.
  - Emission order: `MLFEATURE`/`MLPRIMARY_KEY` before `MLFEATURE_TABLE` (which references them);
    `MLMODEL_GROUP` before `MLMODEL` (which references its group via the SDK's native `model_group=`
    kwarg).
  - Exercised end-to-end in a new integration fixture (`ml-layer/models.yml`).
- **Phase 5B — semantic layer** (`SEMANTIC_MODEL`, `METRIC`) — not yet started. Verified: both have
  SDK V2 wrappers (`datahub.sdk.semantic_model.SemanticModel`/`datahub.sdk.metric.Metric`), both with
  the same narrowed `native=` as 5A (no `subtype=`/`applications=`/`container=` kwarg either).
  `Metric`'s constructor **requires** `semantic_model=` — a real emission-order dependency, not
  cosmetic. `aiContext:` maps to the native `ai_context=` kwarg on both, but needs a real
  `AiContextInput` dataclass (`datahub.sdk.semantic_model.AiContextInput`), not a plain dict — a dict
  fails with `AttributeError` inside the SDK's own `build_ai_context()`. `metricRelationships`'s
  `relatedMetrics`/`parentMetric` need the same `_ensure_metric_relationships()` post-construction
  pattern as C9 (an aspect the SDK partially owns); `metricUpstreams` has no SDK involvement at all,
  so it's a plain `extra_aspects=` entry with no race risk.
- **Phase 5C — software/AI catalog** (`SERVICE`, `API`, `REPOSITORY`, `AI_AGENT`, `AGENT_SKILL`) —
  not yet started. All five: raw MCP, id-based URN (like `QUERY`/`INCIDENT`/`DOCUMENT`). A genuine
  widening of the connector's *subject matter* (software/AI-agent catalog, not data catalog) rather
  than just its kind count — each entity's registry-permitted mixin subset is much thinner than the
  data-oriented kinds (e.g. `SERVICE` only gets `tags`/`owners`/`subTypes`; none of the five get
  `applications` or `deprecation`).
- **Explicitly out of scope for all 12** (documented, not silently dropped): `versionProperties`
  (needs a `VERSION_SET` entity this connector doesn't model, already in Future Considerations),
  `semanticContent` (vector embeddings — system-computed, not hand-authorable), `incidentsSummary`
  (system-computed), `cost` on `MLMODEL` (see above). No new `@capability` decorators — DataHub's
  `SourceCapability` enum has no dedicated value for any ML/semantic/software-catalog entity, the same
  situation already true for `DATA_PRODUCT`/`ASSERTION`/the BI kinds.

Spec item 1.10 (`dataPlatformInstanceProperties`) was deferred by decision D3.
`RawAspectDoc.entityUrn` was added to the model but has no generic-scope builder
registered yet — no concrete new `aspectName` in this round exercises it; wire it up
together with whatever raw aspect first needs a non-dataset/assertion/dataProcessInstance
entity reference.

## Verification

Run from the repo root, using `.venv\Scripts\python.exe`.

**1. Unit tests**
```bash
python -m pytest tests/unit -q
```

**2. Regenerate derived artifacts** (non-optional — two unit tests assert they are in sync)
```bash
python scripts/generate_json_schema.py
python scripts/generate_markdown_docs.py
python -m pytest tests/unit/test_json_schema_generation.py tests/unit/test_markdown_docs_generation.py -q
```

**3. Golden file**
```bash
python -m pytest tests/integration -q
python -m pytest tests/integration -q --update-golden-files   # then review the diff by hand
```
A pure refactor that changes output is a bug — verify an empty structural diff before
new fixture content lands on top of it.

**4. Full suite with coverage**
```bash
python -m pytest tests/unit tests/integration -q --cov=datahub_yaml_source --cov-report=term-missing
# 140 passed, 97% coverage, no file below 83% (acryl-datahub==1.7.0.3)
```

**5. Real ingest against the AP-HP repo** (88 datasets, 64 structured properties, 12 containers, 39 jobs)
```bash
datahub ingest -c docs/sources/yaml/yaml_recipe.yml --dry-run
```
Then a live run, checking the report for `warnings` / `dangling_references` /
`unknown_fields` / `failures` at zero, and confirming in the UI: a dataset with a
structured property value, a deprecated dataset, a dataset with links, a nested domain
tree, a PII-tagged column, a job→job DAG edge, a dashboard with its charts, a query
linked to a column, an incident linked to its triggering assertion, and a native
document. **Not yet run** in this environment — needs the actual sample repo and/or a
live GMS.

**6. Standards review** — `/datahub-skills:connector-review` on the branch before
merging any future change. The capability declarations and report counters answer that
checklist's coverage criteria directly; the shared mixin/dispatcher architecture answers
its DRY criteria.

## Open Questions

| # | Question | Owner | Status |
|---|---|---|---|
| 1 | Confirm each mixin↔kind cell against `entity-registry.yml` at the pinned version before writing the class declarations. | implementer | **Resolved** — done for all 19 kinds, recorded as the matrix comment in `models.py` |
| 2 | Is the target GMS recent enough for `DOCUMENT`, `applications`, and `displayProperties`? | AP-HP platform team | **Open** — code ships regardless; real confirmation against the target deployment still pending |
| 3 | Does the target deployment index `schemaField` entities? | AP-HP platform team | **Open** — same as #2, column-level tags may not surface in the UI even though the MCPs succeed |
| 4 | Does `docs/sources/yaml/yaml_recipe.yml` stay pointed at the `datahub-sample` root? | maintainer | Open, non-blocking |

## Approval

- [x] Initial build approved on: 2026-07-13 — "j'approuve le plan"
- [x] Coverage-extension plan (Phases 1-4) approved and executed phase-by-phase between
      2026-08-15 and the completion of `DOCUMENT` (commit `664d5c2`), each phase reviewed
      and its own commit created before moving to the next.
