# Spec — Entity & Aspect Coverage Gaps in `datahub-yaml-source`

**Reference DataHub version**: `v1.7.0rc1-111-gb9890a0912` (`C:/Users/4087446/Projects/datahub-project/datahub`)
**Connector under spec**: `C:/Users/4087446/Projects/aphp/datahub-yaml-source` (branch `main`)
**Status**: **IMPLEMENTED** (2026-08-15) — every Phase below shipped. This document is kept as the
original problem statement and requirements; see `_PLANNING.md`'s "Coverage extension" section for
the as-built architecture, the corrections found during implementation (C1-C8), and what deviated
from this spec's own sketches. Status annotations (`✅ Done`, `⏸ Deferred`) have been added inline
below rather than rewriting the spec into a report.

---

## Implementation Summary

Shipped across 6 commits on `main`: `367cbfb` (Phase 1 refactor), `4c05eeb` (Phase 3, landed early
since it was cheap once Phase 1's dispatcher existed), `f4ed4cc`/`c63997a`/`24490ef`/`19bafcd`/
(unhashed at merge time) (Phase 4, one commit per kind: `CHART`, `DASHBOARD`, `QUERY`, `INCIDENT`,
`DOCUMENT`). Phase 2 landed opportunistically inside the Phase 1 commit once its corrections (C1-C3)
showed it was nearly free. Final state: **140 tests, 97% coverage**, zero dangling references / unknown
fields on the integration fixture tree, `acryl-datahub==1.7.0.3`.

**One architecture decision diverged from this spec's own sketch**: the "Shared Common-Metadata
Block" section below sketches a single flat `CommonMetadataMixin` plus a runtime
`COMMON_ASPECTS_BY_KIND` allowlist. The actual implementation (`_PLANNING.md`, Decision D1) uses nine
separate one-field mixins (`HasOwners`, `HasTags`, `HasTerms`, `HasDomain`, `HasApplications`,
`HasLinks`, `HasDeprecation`, `HasStructuredProps`, `HasSubTypes`) instead, so that per-kind validity
is static — a field either exists on a kind's Pydantic model or it doesn't, with no separate
allowlist to keep in sync. The rest of this spec's architecture section (the SDK V2 traps, the
`build_common_aspects()` emission split, the per-addition file checklist) matches what was built,
just realized as two dispatchers (`common_sdk_kwargs()`/`common_aspect_mcps()`) rather than one.

---

## Context

`_PLANNING.md` describes this connector as generalized to "(almost) the entire DataHub entity
model". Measured against `metadata-models/src/main/resources/entity-registry.yml`, it covered
**14 of ~40 user-facing entity types** at the time this spec was written (now 19, after this spec's
Phase 4 shipped `CHART`/`DASHBOARD`/`QUERY`/`INCIDENT`/`DOCUMENT`) — and, more importantly, the
*aspect* coverage **within** those 14 kinds was inconsistent in ways that had no design rationale. They
were artifacts of implementation order: each builder was written independently, so whichever
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

1. **✅ Done.** **Uniform cross-cutting aspects.** `owners`, `tags`, `glossaryTerms`, `domains`,
   `applications`, `links`, `deprecation`, `structuredProperties`, `subTypes` behave identically on
   every `kind:` where the DataHub entity registry permits that aspect — and simply don't exist as a
   field where it does not (a warning on `extra="allow"`, not a rejection — see D2 in `_PLANNING.md`).
2. **✅ Done**, via granular mixins rather than the allowlist sketched here (D1). **Marginal cost of
   a new aspect drops to ~3 files** (model field / mixin, `common_sdk_kwargs()`/`common_aspect_mcps()`
   dispatch, regenerated docs), not a new code path per builder.
3. **✅ Done.** **Column-level metadata is expressible** — tags, glossary terms, structured
   properties, and deprecation on an individual `schema.fields[]` entry (Phase 3).
4. **✅ Done. Five new entity kinds shipped**: `CHART`, `DASHBOARD`, `QUERY`, `INCIDENT`, `DOCUMENT`
   (Phase 4).
5. **✅ Done.** **Declared capabilities match actual output.** `DOMAINS`, `GLOSSARY_TERMS`,
   `PLATFORM_INSTANCE`, `DESCRIPTIONS`, `DATA_PROFILING`, `USAGE_STATS`, `OPERATION_CAPTURE` all added
   to `yaml_source.py`'s `@capability` decorators.

---

## Non-Goals

| Not doing | Why |
|---|---|
| `editableDatasetProperties`, `editableSchemaMetadata`, `editable*Properties` | The `editable*` aspects are UI-owned by design. A connector writing them would fight the UI on every run. Column-level metadata goes on `schemaField` entity aspects instead (see P1-3). |
| `testResults`, `incidentsSummary`, `partitionsSummary`, `assetSettings`, `browsePaths` (v1), `siblings`, `embed`, `access`, `icebergCatalogInfo`, `aliases`, `logicalParent` | System-computed, platform-specific, or superseded. Nothing to hand-author. |
| Generating `datasetProfile` / `datasetUsageStatistics` / `operation` | Already reachable via the `aspectName:` raw-aspect passthrough, which the sample repo uses 32 times. No new mechanism needed. |
| `CORP_USER` / `CORP_GROUP` | Deferred by explicit decision. Documented in Future Considerations because `owners:` today points at `corpuser` URNs that are never created — the gap is real, just not now. |
| `DATA_CONTRACT` | Deferred by explicit decision, despite being a natural pairing with the existing `ASSERTION` support. |
| `FORM` assignment, `ER_MODEL_RELATIONSHIP`, `BUSINESS_ATTRIBUTE` definitions | No current AP-HP use case. Future Considerations. |
| ~~ML entities; v1.7 entities `SEMANTIC_MODEL`, `METRIC`, `SERVICE`, `API`, `REPOSITORY`, `AI_AGENT`, `AGENT_SKILL`~~ | **Superseded — shipped in Phase 5.** All 12 kinds this row deferred were built; see `docs/specs/ml-semantic-ai-catalog-entities.md` and `_PLANNING.md`'s "ML / semantic / software-catalog entities — Phase 5" section for the coverage matrix, decisions, and verified SDK facts. |
| SQL parsing / lineage inference | Deliberate existing design: lineage is fully YAML-declared (`_PLANNING.md`, "Key simplification"). `parse_view_lineage=False` at `builders/dataset.py:185` stays. |

---

## Original Coverage Matrix (pre-implementation baseline)

This is the state the spec was written against — kept for context on the problem being solved, not
the current state. **Every `✗` cell below is now `✓`**; see `_PLANNING.md`'s mixin→kind matrix
(Architecture § "Cross-cutting aspect architecture") for the current, fully-populated version, which
also covers the five new kinds this spec added.

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

Entity-specific gaps inside supported kinds, as they stood before this spec (status now noted):

| Kind | Missing (then) | Status |
|---|---|---|
| `DOMAIN` | `domainProperties.parentDomain` (**nested domains impossible today**), `displayProperties` (icon/colour) | ✅ Done (1.7, 1.9) |
| `GLOSSARY_TERM` | `glossaryRelatedTerms` (`isA`/`hasA`/`relatedTerms`/`values`) — the relational core of a glossary; `termSource`/`sourceRef`/`sourceUrl`; `customProperties` | ✅ Done (1.8) |
| `TAG` | `tagProperties.colorHex` | ✅ Done (1.9) |
| `DATA_JOB` | `dataJobInputOutput.inputDatajobs` (**job→job edges — DAG dependencies cannot be declared**), `externalUrl`, `customProperties` | ✅ Done (2.1, 2.2) |
| `DATA_FLOW` | `container` (a flow cannot live in a container) | ✅ Done (2.3) |
| `ASSERTION` | assertion types `VOLUME`, `DATA_SCHEMA`, `CUSTOM` (only `FRESHNESS`/`SQL`/`FIELD` then); `assertionActions`, `assertionNote`, `assertionInfo.description` | ✅ Done (2.4, 2.5) |
| `dataPlatformInstance` **entity** | The *aspect* is emitted, but the entity itself never gets `dataPlatformInstanceProperties` — instances appear unnamed in the UI | ⏸ Deferred by decision (D3, 1.10) |
| raw-aspect passthrough | Entity reference limited to `dataset` / `assertionUrn` / `dataProcessInstanceUrn` — no generic `entityUrn:` | 🟡 Partial (2.6): the `entityUrn:` field exists on the model, but no builder registers a use for it yet — no concrete aspect in this round needed it |

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

### Phase 1 — Cross-cutting parity + refactor (P0) — ✅ Done (`367cbfb`)

| # | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| 1.1 | `CommonMetadataMixin` + `COMMON_ASPECTS_BY_KIND` + `build_common_aspects()` | Every kind's builder obtains cross-cutting aspects from the shared helper; no builder assembles `OwnershipClass`/`GlobalTagsClass`/`GlossaryTermsClass`/`DomainsClass` inline any more. Existing golden file is unchanged except for the newly-added aspects. | ✅ Built as 9 granular mixins + `common_sdk_kwargs()`/`common_aspect_mcps()` (D1) instead of one flat mixin + allowlist. Golden diff was empty before new fixture content was added — checkpoint met. |
| 1.2 | `structuredProperties` assignable on every kind the registry allows | Given a `DATASET` with `structuredProperties: {org.example.legalBasis: consent}`, a `structuredProperties` MCP is emitted with a deterministic (zero) audit stamp. Undeclared property → dangling-reference warning. | ✅ Done, via `HasStructuredProps` + `build_structured_properties_aspect()`, always through `extra_aspects=` (C4). |
| 1.3 | `deprecation` on every kind the registry allows | `deprecation: {note: "...", decommissionTime: 1767225600000}` emits `DeprecationClass`. `deprecated: false` still emits. | ✅ Done, via `HasDeprecation`. Found and fixed a real Avro trap along the way (C6: `note` is non-nullable despite the `Optional[str]` stub). |
| 1.4 | `institutionalMemory` via `links:` | A list of `{url, description}` emits `InstitutionalMemoryClass` with a zero audit stamp. | ✅ Done, via `HasLinks`. |
| 1.5 | `domains` on `CONTAINER` + `DATA_JOB`; `glossaryTerms` on `CONTAINER`/`DATA_FLOW`/`DATA_JOB`; `applications` beyond `DATASET`; `ownership` on `DOMAIN`/`APPLICATION`/`GLOSSARY_*`/`TAG`/`ASSERTION`; `globalTags` on `APPLICATION`/`GLOSSARY_*`/`ASSERTION` | Filling the `✗` cells of the matrix. Each verified by a unit test and an integration fixture. | ✅ Done — every `✗` cell filled, see `_PLANNING.md`'s matrix. |
| 1.6 | `subTypes` on `DATA_FLOW`, `DATA_PRODUCT`, `APPLICATION`, `GLOSSARY_*` | Uses the existing `normalize_sub_types()`. Fix the multi-subtype-drops-all-but-first bug — subtypes are additive. | ✅ Done (C5): `subtype=` used only for a single value; `SubTypesClass(typeNames=[...])` via `extra_aspects` for more than one. |
| 1.7 | Nested domains: `DomainDoc.parentDomain` | `domainProperties.parentDomain` set; domains topologically sorted parent-before-child. Dangling parent → warning. | ✅ Done: `topological_sort_domains()`, mirroring the existing container Kahn implementation. |
| 1.8 | `glossaryRelatedTerms` on `GLOSSARY_TERM` | `isA`/`hasA`/`relatedTerms`/`values`/`relatedValues`, each a list of term ids resolved through `index.has_glossary_term()`. | ✅ Done — mapped onto `GlossaryTerm`'s native SDK kwargs. |
| 1.9 | `tagProperties.colorHex`; `displayProperties` on `DOMAIN`/`GLOSSARY_*`; `termSource`/`sourceRef`/`sourceUrl` on `GLOSSARY_TERM` | Straight field pass-through. | ✅ Done. `icon` deliberately not implemented (no natural single-field YAML shorthand for `IconPropertiesClass`'s library/name/style triple). |
| 1.10 | `DATA_PLATFORM_INSTANCE` gains `dataPlatformInstanceProperties` | New optional `instances:` block on `DataPlatformDoc`, or a `DATA_PLATFORM_INSTANCE` kind. | ⏸ **Deferred by decision D3** — see Open Question 1's resolution. Instances still render unnamed in the UI. |
| 1.11 | Capability decorators corrected | `DOMAINS`, `GLOSSARY_TERMS`, `PLATFORM_INSTANCE`, `DESCRIPTIONS`, `DATA_PROFILING`, `USAGE_STATS`, `OPERATION_CAPTURE` added to `yaml_source.py`. Each declared capability demonstrably produces output from the integration fixture tree. | ✅ Done — all 7 added. |
| 1.12 | Report counters for the new aspects | `yaml_source_report.py` gains counters in the existing style. | ✅ Done — plus `unknown_fields` (D2), not originally scoped here but added alongside. |

### Phase 2 — Pipeline & assertion completeness (P0) — ✅ Done (opportunistically, inside `367cbfb`)

| # | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| 2.1 | `DATA_JOB.inputDataJobs` | `dataJobInputOutput.inputDatajobs` populated from a list of `DataFlowJobRef`. Enables DAG edges with no intervening dataset. | ✅ Done. SDK V2 has no public API for this yet (its own source says so), so it's set directly via `job._ensure_datajob_inputoutput_props().inputDatajobs`. |
| 2.2 | `DATA_JOB` gains `externalUrl`, `properties`, `container` | Parity with `DATA_FLOW`. | ✅ Done — first two as constructor kwargs (C3); `container` via `extra_aspects=[ContainerClass(...)]` since `DataJob` has no `parent_container=`. |
| 2.3 | `DATA_FLOW` gains `container` | A pipeline can sit inside a container. | ✅ Done — `parent_container=` constructor kwarg (C2), guarded against the `Unset`-sentinel trap. |
| 2.4 | Assertion types `VOLUME`, `DATA_SCHEMA`, `CUSTOM` | Extends the `type` discriminator in `builders/assertion.py`. `VOLUME` covers `RowCountTotal`/`RowCountChange`. `DATASET` is **not** added — deprecated upstream. | ✅ Done. Found a second Avro non-nullability trap along the way (C6: `RowCountTotalClass`/`RowCountChangeClass.parameters`). |
| 2.5 | `assertionInfo.description`, `assertionNote`, `assertionActions` | Declarative on-failure actions. | ✅ Done. `assertionNote` was dropped then restored (C7) once `acryl-datahub` moved to `1.7.0.3`, where `AssertionNoteClass` is a registered top-level aspect (it wasn't in `1.6.0.13`). |
| 2.6 | Generic raw-aspect entity reference | `RawAspectDoc` accepts `entityUrn:` alongside the three typed refs, so a raw aspect can target any entity. The per-aspect builder registry in `raw_aspect.py` stays. | 🟡 Partial — the `entityUrn:` field was added to the model, but no builder registers a use for it: no concrete new `aspectName` in this round needed a non-dataset/assertion/dataProcessInstance reference. Wire it up when one does. |

### Phase 3 — Column-level metadata (P1) — ✅ Done (`4c05eeb`)

| # | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| 3.1 | `schema.fields[]` accepts `tags`, `glossaryTerms`, `structuredProperties`, `deprecation` | Emitted as aspects on the **`schemaField` entity URN** (`make_schema_field_urn()`) — *not* as `editableSchemaMetadata`. The registry permits `globalTags`, `glossaryTerms`, `structuredProperties`, `deprecation`, `documentation`, `businessAttributes` on `schemaField`. | ✅ Done. `SchemaFieldDoc` gains only the 4 mixins this use case needs (not `documentation`/`businessAttributes`/ownership/domains/subTypes, which the registry also permits but nothing needs yet). Delegates straight to `common_aspect_mcps()` — no new aspect-construction code was needed at all. |
| 3.2 | Field-level references validated | An undeclared tag/term on a column produces the same dangling-reference warning as at entity level, naming the column. | ✅ Done — context string is `"DATASET 'x' field 'ssn'"`. |
| 3.3 | Emission order | `schemaField` MCPs emitted after the parent dataset's `schemaMetadata`, so the fields exist when the annotations land. | ✅ Done. |

### Phase 4 — New entity kinds (P1) — ✅ Done, one commit per kind

| # | Kind | Aspects | Mechanism | Status |
|---|---|---|---|---|
| 4.1 | `DASHBOARD` | `dashboardInfo` (`title`, `description`, `dashboardUrl`, `charts`, `datasets`, `dashboards`), `subTypes`, `container`, `dataPlatformInstance` + all 9 common mixins | `datahub.sdk.dashboard.Dashboard` — `input_datasets=`, `charts=`, `dashboards=`. Audit stamps default to `time=0`. | ✅ Done (`c63997a`), after `CHART`. New `ChartRef`/`DashboardRef` (platform+name) + `chart_urn()`/`dashboard_urn()`, not cross-validated against declared docs (same precedent as `DatasetRef`). |
| 4.2 | `CHART` | `chartInfo` (`title`, `description`, `chartUrl`, `inputs`, `type`), `subTypes`, `container` + all 9 common mixins | `datahub.sdk.chart.Chart` | ✅ Done (`f4ed4cc`), first of the five. |
| 4.3 | `QUERY` | `queryProperties` (`statement`, `language`, `source`, `name`, `description`), `querySubjects` (datasets/fields the query touches), `subTypes` only among common aspects | Raw MCP — no SDK V2 wrapper. | ✅ Done (`24490ef`). New `QuerySubjectRef` (a `DatasetRef` with optional `fieldPath`) resolves to a dataset or `schemaField` URN. |
| 4.4 | `INCIDENT` | `incidentInfo` (`type`, `title`, `description`, `entities`, `status`, `priority`, `assignees`), `incidentNotes`, `tags` only among common aspects | Raw MCP. | ✅ Done (`19bafcd`). `entities:` takes full URNs directly (same precedent as `DataProductDoc.assets`). `incidentExternalLinks` explicitly **out of scope** — needs a DataHub `connection` entity this connector has no concept of. |
| 4.5 | `DOCUMENT` | `documentInfo`, `documentSettings`, 7 of 9 common mixins (no `applications`, no `deprecation` — not permitted by the registry on `document`) | `datahub.sdk.document.Document.create_document()` / `create_external_document()` factories (no plain constructor). | ✅ Done, last of the five (Open Question 3's gate was resolved by shipping regardless — see below). Found a new, connector-wide-first trap (C8): these two factories stamp `datetime.now()` on `created`/`lastModified` unless explicitly pinned — every other SDK V2 entity in this connector defaults to a deterministic `time=0`. |

New kinds each needed: an entry in `ENTITY_DOC_TYPES_BY_KIND` / `EntityDoc`, a `ParsedRepository`
list + `loader.py` dispatch branch, a URN helper in `urns.py` (where the kind needs one), a report
counter, a slot in the emission order in `yaml_source.py`, both doc generators, unit tests, and a
fixture + golden-file regeneration — the "~3 files" target from Goal 2 held roughly true per kind once
Phase 1's dispatcher existed (the marginal work per kind was almost entirely the kind's own
properties aspect, not its cross-cutting aspects).

### Future Considerations (P2 — design for, do not build)

`CORP_USER` / `CORP_GROUP` (`owners:` currently references `corpuser` URNs that are never created —
no name, email, or group membership reaches DataHub); `DATA_CONTRACT` (would reference the
already-supported `ASSERTION` entities); `ER_MODEL_RELATIONSHIP`;
`BUSINESS_ATTRIBUTE` definitions + the `businessAttributes` aspect on `schemaField`; `FORM` +
`dynamicFormAssignment`; `NOTEBOOK`; `VERSION_SET` / `versionProperties`; custom `OWNERSHIP_TYPE`
(today `OwnerEntry.type` is a free-text string mapped onto the built-in `OwnershipType` enum —
custom types need `typeUrn`).

**No longer deferred**: the ML entities (`MLMODEL`, `MLMODEL_GROUP`, `MLFEATURE_TABLE`, `MLFEATURE`,
`MLPRIMARY_KEY`) and the v1.7 entities (`SEMANTIC_MODEL`, `METRIC`, `SERVICE`, `API`, `REPOSITORY`,
`AI_AGENT`, `AGENT_SKILL`) previously listed here shipped in Phase 5 — see
`docs/specs/ml-semantic-ai-catalog-entities.md`.

The `CommonMetadataMixin` + allowlist design is what makes each of these cheap later: a new kind
inherits the full cross-cutting surface for free and declares only its own properties aspect.

---

## Success Metrics

**Leading (measurable at merge)**
- ✅ Cross-cutting aspect matrix has **zero `✗` cells** for the nine common aspects across all 19
  kinds (the original 14 plus the 5 this spec added) — confirmed against `entity-registry.yml`,
  transcribed as the matrix comment in `models.py`.
- ✅ `STRUCTURED_PROPERTY` values are assignable on any kind the registry permits. Spot-checked
  against real definitions during the Phase 1-3 real-ingest pass against `datahub-sample`.
- ✅ Unit coverage on new/changed builder code: **97% overall**, no file below 83% (bar was ≥80%).
- Not yet run: `check-capabilities` against a live fixture ingest (requires the
  `datahub-skills:connector-validator` tooling) — the fixture tree itself demonstrably produces every
  declared capability's output via the passing integration tests.

**Lagging**
- ✅ Confirmed in practice: adding `INCIDENT`/`QUERY` (the two thinnest new kinds) touched
  `models.py`, one new `builders/<kind>.py`, `urns.py`, `loader.py`, `yaml_source.py`,
  `yaml_source_report.py`, both doc generators' output, and tests+fixture — more than 3 *files*
  literally, but the cross-cutting-aspect part of each was zero additional code, which was the actual
  target ("no new code path in a builder" per Goal 2).
- ✅ Done for Phases 1-3: a real `datahub ingest` against the actual `datahub-sample` repo was run
  after the Phase 1-3 refactor, found ~90 pre-existing dangling tag/glossaryTerm warnings in the
  *sample data itself* (undeclared tags, duplicate tag/glossaryTerm entries, undeclared glossary
  terms — none were connector bugs), and after correcting the sample repo settled at **zero**
  dangling-reference / unknown-field / failure warnings.
- **Not yet run**: the same real-ingest pass has not been repeated since Phase 4 landed — the
  `datahub-sample` repo declares no `CHART`/`DASHBOARD`/`QUERY`/`INCIDENT`/`DOCUMENT` documents, so
  the five new kinds are so far only exercised against the curated integration fixture tree, not the
  full real-world repo.

---

## Open Questions

| # | Question | Owner | Resolution |
|---|---|---|---|
| 1 | `DATA_PLATFORM_INSTANCE`: nested `instances:` under `DataPlatformDoc`, or its own top-level kind? | maintainer | **Resolved by decision D3**: neither, for now. Named platform instances deferred to Future Considerations; the `dataPlatformInstance` aspect keeps emitting exactly as before. |
| 2 | Should an unsupported common field on a kind be a hard validation error (rejects the file) or a warning-and-skip? | maintainer | **Resolved by decision D2**: warning-and-skip by default (`report_unknown_fields`), escalated to a hard error under `fail_on_unresolved_reference: true` — consistent with every other soft-error in the connector. |
| 3 | Is the target GMS actually on v1.7? `DOCUMENT`, `applications`, and `displayProperties` are recent; emitting them against an older GMS yields rejected MCPs. | AP-HP platform team | **Still open.** Decision made to ship all of Phase 4 regardless (code correctness doesn't depend on the answer), but the actual target deployment's version has not been confirmed in this environment. If it predates `DOCUMENT`'s introduction, only that kind's MCPs would be rejected — everything else is unaffected. |
| 4 | Does `docs/sources/yaml/yaml_recipe.yml` stay pointed at the full `datahub-sample` root? | maintainer | Still open, non-blocking. |
| 5 | Column-level annotation on `schemaField` entities requires those URNs to resolve in the target GMS. Confirm the deployment indexes `schemaField` entities. | AP-HP platform team | **Still open** — same caveat as #3: the MCPs are emitted and valid regardless, but whether tags surface on a column in the UI depends on this. |

---

## Timeline / Phasing (as executed)

No hard external deadline; sequencing followed dependency, not calendar, exactly as planned:

1. **Phase 1** landed first, alone (`367cbfb`) — the refactor everything else rode on, touching all 14
   original builders plus the golden file. Confirmed via an empty structural golden-diff checkpoint
   before any new fixture content was added.
2. **Phase 2** landed inside the same commit, opportunistically — once Phase 1's corrections (C1-C3)
   showed the remaining pipeline/assertion work was nearly free, splitting it into a separate commit
   would have added process overhead for no isolation benefit.
3. **Phase 3** landed next (`4c05eeb`), independently, exactly the largest single behavioural change to
   `builders/dataset.py` this spec anticipated — but a small one in practice, since it reused Phase 1's
   dispatcher with zero new aspect-construction code.
4. **Phase 4** landed last, five separate commits (one per kind), each depending on Phase 1's mixins
   existing from the start rather than being retrofitted: `CHART` → `DASHBOARD` (needs `CHART` for its
   `charts:` field) → `QUERY` → `INCIDENT` → `DOCUMENT` (gated last on the SDK factory quirks in C8).

Each phase/commit was independently reviewable, and each was verified (unit + integration + coverage)
before moving to the next.

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

---

### Actual run status (2026-08-15)

- **Steps 1-2** (unit tests, artifact regeneration): run repeatedly through every phase and commit —
  currently 140 passed, generated artifacts in sync.
- **Step 3** (integration fixture + golden file): run and reviewed by hand after every commit; each
  regeneration verified via a structural diff (added/removed/changed aspect keys) to confirm only the
  intended aspects changed.
- **Step 4** (real ingest against `datahub-sample`): run for Phases 1-3 — found and fixed ~90
  pre-existing warnings in the sample data itself (not connector bugs), settled at zero. **Not
  re-run since Phase 4** — `datahub-sample` has no `CHART`/`DASHBOARD`/`QUERY`/`INCIDENT`/`DOCUMENT`
  fixtures of its own yet, so the five new kinds are only verified against this connector's own
  integration fixture tree so far.
- **Step 5** (standards review): not yet run in this environment.
