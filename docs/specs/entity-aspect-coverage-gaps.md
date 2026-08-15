# Spec — Entity & Aspect Coverage Gaps in `datahub-yaml-source`

**Reference DataHub version**: `v1.7.0rc1-111-gb9890a0912` (`C:/Users/4087446/Projects/datahub-project/datahub`)
**Connector under spec**: `C:/Users/4087446/Projects/aphp/datahub-yaml-source` (branch `dou-feat-view-application`)
**Status**: DRAFT — awaiting implementation

---

## Context

`_PLANNING.md` describes this connector as generalized to "(almost) the entire DataHub entity
model". Measured against `metadata-models/src/main/resources/entity-registry.yml`, it currently
covers **14 of ~40 user-facing entity types**, and — more importantly — the *aspect* coverage
**within** those 14 kinds is inconsistent in ways that have no design rationale. They are
artifacts of implementation order: each builder was written independently, so whichever
cross-cutting aspect the author happened to need at the time got wired into that one builder
and nowhere else.

Three concrete symptoms, all verified in the code:

1. **`structuredProperties` values can only be assigned to `DATA_PRODUCT`.** The AP-HP metadata
   repo (`C:/Users/4087446/Projects/aphp/datahub-sample`) declares **64 `STRUCTURED_PROPERTY`
   documents**, many with `entityTypes: [dataset]`, but the connector has no way to attach a
   value to a dataset. Only `builders/data_product.py:75-93` implements assignment.
2. **`domains` works on `DATASET` and `DATA_FLOW` but not on `CONTAINER` or `DATA_JOB`.**
   Same for `glossaryTerms` (dataset + data product only) and `applications` (dataset only).
3. **`deprecation` and `institutionalMemory` are supported on nothing at all**, despite being
   valid on almost every entity in the registry and being pure-declarative metadata — exactly
   what a metadata-as-code repo is for.

There is no way to attach metadata to an **individual column**. `schemaMetadata` carries per-field
descriptions and types, but a column cannot be tagged, given a glossary term, or annotated — which
for a health-data platform means no per-column PII tagging from the YAML.

The intended outcome: aspect support becomes a property of the *format*, declared once and applied
uniformly, instead of a per-builder accident; and the connector grows the entity kinds AP-HP
actually needs next.

---

## Problem Statement

Authors of the YAML metadata repo cannot express metadata that DataHub fully supports, and cannot
predict which fields will work on which `kind:` — the same field name is accepted on one document
type and silently rejected on another. Every new aspect currently costs a bespoke edit to one
builder, one model, the JSON schema generator, the markdown doc generator, the fixture tree and the
golden file (~20 files, per commit `52ad86f`), so the inconsistency compounds with each addition.

---

## Goals

1. **Uniform cross-cutting aspects.** `owners`, `tags`, `glossaryTerms`, `domains`, `applications`,
   `links`, `deprecation`, `structuredProperties`, `subTypes` behave identically on every `kind:`
   where the DataHub entity registry permits that aspect — and are rejected with a clear error where
   it does not.
2. **Marginal cost of a new aspect drops to one line.** Adding a cross-cutting aspect to a kind
   becomes an entry in a registry-derived allowlist, not a new code path in a builder.
3. **Column-level metadata becomes expressible** — tags, glossary terms, structured properties and
   deprecation on an individual `schema.fields[]` entry.
4. **Four new entity kinds ship**: `DASHBOARD`, `CHART`, `QUERY`, `INCIDENT`, `DOCUMENT`.
5. **Declared capabilities match actual output.** The `@capability` decorators on
   `yaml_source.py:48-55` under-report what the connector emits (`DOMAINS`, `GLOSSARY_TERMS`,
   `PLATFORM_INSTANCE`, `DESCRIPTIONS`, `DATA_PROFILING`, `USAGE_STATS`, `OPERATION_CAPTURE` are all
   produced but not declared).

---

## Non-Goals

| Not doing | Why |
|---|---|
| `editableDatasetProperties`, `editableSchemaMetadata`, `editable*Properties` | The `editable*` aspects are UI-owned by design. A connector writing them would fight the UI on every run. Column-level metadata goes on `schemaField` entity aspects instead (see P1-3). |
| `testResults`, `incidentsSummary`, `partitionsSummary`, `assetSettings`, `browsePaths` (v1), `siblings`, `embed`, `access`, `icebergCatalogInfo`, `aliases`, `logicalParent` | System-computed, platform-specific, or superseded. Nothing to hand-author. |
| Generating `datasetProfile` / `datasetUsageStatistics` / `operation` | Already reachable via the `aspectName:` raw-aspect passthrough, which the sample repo uses 32 times. No new mechanism needed. |
| `CORP_USER` / `CORP_GROUP` | Deferred by explicit decision. Documented in Future Considerations because `owners:` today points at `corpuser` URNs that are never created — the gap is real, just not now. |
| `DATA_CONTRACT` | Deferred by explicit decision, despite being a natural pairing with the existing `ASSERTION` support. |
| `FORM` assignment, ML entities, `ER_MODEL_RELATIONSHIP`, `BUSINESS_ATTRIBUTE` definitions | No current AP-HP use case. Future Considerations. |
| v1.7 entities `SEMANTIC_MODEL`, `METRIC`, `SERVICE`, `API`, `REPOSITORY`, `AI_AGENT`, `AGENT_SKILL` | Brand new in this DataHub release; premature to encode in a stable authoring format. |
| SQL parsing / lineage inference | Deliberate existing design: lineage is fully YAML-declared (`_PLANNING.md`, "Key simplification"). `parse_view_lineage=False` at `builders/dataset.py:185` stays. |

---

## Current State — Verified Coverage Matrix

`✓` emitted today · `✗` valid per entity-registry but not emitted · `—` not valid on that entity

| Aspect | DATASET | CONTAINER | DATA_FLOW | DATA_JOB | DATA_PRODUCT | DOMAIN | APPLICATION | GLOSSARY_TERM | GLOSSARY_NODE | TAG | ASSERTION |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ownership` | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `globalTags` | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✗ | ✗ | ✗ | — | ✗ |
| `glossaryTerms` | ✓ | ✗ | ✗ | ✗ | ✓ | — | ✗ | — | — | — | — |
| `domains` | ✓ | ✗ | ✓ | ✗ | ✓ | — | ✗ | ✗ | ✗ | — | — |
| `applications` | ✓ | ✗ | ✗ | ✗ | ✗ | — | — | ✗ | — | — | — |
| `deprecation` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — | ✗ | — | ✗ | — |
| `institutionalMemory` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — | — |
| `structuredProperties` | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | — | — |
| `subTypes` | ✓ | ✓ | ✗ | ✓ | ✗ | — | ✗ | ✗ | ✗ | — | — |
| `container` | ✓ | ✓ | ✗ | ✗ | — | — | — | — | — | — | — |
| `dataPlatformInstance` | ✓ | ✓ | ✓ | ✗ | — | — | — | — | — | — | ✗ |

Entity-specific gaps inside supported kinds:

| Kind | Missing |
|---|---|
| `DOMAIN` | `domainProperties.parentDomain` (**nested domains impossible today**), `displayProperties` (icon/colour) |
| `GLOSSARY_TERM` | `glossaryRelatedTerms` (`isA`/`hasA`/`relatedTerms`/`values`) — the relational core of a glossary; `termSource`/`sourceRef`/`sourceUrl`; `customProperties` |
| `TAG` | `tagProperties.colorHex` |
| `DATA_JOB` | `dataJobInputOutput.inputDatajobs` (**job→job edges — DAG dependencies cannot be declared**), `externalUrl`, `customProperties` |
| `DATA_FLOW` | `container` (a flow cannot live in a container) |
| `ASSERTION` | assertion types `VOLUME`, `DATA_SCHEMA`, `CUSTOM` (only `FRESHNESS`/`SQL`/`FIELD` today, per `builders/assertion.py`); `assertionActions`, `assertionNote`, `assertionInfo.description` |
| `dataPlatformInstance` **entity** | The *aspect* is emitted, but the entity itself never gets `dataPlatformInstanceProperties` — instances appear unnamed in the UI |
| raw-aspect passthrough | Entity reference limited to `dataset` / `assertionUrn` / `dataProcessInstanceUrn` (`models.py:469-471`) — no generic `entityUrn:` |

---

## User Stories

**Metadata author (AP-HP data steward)**
- As a data steward, I want to attach a structured property value to a dataset, so that the 64 property definitions in `setup/` are usable on the assets they were defined for.
- As a data steward, I want to mark a dataset deprecated with a note and a decommission date, so that consumers stop building on it before it disappears.
- As a data steward, I want to link a dataset to its confluence page and its dbt docs, so that the catalog entry is a starting point rather than a dead end.
- As a data steward, I want to tag a single column as PII, so that column-level governance is declared in git alongside the schema.
- As a data steward, I want to nest domains (`Imagerie` under `Données cliniques`), so that the domain tree matches the organisation.
- As a data steward, I want `glossaryTerms` and `domains` on a `CONTAINER`, so that a whole schema can be classified without repeating myself on all 88 datasets.

**Pipeline owner**
- As a pipeline owner, I want to declare that job B depends on job A, so that the DAG shows in DataHub even where no dataset sits between the two steps.
- As a pipeline owner, I want a volume assertion (row count within bounds), so that our quality layer covers volume and not only freshness/SQL/field checks.

**Format maintainer (this repo)**
- As the connector maintainer, I want a single declaration point for which aspects a kind accepts, so that a new aspect is one entry rather than fourteen edits.
- As the connector maintainer, I want an unsupported field on a kind to raise a clear validation error, so that authors are not silently ignored.

---

## Architecture — Shared Common-Metadata Block

The root cause of the matrix above is that each builder assembles its own aspects. The fix is one
mixin on the model side and one emitter on the builder side, driven by an allowlist transcribed
from `entity-registry.yml`.

### 1. `models.py` — `CommonMetadataMixin`

```python
class LinkDoc(BaseModel):                     # -> institutionalMemory
    url: str
    description: Optional[str] = None

class DeprecationDoc(BaseModel):              # -> deprecation
    deprecated: bool = True
    note: Optional[str] = None
    decommissionTime: Optional[int] = None
    actor: Optional[str] = None

class CommonMetadataMixin(BaseModel):
    owners: Optional[OwnersField] = None
    tags: Optional[StringList] = None
    glossaryTerms: Optional[StringList] = None
    domains: Optional[str] = None
    applications: Optional[StringList] = None
    links: Optional[List[LinkDoc]] = None
    deprecation: Optional[DeprecationDoc] = None
    structuredProperties: Optional[Dict[str, Any]] = None
    subTypes: Optional[SubTypesField] = None
```

Every entity doc model in `models.py` inherits it, and the per-kind fields that duplicate it
(`DatasetDoc.owners`, `DatasetDoc.tags`, `ContainerDoc.owners`, …) are removed. `DatasetDoc.applications`
and `DataProductDoc.structuredProperties` are absorbed — **no YAML in the sample repo changes shape**,
which is the compatibility requirement.

### 2. `builders/common.py` — registry-derived allowlist + emitter

```python
# Transcribed from metadata-models/src/main/resources/entity-registry.yml (v1.7.0).
COMMON_ASPECTS_BY_KIND: Dict[str, FrozenSet[str]] = {
    "DATASET":  frozenset({"owners","tags","glossaryTerms","domains","applications",
                           "links","deprecation","structuredProperties","subTypes"}),
    "CONTAINER": frozenset({...}),
    "TAG":       frozenset({"owners","deprecation"}),
    ...
}

def build_common_aspects(kind, entity_urn, doc, index, report) -> Iterable[MetadataWorkUnit]:
    """Emit every cross-cutting aspect declared on `doc` and permitted for `kind`."""
```

A Pydantic model-level validator rejects a common field set on a kind whose allowlist omits it
(`glossaryTerms` on a `TAG`, say) rather than emitting an aspect the GMS will refuse.

### 3. Interaction with SDK V2

SDK V2 (`datahub/sdk/_shared.py`) provides mixins for `owners`, `tags`, `terms`, `domain`, `links`,
`subtype`, `structured_properties`, `container`, `platform_instance` — but **not** `deprecation` and
**not** `applications`. So for SDK-backed kinds (`DATASET`, `DATA_FLOW`, `DATA_JOB`, `TAG`,
`GLOSSARY_*`, and the new `DASHBOARD`/`CHART`/`DOCUMENT`) the split is:

- pass what the constructor accepts natively (`owners=`, `tags=`, `terms=`, `domain=`, `links=`, `subtype=`);
- route the rest through `extra_aspects=`, exactly as `builders/dataset.py:186-188` already does for `ApplicationsClass`.

Two mechanical traps, both verified:

> **Do not call `HasStructuredProperties.set_structured_property()`.** It stamps
> `make_ts_millis(datetime.now())` into `created`/`lastModified` (`sdk/_shared.py:917-938`), which makes
> golden files non-deterministic. Build `StructuredPropertiesClass` directly, the way
> `builders/data_product.py:82-93` already does.

> **`gen_containers()` takes no `domain` / `terms` / `structuredProperties` / `deprecation` arguments.**
> `CONTAINER`'s extra aspects must be emitted as follow-up MCPs after the `gen_containers()` call —
> the same shape `builders/container.py:96-99` already uses for the multi-owner case.

### 4. Per-addition file checklist

Commit `52ad86f` (`viewProperties` + `applications`) establishes the footprint every addition must
cover. Any new field or kind touches:

`src/datahub_yaml_source/models.py` · the relevant `builders/*.py` · `urns.py` (new URN helper) ·
`loader.py` + `yaml_source.py` + `yaml_source_report.py` (new kinds only) ·
`scripts/generate_json_schema.py` → regenerate `docs/sources/yaml/schema/yaml-metadata.schema.json` ·
`scripts/generate_markdown_docs.py` → regenerate `docs/sources/yaml/reference.md` · `docs/sources/yaml/yaml.md` ·
`tests/unit/test_models.py` + `tests/unit/test_builders_*.py` ·
`tests/integration/yaml_source/resources/**` + `yaml_source_mces_golden.json`

`tests/unit/test_json_schema_generation.py` and `test_markdown_docs_generation.py` assert the
generated artifacts are in sync, so skipping the regeneration step fails the suite.

---

## Requirements

### Phase 1 — Cross-cutting parity + refactor (P0)

| # | Requirement | Acceptance criteria |
|---|---|---|
| 1.1 | `CommonMetadataMixin` + `COMMON_ASPECTS_BY_KIND` + `build_common_aspects()` | Every kind's builder obtains cross-cutting aspects from the shared helper; no builder assembles `OwnershipClass`/`GlobalTagsClass`/`GlossaryTermsClass`/`DomainsClass` inline any more. Existing golden file is unchanged except for the newly-added aspects. |
| 1.2 | `structuredProperties` assignable on every kind the registry allows | Given a `DATASET` with `structuredProperties: {org.example.legalBasis: consent}`, a `structuredProperties` MCP is emitted with a deterministic (zero) audit stamp. Undeclared property → dangling-reference warning, as `data_product.py:76-81` does today. |
| 1.3 | `deprecation` on every kind the registry allows | `deprecation: {note: "...", decommissionTime: 1767225600000}` emits `DeprecationClass`. `deprecated: false` still emits (un-deprecating is an intentional act). |
| 1.4 | `institutionalMemory` via `links:` | A list of `{url, description}` emits `InstitutionalMemoryClass` with a zero audit stamp (`sdk/_shared.py:702-706` already defaults this way). |
| 1.5 | `domains` on `CONTAINER` + `DATA_JOB`; `glossaryTerms` on `CONTAINER`/`DATA_FLOW`/`DATA_JOB`; `applications` beyond `DATASET`; `ownership` on `DOMAIN`/`APPLICATION`/`GLOSSARY_*`/`TAG`/`ASSERTION`; `globalTags` on `APPLICATION`/`GLOSSARY_*`/`ASSERTION` | Filling the `✗` cells of the matrix. Each verified by a unit test asserting the aspect appears in the workunit stream, and by a fixture in the integration tree. |
| 1.6 | `subTypes` on `DATA_FLOW`, `DATA_PRODUCT`, `APPLICATION`, `GLOSSARY_*` | Uses the existing `normalize_sub_types()`. Note `builders/dataset.py:162-163` currently drops all but the first subtype — fix to pass the full list, since subtypes are additive (`standards/main.md` §4.4). |
| 1.7 | Nested domains: `DomainDoc.parentDomain` | `domainProperties.parentDomain` set; domains topologically sorted parent-before-child, reusing the Kahn implementation in `builders/container.py:20-58`. Dangling parent → warning. |
| 1.8 | `glossaryRelatedTerms` on `GLOSSARY_TERM` | `isA`/`hasA`/`relatedTerms`/`values`/`relatedValues`, each a list of term ids resolved through `index.has_glossary_term()`. |
| 1.9 | `tagProperties.colorHex`; `displayProperties` on `DOMAIN`/`GLOSSARY_*`; `termSource`/`sourceRef`/`sourceUrl` on `GLOSSARY_TERM` | Straight field pass-through. |
| 1.10 | `DATA_PLATFORM_INSTANCE` gains `dataPlatformInstanceProperties` | New optional `instances:` block on `DataPlatformDoc`, or a `DATA_PLATFORM_INSTANCE` kind — implementer's call, documented in the ADR. Instances currently render unnamed in the UI. |
| 1.11 | Capability decorators corrected | `DOMAINS`, `GLOSSARY_TERMS`, `PLATFORM_INSTANCE`, `DESCRIPTIONS`, `DATA_PROFILING`, `USAGE_STATS`, `OPERATION_CAPTURE` added to `yaml_source.py`. Each declared capability demonstrably produces output from the integration fixture tree. |
| 1.12 | Report counters for the new aspects | `yaml_source_report.py` gains counters in the existing style, so the ingestion report shows what was emitted. |

### Phase 2 — Pipeline & assertion completeness (P0)

| # | Requirement | Acceptance criteria |
|---|---|---|
| 2.1 | `DATA_JOB.inputDataJobs` | `dataJobInputOutput.inputDatajobs` populated from a list of `DataFlowJobRef` (the model already exists, `models.py:368-371`). Enables DAG edges with no intervening dataset. |
| 2.2 | `DATA_JOB` gains `externalUrl`, `properties`, `container` | Parity with `DATA_FLOW`. |
| 2.3 | `DATA_FLOW` gains `container` | A pipeline can sit inside a container. |
| 2.4 | Assertion types `VOLUME`, `DATA_SCHEMA`, `CUSTOM` | Extends the `type` discriminator in `builders/assertion.py`. `VOLUME` covers `RowCountTotal`/`RowCountChange`. `DATASET` is **not** added — deprecated in `AssertionType.pdl:13`. |
| 2.5 | `assertionInfo.description`, `assertionNote`, `assertionActions` | Declarative on-failure actions. |
| 2.6 | Generic raw-aspect entity reference | `RawAspectDoc` accepts `entityUrn:` alongside the three typed refs, so a raw aspect can target any entity. The per-aspect builder registry in `raw_aspect.py` stays — the module docstring's reasoning (nested objects need real aspect classes, not dicts) is correct and must not be replaced with a generic constructor. |

### Phase 3 — Column-level metadata (P1)

| # | Requirement | Acceptance criteria |
|---|---|---|
| 3.1 | `schema.fields[]` accepts `tags`, `glossaryTerms`, `structuredProperties`, `deprecation` | Emitted as aspects on the **`schemaField` entity URN** (`make_schema_field_urn()`, already imported in `builders/dataset.py:3`) — *not* as `editableSchemaMetadata`. The registry permits `globalTags`, `glossaryTerms`, `structuredProperties`, `deprecation`, `documentation`, `businessAttributes` on `schemaField`. |
| 3.2 | Field-level references validated | An undeclared tag/term on a column produces the same dangling-reference warning as at entity level, naming the column. |
| 3.3 | Emission order | `schemaField` MCPs emitted after the parent dataset's `schemaMetadata`, so the fields exist when the annotations land. |

### Phase 4 — New entity kinds (P1)

| # | Kind | Aspects | Mechanism |
|---|---|---|---|
| 4.1 | `DASHBOARD` | `dashboardInfo` (`title`, `description`, `dashboardUrl`, `charts`, `datasets`, `dashboards`), `subTypes`, `container`, `dataPlatformInstance` + all common | `datahub.sdk.Dashboard` — has `input_datasets=`, `charts=`, `dashboards=` (`sdk/dashboard.py:84-86`). Audit stamps default to `time=0`, so output stays deterministic. |
| 4.2 | `CHART` | `chartInfo` (`title`, `description`, `chartUrl`, `inputs`, `type`), `subTypes`, `container` + all common | `datahub.sdk.Chart` |
| 4.3 | `QUERY` | `queryProperties` (`statement`, `language`, `source`, `name`, `description`), `querySubjects` (datasets/fields the query touches), `subTypes` | Raw MCP — no SDK V2 wrapper. Curated SQL attached to datasets, a fit for the sharing layer. |
| 4.4 | `INCIDENT` | `incidentInfo` (`type`, `title`, `description`, `entities`, `status`, `priority`, `assignees`), `incidentExternalLinks`, `incidentNotes` | Raw MCP. Complements the existing `observability-layer` + `ASSERTION_RUN_EVENT` usage. |
| 4.5 | `DOCUMENT` | `documentInfo`, `documentSettings`, `subTypes` + common | `datahub.sdk.Document`. Wiki-as-code — new in v1.7, so gate on confirming the aspect is stable in the target GMS. |

New kinds each need: an entry in `ENTITY_DOC_TYPES_BY_KIND` / `EntityDoc` (`models.py:474-506`), a
`ParsedRepository` list + `ReferenceIndex` entry, a URN helper in `urns.py`, a report counter, and a
slot in the fixed emission order in `yaml_source.py:128-206` (parents before children:
`CHART` before `DASHBOARD`; `QUERY`/`INCIDENT` after `DATASET`).

### Future Considerations (P2 — design for, do not build)

`CORP_USER` / `CORP_GROUP` (`owners:` currently references `corpuser` URNs that are never created —
no name, email, or group membership reaches DataHub); `DATA_CONTRACT` (would reference the
already-supported `ASSERTION` entities); ML entities (`MLMODEL`, `MLMODEL_GROUP`, `MLFEATURE_TABLE`,
`MLFEATURE`, `MLPRIMARY_KEY` — SDK V2 exists for the first two); `ER_MODEL_RELATIONSHIP`;
`BUSINESS_ATTRIBUTE` definitions + the `businessAttributes` aspect on `schemaField`; `FORM` +
`dynamicFormAssignment`; `NOTEBOOK`; `VERSION_SET` / `versionProperties`; custom `OWNERSHIP_TYPE`
(today `OwnerEntry.type` is a free-text string mapped onto the built-in `OwnershipType` enum —
custom types need `typeUrn`); v1.7 entities `SEMANTIC_MODEL`, `METRIC`, `SERVICE`, `API`,
`REPOSITORY`, `AI_AGENT`, `AGENT_SKILL`.

The `CommonMetadataMixin` + allowlist design is what makes each of these cheap later: a new kind
inherits the full cross-cutting surface for free and declares only its own properties aspect.

---

## Success Metrics

**Leading (measurable at merge)**
- Cross-cutting aspect matrix has **zero `✗` cells** for the nine common aspects across the 14 existing kinds.
- Every `STRUCTURED_PROPERTY` in `datahub-sample` with `entityTypes: [dataset]` can be assigned on a dataset — spot-check ≥5 of the 64.
- Unit coverage on new/changed builder code ≥80% (existing bar, `_PLANNING.md` step 8).
- `check-capabilities` shows every declared `@capability` producing output from the fixture tree.

**Lagging**
- A new cross-cutting aspect can be added in ≤3 files (model field + allowlist entry + regenerated artifacts), versus ~20 today.
- `datahub-sample` re-ingests with zero dangling-reference warnings.

---

## Open Questions

| # | Question | Owner | Blocking? |
|---|---|---|---|
| 1 | `DATA_PLATFORM_INSTANCE`: nested `instances:` under `DataPlatformDoc`, or its own top-level kind? | maintainer | No — decide during 1.10 |
| 2 | Should an unsupported common field on a kind be a hard validation error (rejects the file) or a warning-and-skip? Everything else in the connector is warning-and-skip (`fail_on_unresolved_reference` gates the strict mode), but a *schema* mistake differs from a *reference* mistake. | maintainer | **Yes** — shapes 1.1 |
| 3 | Is the target GMS actually on v1.7? `DOCUMENT`, `applications`, and `displayProperties` are recent; emitting them against an older GMS yields rejected MCPs. | AP-HP platform team | **Yes** for 4.5, no for Phases 1–3 |
| 4 | Does `docs/sources/yaml/yaml_recipe.yml` stay pointed at the full `datahub-sample` root (currently modified from `observability-layer` to the repo root, uncommitted)? | maintainer | No |
| 5 | Column-level annotation on `schemaField` entities requires those URNs to resolve in the target GMS. Confirm the deployment indexes `schemaField` entities. | AP-HP platform team | No — Phase 3 only |

---

## Timeline / Phasing

No hard external deadline. Sequence is dictated by dependency, not calendar:

1. **Phase 1** must land first — it is the refactor everything else rides on, and it touches all 14 builders plus the golden file. Landing it alongside other work would make the golden diff unreadable.
2. **Phase 2** is independent of Phase 1 and could run in parallel, but sequencing it after keeps golden-file churn serialized.
3. **Phase 3** depends on nothing but is the largest single behavioural change to `builders/dataset.py`.
4. **Phase 4** depends on Phase 1 (new kinds should inherit the common mixin from birth, not be retrofitted).

Each phase is independently shippable and separately reviewable against the connector standards.

---

## Verification

Run from the repo root (`C:/Users/4087446/Projects/aphp/datahub-yaml-source`).

**1. Unit tests** — the existing files map to the work: `test_models.py` (mixin validation, allowlist
rejection), `test_builders_core.py` / `test_builders_dataset.py` / `test_builders_extended.py` /
`test_builders_flow_job.py` (per-aspect emission), `test_urns.py` (new URN helpers), `test_loader.py`
(new kinds parsed).

```bash
python -m pytest tests/unit -q
```

**2. Regenerate the derived artifacts** — non-optional; two unit tests assert they are in sync.

```bash
python scripts/generate_json_schema.py      # -> docs/sources/yaml/schema/yaml-metadata.schema.json
python scripts/generate_markdown_docs.py    # -> docs/sources/yaml/reference.md
python -m pytest tests/unit/test_json_schema_generation.py tests/unit/test_markdown_docs_generation.py -q
```

**3. Extend the integration fixture tree, then refresh the golden file.** Every new aspect and kind
needs a fixture. Existing tree: `tests/integration/yaml_source/resources/{setup,raw-layer,transform-layer,view-layer,dataproduct-layer,quality-layer,observability-layer}/`.

```bash
python -m pytest tests/integration -q
python -m pytest tests/integration -q --update-golden-files   # then review the diff by hand
```

Review the golden diff aspect by aspect — it is the primary evidence that Phase 1's refactor changed
*only* what was intended. A pure refactor step should produce an empty diff before the new aspects are
wired in; make that an intermediate checkpoint.

**4. Real ingest against the AP-HP repo** — 88 datasets, 64 structured properties, 12 containers,
39 data jobs, the realistic load.

```bash
datahub ingest -c docs/sources/yaml/yaml_recipe.yml --dry-run
```

Then a real run against a live GMS, checking the ingestion report for `warnings` /
`dangling_references` / `failures` at zero, and confirming in the UI: a dataset with a structured
property value, a deprecated dataset, a dataset with links, a nested domain tree, a PII-tagged
column, and a job→job DAG edge.

**5. Standards review** — re-run `/datahub-skills:connector-review` on the branch before merge. The
capability-declaration fix (1.11) and the report-counter additions (1.12) are direct responses to
that skill's checklist; Phase 1's removal of per-builder aspect assembly addresses its DRY criteria.
