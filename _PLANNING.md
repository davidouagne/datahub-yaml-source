# YAML Metadata Source Connector - Planning Document

**Created**: 2026-07-13
**Last updated**: 2026-08-15
**Status**: IMPLEMENTED

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
https://github.com/aphp/datahub-sample (AP-HP health-data-platform metadata).

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
- **Reference format**: https://github.com/aphp/datahub-sample (layered directories: `setup/`, `raw-layer/`, `semantic-layer/`, `transform-layer/`, `sharing-layer/`, `quality-layer/`, `dataproduct-layer/`, `observability-layer/`)

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

The connector covers **29 entity kinds** (discriminated by a `kind:` field on every YAML
document) plus a **raw-aspect passthrough** format (discriminated by an `aspectName:`
field). 14 kinds shipped in the initial build; `CHART`, `DASHBOARD`, `QUERY`, `INCIDENT`,
and `DOCUMENT` were added in the coverage extension (Phase 4); `MLMODEL`, `MLMODEL_GROUP`,
`MLFEATURE_TABLE`, `MLFEATURE`, and `MLPRIMARY_KEY` in Phase 5A; `SEMANTIC_MODEL` and
`METRIC` in Phase 5B; `SERVICE`, `API`, `REPOSITORY`, `AI_AGENT`, and `AGENT_SKILL` in
Phase 5C. All 12 kinds targeted by Phase 5 have now shipped.

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
| `SEMANTIC_MODEL` | `semanticModel` | platform, path, id, nativeDefinition, datasets, aiContext | SDK V2 `SemanticModel` + `common_sdk_kwargs()` (narrowed `native=`, no `subtype=`/`applications=` kwarg); `externalUrl` via `_ensure_model_props()` (no constructor kwarg, C9) |
| `METRIC` | `metric` | platform, path, id, semanticModel (required), expression, derivedFrom, relatedMetrics, datasetUpstreams, aiContext | SDK V2 `Metric` + `common_sdk_kwargs()` (same narrowed `native=`); `externalUrl`/`relatedMetrics` via `_ensure_metric_props()`/`_ensure_metric_relationships()` (C9); emitted after `SEMANTIC_MODEL` — `semantic_model=` is a required constructor kwarg |
| `REPOSITORY` | `repository` | id, name, defaultBranch, languages, license, homepageUrl, archived, source (externalUrl/externalId), forkOf, platform/instance | Raw MCP (`repositoryProperties`, `repositorySource`, `repositoryLineage`) + `common_aspect_mcps()`; `platform`/`instance` emit a standalone `dataPlatformInstance` aspect (no `Has*` mixin — see Phase 5C notes) |
| `API` | `api` | id, name, externalUrl, sourceRepository, restApi (method/path), signature (schemaDefinition), platform/instance | Raw MCP (`apiProperties`, `restApiProperties`, `apiSignature`) + `common_aspect_mcps()` |
| `AGENT_SKILL` | `agentSkill` | id, name, instructions, requiredTools (API ids — `array[Urn]` in the PDL, not free text), sourceRepository, platform/instance | Raw MCP (`agentSkillInfo`) + `common_aspect_mcps()`; no `subTypes` (registry doesn't permit it on `agentSkill`) |
| `AI_AGENT` | `aiAgent` | id, name, tagline, instructions, source (type/clonedFrom), dependencies (skills/tools/models — all `array[Urn]` in the PDL), displayProperties, platform/instance | Raw MCP (`aiAgentInfo`, `aiAgentDependencies`, `displayProperties`) + `common_aspect_mcps()`; `created`/`lastModified` required on `aiAgentInfo` — pinned to the epoch like `queryProperties`; no `subTypes` |
| `SERVICE` | `service` | id, displayName, lifecycle, apis, sourceRepository, mcpServer (url/transport), definition (format/rawSpec/version), platform/instance | Raw MCP (`serviceProperties`, `mcpServerProperties`, `serviceDefinition`) + `common_aspect_mcps()`; only `tags`/`owners`/`subTypes` among the 9 cross-cutting mixins — the most restricted kind in the connector |
| `DATA_PRODUCT` | `dataProduct` | id, name, assets (raw URNs) | Raw MCP (`DataProductPropertiesClass`) + `common_aspect_mcps()` |
| `DATA_FLOW` | `dataFlow` | orchestrator/flowId/cluster, project, externalUrl, container | SDK V2 `DataFlow` + `common_sdk_kwargs()` |
| `DATA_JOB` | `dataJob` | jobId + `dataFlow` ref, inputDatasets/outputDatasets, inputDataJobs (DAG edges), fineGrainedLineages | SDK V2 `DataJob` + `common_sdk_kwargs()` (no `HasSubTypes` — its own `type` field already maps to that aspect) |
| `DATA_PROCESS_INSTANCE` | `dataProcessInstance` | id, `parentTemplate` (DataJob ref), inputs/outputs, runEvents | Raw MCP (properties, relationships, input/output, run events) |
| `ASSERTION` | `assertion` | id, `assertion` (discriminated by `assertion.type`: `FRESHNESS`/`VOLUME`/`SQL`/`FIELD`/`DATA_SCHEMA`/`CUSTOM`), assertionNote, assertionActions | Raw MCP (`AssertionInfoClass`) + `common_aspect_mcps()` |

### Raw aspect documents

For aspects that don't map to their own `kind` (mostly time-series data), use
`aspectName:` instead of `kind:`:

| `aspectName`                       | Entity reference field        |
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
   QUERY → INCIDENT → DOCUMENT → MLFEATURE → MLPRIMARY_KEY → MLFEATURE_TABLE →
   MLMODEL_GROUP → MLMODEL → SEMANTIC_MODEL → METRIC → REPOSITORY → API → AGENT_SKILL →
   AI_AGENT → SERVICE → DATA_PRODUCT → DATA_FLOW → DATA_JOB → DATA_PROCESS_INSTANCE →
   ASSERTION → raw-aspect docs`.

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
│           ├── semantic.py                   # SEMANTIC_MODEL / METRIC
│           ├── software.py                   # REPOSITORY / API / AGENT_SKILL / AI_AGENT / SERVICE
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
| `SEMANTIC_MODEL` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `METRIC` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `REPOSITORY` | ● | ● | ● | ● | | ● | | ● | ● |
| `API` | ● | ● | ● | ● | | ● | | ● | ● |
| `AGENT_SKILL` | ● | ● | ● | ● | | ● | | ● | |
| `AI_AGENT` | ● | ● | ● | ● | | ● | | ● | |
| `SERVICE` | ● | ● | | | | | | | ● |
| `GLOSSARY_TERM` | ● | ● | | ● | ● | ● | ● | ● | ● |
| `GLOSSARY_NODE` | ● | ● | | ● | | ● | | ● | ● |
| `APPLICATION` | ● | ● | | ● | | ● | | ● | ● |
| `DOMAIN` | ● | | | | | ● | ● | ● | |
| `TAG` | ● | | | | | | ● | | |
| `ASSERTION` | ● | ● | | | | | | | |
| `QUERY` | | | | | | | | | ● |
| `INCIDENT` | | ● | | | | | | | |
| `SchemaField` (column) | | ● | ● | | | | ● | ● | |

The five Phase 5C kinds (`REPOSITORY`/`API`/`AGENT_SKILL`/`AI_AGENT`/`SERVICE`) also each
accept a tenth aspect this matrix doesn't track: `dataPlatformInstance`, via a `platform`/
`instance` field pair on their Doc classes and a new
`build_data_platform_instance_aspect()` helper in `builders/common.py`. It's not a
`Has*` mixin (nothing else in the connector uses it — their URNs are the only ones in
the connector that don't already encode a platform) and is emitted directly by each
Phase 5C builder rather than dispatched from `common_sdk_kwargs()`/`common_aspect_mcps()`.

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

`YamlSourceConfig` inherits `StatefulIngestionConfigBase` only — **no `EnvConfigMixin`**,
**no `PlatformInstanceConfigMixin`** at the top level. This source doesn't have one
platform or one environment: it *declares* both per-entity via `DATA_PLATFORM`
documents and per-container/dataset `platform:`/`env:` fields. (An earlier draft of
this doc specified `EnvConfigMixin` and a `file_pattern` field; neither was actually
built — extensions are hard-coded to `.yml`/`.yaml` in `loader.discover_yaml_files()`.)

```python
class YamlSourceConfig(StatefulIngestionConfigBase):
    path: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="One or more locations to scan for YAML metadata files: a local "
        "directory (recursive), an s3://bucket/prefix (recursive, requires "
        "aws_connection), or an https://.../file.yml URL (single file, requires "
        "http_connection only if authenticated). Required unless git_info is set, "
        "in which case a relative local entry defaults to/resolves against the "
        "cloned checkout; s3/http entries are rejected together with git_info.",
    )
    git_info: Optional[GitInfo] = Field(
        default=None,
        description="Git repository to shallow-clone before scanning, instead of "
        "reading an already-checked-out local directory. Same shape as DataHub's "
        "GitReference/GitInfo (datahub.configuration.git), used by the lookml and "
        "odcs sources for the same purpose. Requires the `git` extra.",
    )
    aws_connection: Optional[Dict[str, Any]] = Field(default=None)
    http_connection: Optional[HTTPConnectionConfig] = Field(default=None)
    max_input_file_bytes: Optional[int] = Field(default=None)
    fail_on_unresolved_reference: bool = Field(
        default=False,
        description="If true, a reference to a tag/domain/glossary term/container/"
        "application/structuredProperty that was never declared, or a field that's "
        "either misspelled or not valid for its kind, raises an error instead of a "
        "warning.",
    )
    stateful_ingestion: Optional[StatefulStaleMetadataRemovalConfig] = Field(default=None)
```

`aws_connection` is deliberately typed `Optional[Dict[str, Any]]` rather than
`Optional[AwsConnectionConfig]`: pydantic v2 resolves field type annotations at
class-definition time, and `AwsConnectionConfig`
(`datahub.ingestion.source.aws.aws_common`) hard-imports `boto3` at module level
with no lazy variant. Typing the field as a plain dict keeps that import out of
`yaml_source_config.py` entirely; the real `AwsConnectionConfig` is constructed
(and boto3 actually imported) only inside `yaml_source._resolve_aws_connection()`,
called only when an `s3://` path is actually configured — guarded by
`try/except ImportError` pointing at the `s3` extra. `http_connection` needs no
such treatment: `HTTPConnectionConfig`
(`datahub.ingestion.source.common.http_connection_config`) is a plain pydantic
model with no heavy import (`requests` itself is a base acryl-datahub dependency,
so HTTP support needs no extra at all). `loader.py` carries the equivalent
reasoning for `_discover_s3_files`/`_read_s3_bytes` vs. `_read_http_bytes` — see
its module docstring.

`git_info` support: `YamlSource._load_repository_maybe_from_git()` clones (if
`git_info` is set) into a `tempfile.TemporaryDirectory` and calls
`_load_repository(checkout_dir)`, which resolves a relative `path` under the
checkout. The temp directory only needs to live for that one call — unlike ODCS's
lazy per-file scan, `_load_repository` fully materializes the `ParsedRepository`
in memory before returning, so there's no need to keep the checkout open for the
lifetime of the (lazy) `get_workunits_internal` generator. `report.git_checkout`
records the resolved checkout path for troubleshooting. `test_connection()` clones
into a throwaway temp dir when `git_info` is set, instead of the local
exists/is_dir check.

**Verified end-to-end (2026-08-16)** against a real clone of
`https://github.com/aphp/datahub-sample.git` (real network + real GitPython, no
mocks): 8 files scanned, 1702 workunits, 0 failures. Two gotchas discovered in
DataHub core's `GitInfo`/`GitClone` (not our code, but our docs were wrong about
the first one): (1) `GitInfo.clone()` always clones via `repo_ssh_locator`, which
it derives as an SSH URL even for a plain `https://` `repo` — a public repo with
no deploy key needs `repo_ssh_locator` overridden to the HTTPS clone URL, or the
clone attempts SSH auth and fails; (2) on Windows, GitPython's
`kill_after_timeout` (used to enforce `clone_timeout`, default 300s) isn't
supported, so the clone fails outright unless `clone_timeout: null` is set. Both
are now documented in `yaml.md`/`yaml_recipe.yml`/the `git_info` field
description; neither was worked around in code (out of scope for a doc fix — see
`yaml.md` Troubleshooting for the literal error strings).

**HTTP support also verified end-to-end (2026-08-16)**, real network, no mocks:
`path` set to two `https://raw.githubusercontent.com/aphp/datahub-sample/main/...`
URLs (`setup/assets.yml`, `raw-layer/assets.yml`) — 2 files scanned, 294
workunits, 0 failures; `test_connection()` capable. S3 support (`_discover_s3_files`
/`_read_s3_bytes`, paginated prefix listing) is covered only by unit tests against
a hand-rolled fake `AwsConnectionConfig`-shaped object (`tests/unit/test_loader_remote.py`)
— no real S3 bucket was available to verify against; the `boto3`-import-is-lazy
guarantee itself *was* verified for real (`python -c "import
datahub_yaml_source.yaml_source"` with `boto3` uninstalled succeeds; `sys.modules`
confirms `boto3` isn't loaded).

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

## Corrections found during implementation (C1-C10)

C9 (an SDK V2 aspect field with no matching constructor kwarg) and C10 (`array[Urn]`
fields that look like free-text from their names) are documented inline in the Phase 5
implementation history below, where the surrounding context they were found in matters
more than a one-line table row would convey.

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
# 157 passed, 98% coverage, no file below 83% (acryl-datahub==1.7.0.3, post Phase 5)
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
| 4 | Does `docs/sources/yaml/yaml_recipe.yml` stay pointed at the `datahub-sample` root? | maintainer | **Resolved** — points at https://github.com/aphp/datahub-sample; `git_info` (below) lets a recipe clone it automatically instead of requiring a pre-existing local checkout |
| 5 | Should `path` also accept `s3://` / `http(s)://` URIs (not just a local directory or a `git_info` checkout)? | maintainer | **Resolved** — implemented. NOT via `object_store_files.read_file_as_bytes()` as originally proposed: that module transitively imports `AwsConnectionConfig`, which hard-imports `boto3` at module level, so merely importing it would force `boto3` on every user (local/git-only recipes included). Instead: `loader._discover_s3_files`/`_read_s3_bytes` take an already-built `aws_connection` as a loosely-typed `Any` parameter (boto3 only touched inside those two functions); `yaml_source._resolve_aws_connection()` lazily imports `AwsConnectionConfig` and builds it from the config's plain-dict `aws_connection` field, guarded by `try/except ImportError` naming the `s3` extra. HTTP is hand-rolled with `requests` (already a base dependency, so no extra needed) rather than reused from `object_store_files`, for the same reason. `path` accepts a single string or a `List[str]`; HTTP entries must each name a single file (no directory listing), consistent with the original proposal. Verified end-to-end for both (see "Config Structure" above): git test against `github.com/aphp/datahub-sample`, HTTP test against two real `raw.githubusercontent.com` files; S3 covered by unit tests only (no real bucket available). |
