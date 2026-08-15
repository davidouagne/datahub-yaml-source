# YAML Metadata Source Connector — Planning Document v2 (Coverage Extension)

**Created**: 2026-08-15
**Status**: PARTIALLY IMPLEMENTED — see [Implementation Status](#implementation-status) at the bottom
**Implements**: [`docs/specs/entity-aspect-coverage-gaps.md`](docs/specs/entity-aspect-coverage-gaps.md)
**Supersedes nothing**: `_PLANNING.md` (2026-07-13, Status IMPLEMENTED) stays as the as-built record of v1.

---

## Context

`_PLANNING.md` planned and delivered a connector covering 14 document kinds. In use, the *aspect*
coverage inside those kinds turned out to be inconsistent in ways that have no design rationale —
each builder was written independently, so whichever cross-cutting aspect the author needed at the
time was wired into that one builder and nowhere else. `structuredProperties` values can only be
attached to `DATA_PRODUCT` (while the AP-HP repo declares 64 property definitions, many scoped to
datasets); `domains` works on `DATASET`/`DATA_FLOW` but not on `CONTAINER`/`DATA_JOB`; `deprecation`
and `institutionalMemory` work nowhere; no column can be tagged.

`docs/specs/entity-aspect-coverage-gaps.md` is the approved spec for closing that. **This document is
the implementation blueprint for that spec** — it records the architecture decisions, the corrections
found by checking the spec's assumptions against the installed SDK, and the file-by-file order of work.
The spec says *what* and *why*; this says *how*.

Intended outcome: aspect support becomes a property of the format, declared once per kind by
inheritance, instead of a per-builder accident — and the marginal cost of the next aspect drops from
~20 files to ~3.

---

## Scope

| In scope | Out of scope |
|---|---|
| Spec Phases 1–4 (cross-cutting parity + refactor, pipeline/assertion completeness, column-level metadata, 5 new kinds) | Everything in the spec's Non-Goals table (`editable*` aspects, system-computed aspects, SQL parsing) |
| Correcting `@capability` declarations to match real output | Spec's Future Considerations (`CORP_USER`/`CORP_GROUP`, `DATA_CONTRACT`, ML entities, …) |
| Regenerating `reference.md` + `yaml-metadata.schema.json` from the models | Spec item **1.10** (`dataPlatformInstanceProperties`) — **deferred by decision**, see Decisions |

---

## Verification Against the Installed SDK

No source-system research applies here — the "source" is a local YAML tree, classified in
`_PLANNING.md` as *Other (declarative file-based)*, base class `StatefulIngestionSourceBase`, and
none of that changes. What *did* need research is whether the spec's mechanical assumptions hold
against the SDK this repo actually runs.

**Installed: `acryl-datahub 1.7.0.3`** (`.venv/`) — raised from `1.6.0.13` on 2026-08-15 at the user's
request, to match the version their real GMS/CLI actually runs (`datahub ingest` reported
`DataHub CLI version: 1.7.0.3`), and because it's closer to the spec's own reference,
`v1.7.0rc1-111-gb9890a0912`. `setup.py`'s floor is now `acryl-datahub>=1.7.0`. Re-verifying every
version-dependent finding below against 1.7.0.3 changed two things (both already applied to the code):
`AssertionNoteClass` **is** a registered top-level aspect in 1.7.0.3 (it wasn't in 1.6.0.13) — the
`assertionNote` field and its emission, previously dropped as infeasible, are back. `GlossaryNode`/
`GlossaryTerm`'s SDK V2 wrappers gained a native `tags=` constructor kwarg in 1.7.x — `glossary.py`'s
`_GLOSSARY_NODE_NATIVE_KWARGS`/`_GLOSSARY_TERM_NATIVE_KWARGS` now include it, so tags on those two
kinds go through the SDK's own `set_tags()` instead of the `extra_aspects` fallback (same resulting
aspect either way — confirmed via an empty structural golden-file diff before/after the version bump).
Everything else below (the C1–C7 corrections, the Unset-sentinel trap, the required-non-null-`note`
trap) was re-verified unchanged under 1.7.0.3. Everything the spec needs exists — verified by import:

- Aspect classes: `DeprecationClass`, `InstitutionalMemoryClass`, `StructuredPropertiesClass`,
  `ApplicationsClass`, `DisplayPropertiesClass`, `GlossaryRelatedTermsClass`, `QueryPropertiesClass`,
  `QuerySubjectsClass`, `IncidentInfoClass`, `DocumentInfoClass`, `VolumeAssertionInfoClass`,
  `SchemaAssertionInfoClass`, `CustomAssertionInfoClass`, `AssertionActionsClass`, `DocumentationClass`.
- SDK V2 wrappers: `Chart`, `Dashboard`, `Document` all present. **No** `Domain` / `DataProduct`
  wrapper → those stay on raw MCP, as today.

**Five corrections to the spec's architecture notes**, each verified by inspecting the installed code:

| # | Spec said | Actually (1.6.0.13) | Consequence |
|---|---|---|---|
| C1 | `gen_containers()` takes no `domain`/`structuredProperties` → emit follow-up MCPs | Signature **does** include `domain_urn=` and `structured_properties=` | Container follow-up MCPs are only needed for `terms`, `links`, `deprecation`, `applications` — a smaller job than planned |
| C2 | `DATA_FLOW` needs new plumbing for `container` (spec 2.3) and `glossaryTerms` (1.5) | `DataFlow.__init__` already accepts `parent_container`, `terms`, `links`, `structured_properties`, `extra_aspects` | Both become constructor kwargs, near-free |
| C3 | `DATA_JOB` needs `externalUrl`/`properties`/`container` (spec 2.2) | `DataJob.__init__` accepts `external_url`, `custom_properties`, `terms`, `links`, `domain`, `structured_properties` — but **no `parent_container`** | Only `container` needs special handling: `extra_aspects=[ContainerClass(container=...)]` |
| C4 | "Don't call `set_structured_property()`" (non-deterministic `datetime.now()`) | True — **and the `structured_properties=` constructor kwarg routes straight into it** (`Dataset.__init__` loops `set_structured_property`) | The kwarg is unusable for golden-file work. Build `StructuredPropertiesClass` directly and pass it via `extra_aspects=`, as `builders/data_product.py:82-93` already does |
| C5 | `subTypes` fix = "pass the full list" | `subtype=` is a single `str`; `set_subtype()` stores `typeNames=[subtype]` and the getter warns on >1 | Multi-subtype needs `subtype=None` + `SubTypesClass(typeNames=[...])` in `extra_aspects`. Verified safe: `_set_extra_aspects()` runs *before* `set_subtype()` in `__init__`, so passing both would silently let `subtype=` win — pass only one |

`links=` is safe as a constructor kwarg: `HasInstitutionalMemory._institutional_memory_audit_stamp()`
returns `AuditStampClass(time=0, …)`, so golden files stay deterministic.

**Action item**: raise the floor in `setup.py` from `acryl-datahub>=1.0.0` to `>=1.6.0` — the code
below depends on constructor kwargs that older releases do not have.

---

## Decisions

### D1 — Granular per-aspect mixins, not one flat mixin + runtime allowlist

The spec sketched a single `CommonMetadataMixin` carrying all nine fields, plus a
`COMMON_ASPECTS_BY_KIND` allowlist checked at runtime. **Chosen instead**: one small mixin per
aspect, and each kind inherits exactly the ones DataHub's entity registry permits.

```python
# models.py
class HasOwners(BaseModel):            owners: Optional[OwnersField] = None
class HasTags(BaseModel):              tags: Optional[StringList] = None
class HasTerms(BaseModel):             glossaryTerms: Optional[StringList] = None
class HasDomain(BaseModel):            domains: Optional[str] = None
class HasApplications(BaseModel):      applications: Optional[StringList] = None
class HasLinks(BaseModel):             links: Optional[List[LinkDoc]] = None
class HasDeprecation(BaseModel):       deprecation: Optional[DeprecationDoc] = None
class HasStructuredProps(BaseModel):   structuredProperties: Optional[Dict[str, Any]] = None
class HasSubTypes(BaseModel):          subTypes: Optional[SubTypesField] = None

class TagDoc(HasOwners, HasLinks, HasDeprecation, BaseModel):
    kind: Literal["TAG"]
    ...
```

**Why**: this is the shape DataHub's own SDK V2 uses (`HasOwnership`, `HasTags`, `HasTerms`,
`HasDomain`, `HasInstitutionalMemory`, `HasSubtype` in `datahub/sdk/_shared.py`), so the format's
model layer and the SDK it targets read the same way. Per-kind validity becomes *static*: the
generated `reference.md` and JSON schema show a field only where it is genuinely valid, with no
second allowlist to keep in sync with the models. `glossaryTerms` on a `TAG` doesn't get rejected —
it doesn't exist.

The allowlist still exists, but only as the *derivation* of the class declarations, recorded as a
comment block citing `entity-registry.yml` at the pinned version.

### D2 — Unknown / non-permitted fields: warning by default, hard failure on request

Every entity doc model gets `model_config = ConfigDict(extra="allow")` plus a shared
`model_validator(mode="after")` that reports anything landing in `model_extra`. The loader turns that
into `report.report_unknown_field(...)` — a new counter alongside `dangling_references` — and
`fail_on_unresolved_reference: true` escalates it to an error.

**Why**: consistent with the connector's existing "one bad document warns and is skipped, it never
takes down the run" philosophy, while fixing the spec's core complaint that authors are *silently*
ignored today. `extra="forbid"` was rejected as too risky against the real AP-HP repo, where a stray
field is currently ignored without consequence and would become a hard failure overnight.

### D3 — Spec item 1.10 (`dataPlatformInstanceProperties`) deferred

Named platform instances move to Future Considerations. The `dataPlatformInstance` *aspect* keeps
being emitted exactly as today; instances simply continue to render unnamed in the UI. Neither a
nested `instances:` block nor a `DATA_PLATFORM_INSTANCE` kind is built in this round. Spec Open
Question #1 is closed by this decision.

### D4 — Doc generator learns about the mixins

Pydantic orders `model_fields` with inherited fields first, so mixins would push `kind`/`name`/
`platform` below `owners`/`tags`/… in every generated table. `scripts/generate_markdown_docs.py`
therefore gets a small change: render each kind's *own* fields first, then a short "Common metadata"
line listing which shared blocks that kind accepts, linking to one shared section documented once.
That turns an accidental ordering regression into the documentation improvement the spec asked for
("a single declaration point for which aspects a kind accepts").

---

## Architecture

### Emission split: SDK V2 kwargs vs. follow-up MCPs

The nine common aspects do not all reach DataHub the same way, so `builders/common.py` grows **two**
helpers rather than the spec's single `build_common_aspects()`:

```python
# builders/common.py

def common_sdk_kwargs(doc, index, report, context: str) -> Dict[str, Any]:
    """Cross-cutting aspects for an SDK V2-backed kind: returns owners=/tags=/terms=/
    domain=/links=/subtype= plus an `extra_aspects` list for what the SDK cannot take
    natively (applications, deprecation, structuredProperties, multi-subtype)."""

def common_aspect_mcps(entity_urn, doc, index, report, context: str) -> Iterable[MetadataWorkUnit]:
    """Same aspects as standalone MCPs, for raw-MCP kinds (DOMAIN, APPLICATION,
    DATA_PRODUCT, ASSERTION) and as follow-ups after gen_containers()."""
```

Both dispatch on `isinstance(doc, HasTags)` etc., so a kind automatically gets whatever it inherited
and nothing else. Both take the `context` string used in dangling-reference warnings
(`"DATASET 'foo'"`), so the existing warning text stays identical.

Per-kind routing:

| Kind | Mechanism |
|---|---|
| `DATASET`, `DATA_FLOW`, `DATA_JOB`, `TAG`, `GLOSSARY_NODE`, `GLOSSARY_TERM`, and new `DASHBOARD`/`CHART`/`DOCUMENT` | `common_sdk_kwargs()` spread into the SDK V2 constructor |
| `CONTAINER` | `domain_urn=` / `structured_properties=` into `gen_containers()` (C1); `terms`/`links`/`deprecation`/`applications` as follow-up MCPs, the shape `builders/container.py:96-99` already uses |
| `DOMAIN`, `APPLICATION`, `DATA_PRODUCT`, `ASSERTION`, and new `QUERY`/`INCIDENT` | `common_aspect_mcps()` after the entity's own properties aspect |

Three aspects **never** go through an SDK constructor, regardless of kind: `applications` (no SDK
support), `deprecation` (no SDK support), `structuredProperties` (C4 — the kwarg is
non-deterministic). They are always built as aspect classes and passed via `extra_aspects=`.

### Mixin → kind matrix

Transcribed from the spec's verified coverage matrix (`✓`/`✗` cells = permitted; `—` = not permitted
on that entity). **The implementer re-checks each cell against
`metadata-models/src/main/resources/entity-registry.yml` before writing the class declarations** —
this is a transcription, and a wrong cell means an MCP the GMS rejects at runtime.

| | Owners | Tags | Terms | Domain | Applications | Links | Deprecation | StructProps | SubTypes |
|---|---|---|---|---|---|---|---|---|---|
| `DATASET` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `CONTAINER` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `DATA_FLOW` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `DATA_JOB` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `DATA_PRODUCT` | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| `DOMAIN` | ● | | | | | ● | ● | ● | |
| `APPLICATION` | ● | ● | | ● | | ● | | ● | ● |
| `GLOSSARY_TERM` | ● | ● | | ● | ● | ● | ● | ● | ● |
| `GLOSSARY_NODE` | ● | ● | | ● | | ● | | ● | ● |
| `TAG` | ● | | | | | | ● | | |
| `ASSERTION` | ● | ● | | | | | | | |

New kinds (Phase 4) inherit the full row of whatever the registry permits, from birth.

### New entity kinds (Phase 4)

| `kind:` | DataHub entity | Own aspects | Mechanism |
|---|---|---|---|
| `CHART` | `chart` | `chartInfo` (title, description, chartUrl, inputs, type), `container` | `datahub.sdk.Chart` |
| `DASHBOARD` | `dashboard` | `dashboardInfo` (title, description, dashboardUrl, charts, datasets, dashboards), `container` | `datahub.sdk.Dashboard` (`input_datasets=`, `charts=`, `dashboards=`) |
| `QUERY` | `query` | `queryProperties` (statement, language, source, name, description), `querySubjects` | Raw MCP — no SDK wrapper |
| `INCIDENT` | `incident` | `incidentInfo` (type, title, description, entities, status, priority, assignees), `incidentExternalLinks`, `incidentNotes` | Raw MCP |
| `DOCUMENT` | `document` | `documentInfo`, `documentSettings` | `datahub.sdk.Document` — gate on target-GMS confirmation (Open Question 2) |

Emission order slots into `yaml_source.py:124-206`, parents before children:
`… → DATASET → QUERY → INCIDENT → CHART → DASHBOARD → DOCUMENT → DATA_PRODUCT → …`.

### Column-level metadata (Phase 3)

`SchemaFieldDoc` gains `HasTags`, `HasTerms`, `HasStructuredProps`, `HasDeprecation`. Annotations are
emitted as MCPs on the **`schemaField` entity URN** built with `make_schema_field_urn()` (already
imported at `builders/dataset.py:3`) — never as `editableSchemaMetadata`, which is UI-owned. They are
emitted *after* the parent dataset's workunits so the fields exist when the annotations land, and
they reuse `common_aspect_mcps()` with a context string naming the column.

---

## Capabilities

`yaml_source.py:48-55` currently under-declares. Add, each demonstrably produced by the integration
fixture tree once Phase 1 lands:

| Capability | Produced by |
|---|---|
| `DOMAINS` | `domains:` on every kind that permits it |
| `GLOSSARY_TERMS` | `GLOSSARY_*` docs + `glossaryTerms:` references |
| `PLATFORM_INSTANCE` | `instance:` on datasets/containers → `dataPlatformInstance` aspect |
| `DESCRIPTIONS` | `description:` on nearly every kind |
| `DATA_PROFILING` | `aspectName: DATASET_PROFILE` passthrough |
| `USAGE_STATS` | `aspectName: DATASET_USAGE_STATISTICS` passthrough |
| `OPERATION_CAPTURE` | `aspectName: OPERATION` passthrough |

Keep the eight already declared. Verify with the `check-capabilities` script from
`datahub-skills:connector-validator` before merge — a declared capability with no output is a
standards violation in its own right.

---

## Known Limitations

| Limitation | Impact | Handling |
|---|---|---|
| Mixin inheritance reorders `model_fields` | Large mechanical diff in `reference.md` and `yaml-metadata.schema.json` on the Phase 1 commit | D4: doc generator renders kind-specific fields first; review the diff once, then it is stable |
| `extra="allow"` means typos are warnings, not errors | A misspelled field still ingests silently-but-noisily unless `fail_on_unresolved_reference` is set | D2, deliberate; documented in `yaml.md` |
| Named platform instances still unsupported | Instances render unnamed in the UI | D3, deferred to Future Considerations |
| `DOCUMENT` is recent | MCPs rejected if the target GMS predates it | Open Question 2 — ship 4.5 last, behind confirmation |
| `schemaField` annotations need those URNs indexed by the target GMS | Column tags may not surface | Open Question 3 — Phase 3 only |

---

## Implementation Order

Ordered by dependency, not calendar. Each phase is independently shippable and separately reviewable.
**Phase 1 lands alone** — it touches all 14 builders plus the golden file, and mixing it with feature
work makes the golden diff unreadable.

### Phase 1 — Cross-cutting parity + refactor (P0)

1. `setup.py`: raise the `acryl-datahub` floor to `>=1.6.0`.
2. `models.py`: add `LinkDoc`, `DeprecationDoc`, the nine `Has*` mixins, and the shared unknown-field
   validator. Re-derive each kind's mixin list from `entity-registry.yml`. Remove the now-duplicated
   per-kind fields (`DatasetDoc.owners/tags/glossaryTerms/domains/applications/subTypes`,
   `ContainerDoc.owners/tags/subTypes`, `DataProductDoc.structuredProperties`, …) — **no YAML in the
   sample repo changes shape**, which is the compatibility bar.
3. `builders/common.py`: `common_sdk_kwargs()` + `common_aspect_mcps()`, plus `build_deprecation_aspect()`,
   `build_links_aspect()`, `build_structured_properties_aspect()` (lifted verbatim from
   `data_product.py:75-93`, which becomes its first caller).
4. Rewrite each builder to consume them. Order: `dataset.py` → `container.py` → `data_flow_job.py` →
   `data_product.py` → `domain.py` / `glossary.py` / `tag.py` / `application.py` → `assertion.py`.
   Fix the multi-subtype bug at `dataset.py:162-163` per C5.
5. Entity-specific fields the spec calls out: `DomainDoc.parentDomain` (+ topological sort reusing
   `topological_sort_containers()`'s Kahn implementation at `container.py:20-58`),
   `GlossaryTermDoc.glossaryRelatedTerms` / `termSource` / `sourceRef` / `sourceUrl`,
   `TagDoc.colorHex`, `displayProperties` on `DOMAIN`/`GLOSSARY_*`.
6. `urns.py`: `ReferenceIndex` already answers every lookup the new aspects need
   (`has_structured_property`, `has_application`, `has_glossary_term`, `has_domain`) — no new index
   entries in this phase.
7. `yaml_source_report.py`: counters for the new aspects + `unknown_fields`.
8. `yaml_source.py`: the seven added `@capability` decorators.
9. Regenerate both derived artifacts; unit tests; extend the integration fixture tree; refresh the
   golden file and review it aspect by aspect.

> **Intermediate checkpoint**: after step 4 but before step 5, the golden diff must be **empty**. A
> pure refactor that changes output is a bug, and this is the cheapest place to catch it.

### Phase 2 — Pipeline & assertion completeness (P0)

1. `DataJobDoc.inputDataJobs` → `dataJobInputOutput.inputDatajobs` (the `DataFlowJobRef` model already
   exists at `models.py:368-371`).
2. `DATA_JOB`: `externalUrl`, `properties`, `container` — the first two are constructor kwargs (C3),
   `container` goes via `extra_aspects=[ContainerClass(...)]`.
3. `DATA_FLOW`: `container` → `parent_container=` (C2).
4. `builders/assertion.py`: add `VOLUME`, `DATA_SCHEMA`, `CUSTOM` to the `_BUILDERS` registry at
   line 88. **Not** `DATASET` — deprecated upstream.
5. `assertionInfo.description` (already threaded), `assertionNote`, `assertionActions`.
6. `RawAspectDoc` accepts a generic `entityUrn:` alongside the three typed refs. The per-aspect
   builder registry in `raw_aspect.py` **stays** — its docstring's reasoning (nested payloads need
   real aspect classes, not dicts) is correct.

### Phase 3 — Column-level metadata (P1)

1. `SchemaFieldDoc` inherits `HasTags`/`HasTerms`/`HasStructuredProps`/`HasDeprecation`.
2. `builders/dataset.py` emits `schemaField` MCPs after the dataset's own workunits.
3. Dangling-reference warnings name the column.

### Phase 4 — New entity kinds (P1)

Per kind: `models.py` entry (mixins + own fields) → `ENTITY_DOC_TYPES_BY_KIND` + `EntityDoc` →
`ParsedRepository` list + `loader.py` dispatch → `urns.py` helper → `builders/<kind>.py` → report
counter → emission slot in `yaml_source.py` → doc generators → unit tests → fixture + golden.

Order: `CHART` → `DASHBOARD` (needs charts first) → `QUERY` → `INCIDENT` → `DOCUMENT` (last, gated).

---

## Testing Strategy

Unchanged in structure from `_PLANNING.md`; the existing files map onto the work:

| Area | File |
|---|---|
| Mixin composition, unknown-field warning, new field parsing | `tests/unit/test_models.py` |
| Per-aspect emission from the shared helpers | `tests/unit/test_builders_core.py`, `test_builders_dataset.py`, `test_builders_extended.py`, `test_builders_flow_job.py` |
| New URN helpers (Phase 4) | `tests/unit/test_urns.py` |
| New kinds parsed and dispatched | `tests/unit/test_loader.py` |
| Generated-artifact sync | `tests/unit/test_json_schema_generation.py`, `test_markdown_docs_generation.py` (these fail if regeneration is skipped — not optional) |
| End-to-end | `tests/integration/yaml_source/` fixture tree + `yaml_source_mces_golden.json` |

Every new aspect and every new kind needs a fixture in
`tests/integration/yaml_source/resources/{setup,raw-layer,transform-layer,view-layer,dataproduct-layer,quality-layer,observability-layer}/`.
Bar: ≥80% coverage on new/changed builder code.

---

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
Phase 1's refactor step must produce an **empty** golden diff before new aspects are wired in.

**4. Real ingest against the AP-HP repo** (88 datasets, 64 structured properties, 12 containers, 39 jobs)
```bash
datahub ingest -c docs/sources/yaml/yaml_recipe.yml --dry-run
```
Then a live run, checking the report for `warnings` / `dangling_references` / `unknown_fields` /
`failures` at zero, and confirming in the UI: a dataset with a structured property value, a deprecated
dataset, a dataset with links, a nested domain tree, a PII-tagged column, a job→job DAG edge.

**5. Standards review** — `/datahub-skills:connector-review` on the branch before merge. The
capability fix and report counters answer that checklist directly; the removal of per-builder aspect
assembly answers its DRY criteria.

---

## Open Questions

| # | Question | Owner | Blocking? |
|---|---|---|---|
| 1 | Confirm each mixin↔kind cell against `entity-registry.yml` at the pinned version before writing the class declarations. | implementer | **Yes** — first task of Phase 1 |
| 2 | Is the target GMS recent enough for `DOCUMENT`, `applications` and `displayProperties`? | AP-HP platform team | **Yes** for 4.5, no for Phases 1–3 |
| 3 | Does the target deployment index `schemaField` entities? | AP-HP platform team | No — Phase 3 only |
| 4 | Does `docs/sources/yaml/yaml_recipe.yml` stay pointed at the `datahub-sample` root? (currently modified, uncommitted) | maintainer | No |

Spec Open Question #1 is closed by D3; spec Open Question #2 is closed by D2.

---

## Approval

- [ ] User approved this plan on:
- [ ] Approval message:

---

## Implementation Status

_As of 2026-08-15, re-verified against `acryl-datahub==1.7.0.3`, Phase 3 added. Test suite:
`python -m pytest tests/unit tests/integration -q` → 121 passed, 96% coverage._

### Done

- **Phase 1, items 1.1–1.6, 1.11, 1.12** (the core refactor): `HasOwners`/`HasTags`/`HasTerms`/`HasDomain`/
  `HasApplications`/`HasLinks`/`HasDeprecation`/`HasStructuredProps`/`HasSubTypes` mixins in `models.py`,
  `common_sdk_kwargs()` + `common_aspect_mcps()` in `builders/common.py`, every builder rewritten to consume
  them, the `dataset.py:162-163` multi-subtype bug fixed, seven added `@capability` decorators, new report
  counters. The refactor step alone produced an **empty golden diff** before any new fixture content was
  added — confirmed via a structural before/after comparison, the exact checkpoint the plan called for.
- **1.7** nested domains (`DomainDoc.parentDomain` + `topological_sort_domains()`).
- **1.8** `GlossaryTermDoc.glossaryRelatedTerms` / `termSource` / `sourceRef` / `sourceUrl`, mapped directly
  onto `GlossaryTerm`'s native SDK kwargs (`is_a`/`has_a`/`values`/`related_terms`/`term_source`/...).
- **1.9** `TagDoc.colorHex`, `DisplayPropertiesDoc.colorHex` on `DOMAIN`/`GLOSSARY_TERM`/`GLOSSARY_NODE`.
  (`icon` deliberately not implemented — `IconPropertiesClass` needs a library/name/style triple with no
  natural single-field YAML shorthand.)
- **D2** (unknown-field warning): every entity kind is `extra="allow"` + the loader reports `model_extra`
  as a warning (`report_unknown_fields`), escalated to an error under `fail_on_unresolved_reference`.
- **Phase 2**, opportunistically, since C1–C3 showed it was cheap: 2.1 (`DataJobDoc.inputDataJobs`,
  emitted by reaching into `DataJob._ensure_datajob_inputoutput_props()` since SDK V2 has no public API for
  it yet — its own source says so), 2.2 (`DATA_JOB.externalUrl`/`properties`/`container`), 2.3
  (`DATA_FLOW.container`), 2.4 (assertion types `VOLUME`/`DATA_SCHEMA`/`CUSTOM`), 2.6 partially (see below).
- Integration fixtures extended to exercise the new cross-cutting aspects end-to-end (deprecation, links,
  structuredProperties on a dataset and a container, ownership on a domain/tag, a nested domain pair, a
  DAG edge via `inputDataJobs`, a `DATA_FLOW` container, a `VOLUME` assertion, tags/owners on an assertion)
  — the fixture tree re-ingests with zero dangling references, zero unknown fields, zero parse failures.

### Corrected during implementation (beyond the plan's own C1–C5)

- **C6 — `DeprecationClass.note` is a required, non-nullable `string` in the Avro schema** (`Deprecation.pdl`),
  despite the generated Python stub typing it `Optional[str]`. Passing `None` parses fine but fails
  `MetadataChangeProposalWrapper.validate()` at emit time — it would have crashed the whole ingestion run
  the first time an author wrote `deprecation:` without a `note`. Fixed: `note=dep.note or ""`.
  `RowCountTotalClass`/`RowCountChangeClass.parameters` have the identical trap; fixed by requiring `value`
  for `VOLUME` assertions and always constructing `parameters`, matching the pre-existing SQL-assertion code.
- **C7 — `AssertionNoteClass` was not a registered top-level aspect in `acryl-datahub==1.6.0.13`** (no
  `get_aspect_name()` — confirmed by comparing against `AssertionActionsClass`, which was one). Initially
  dropped for that reason. **Restored 2026-08-15** once the floor moved to `1.7.0.3` (see above) — it *is*
  a registered aspect there. `AssertionDoc.assertionNote` and its emission in `build_assertion()` are back;
  exercised in the integration fixture (`quality-layer/quality.yml`'s `VOLUME` assertion).
- **`DataFlow`'s `parent_container=` (and `Dataset`'s) defaults to a private `Unset` sentinel, not `None`.**
  Passing `None` explicitly still calls `_set_container(None)`, which emits an empty `browsePathsV2`
  aspect that wasn't there before. Fixed in `build_data_flow()` by only including the kwarg in the dict at
  all when a container is actually declared (`Dataset`'s pre-existing call site has the same quirk but was
  out of scope to touch — it predates this refactor and isn't a regression).
- Found and fixed a real bug in my own first draft: `TagDoc` was given a `HasLinks` mixin that contradicted
  the verified entity-registry matrix (`tag` doesn't support `institutionalMemory`) — caught by writing the
  matrix comment in `models.py` *before* the class declarations and then checking each one against it.
- **Design change from the approved plan**: `common_sdk_kwargs()` needed a `native=` parameter partway
  through implementation. The plan assumed every SDK V2 entity class implements the same six mixins
  (`owners`/`tags`/`terms`/`domain`/`links`/`subtype`) uniformly; in fact `Tag`/`GlossaryNode`/`GlossaryTerm`
  each implement a different subset (verified via `__mro__`). A mixin the *document* has but the *target SDK
  class* doesn't natively support now falls back to a standalone aspect via `extra_aspects` instead of
  crashing with a `TypeError` on an unrecognized kwarg.
- `DataJobDoc` does **not** get a `HasSubTypes` mixin, despite the registry permitting `subTypes` on
  `dataJob` — its pre-existing `type` field already maps to that exact aspect (`subtype=doc.type` in
  `build_data_job()`, unchanged from before this refactor). Adding `HasSubTypes` too would have given
  authors two differently-named fields for the same aspect and, worse, a duplicate-keyword crash on
  `subtype=`.

### Not done — deferred

- **Spec item 1.10** (`dataPlatformInstanceProperties`) — deferred by explicit decision (D3), see Open
  Question 1's resolution above.
- **2.5, done**: `assertionActions` and `assertionNote` (restored, see C7) both shipped. `AssertionInfo.description`
  was already threaded pre-refactor.
- **2.6, partially**: `RawAspectDoc.entityUrn` field was added to the model, but **no generic-scope builder
  was registered for it** in `raw_aspect.py` — there's no concrete new `aspectName` in this round that would
  exercise it, and registering the field alone without a matching builder is dead surface. Wire it up
  together with whatever raw aspect first needs a non-dataset/assertion/dataProcessInstance entity reference.
- ~~**Phase 3** (column-level metadata on `schemaField` entities) — not started.~~ **Done, 2026-08-15.**
  `SchemaFieldDoc` gained `HasTags`/`HasTerms`/`HasStructuredProps`/`HasDeprecation` (not `HasOwners`/
  `HasDomain`/`HasApplications`/`HasLinks`/`HasSubTypes` — scoped to the spec's PII-tagging use case,
  even though the registry permits more on `schemaField`). `build_dataset()` loops
  `doc.schema_block.fields` after emitting the dataset's own workunits, computes each field's URN via
  the already-imported `make_schema_field_urn()`, and delegates straight to `common_aspect_mcps()` --
  no new aspect-construction code needed at all, exactly the "marginal cost drops to ~3 files" the
  Phase 1 refactor was meant to enable. Dangling-reference warnings name the column
  (`"DATASET 'x' field 'ssn' references undeclared tag '...'"`). Exercised end-to-end in the
  integration fixture (`nom` column on `ehr_public_patient` tagged `pii` + linked to `fhir:Patient`).
- **Phase 4** (new kinds `DASHBOARD`/`CHART`/`QUERY`/`INCIDENT`/`DOCUMENT`) — in progress, one kind per
  commit. Each is a self-contained addition following the "per-addition file checklist" in the
  Architecture section above, independent of everything else in this document.
  - ~~`CHART`~~ **Done, 2026-08-15.** `ChartDoc` gets all nine `Has*` mixins (the registry permits the
    full row on `chart`). `builders/chart.py` uses the SDK V2 `datahub.sdk.chart.Chart` wrapper directly
    (all six native kwargs apply, same as `Dataset`/`DataFlow`/`DataJob`) -- no raw MCPs needed.
    `inputDatasets:` resolves via the existing `dataset_urn()` helper; no new URN helper was needed.
    Exercised in the integration fixture (`bi-layer/dashboards.yml`).
  - ~~`DASHBOARD`~~ **Done, 2026-08-15.** `DashboardDoc` also gets all nine `Has*` mixins. New
    `ChartRef`/`DashboardRef` natural-key models (platform+name) plus `chart_urn()`/`dashboard_urn()`
    helpers in `urns.py` let `charts:`/`dashboards:` resolve without a `ReferenceIndex` lookup --
    consistent with how `DatasetRef` references (e.g. `inputDatasets:`) are never cross-validated
    against declared `DATASET` docs either. `builders/dashboard.py` uses `datahub.sdk.dashboard.Dashboard`
    the same way `chart.py` uses `Chart`. Exercised in the integration fixture alongside the CHART it
    references.
  - ~~`QUERY`~~ **Done, 2026-08-15.** `QueryDoc` gets only `HasSubTypes` -- the registry permits
    nothing else transverse on `query`. No SDK V2 wrapper exists for it, so `builders/query.py` emits
    raw MCPs (`queryProperties`, and `querySubjects` only when `subjects:` is non-empty), like
    `domain.py`/`data_product.py`. New `QuerySubjectRef` (a `DatasetRef` with an optional `fieldPath`)
    resolves to either the dataset URN or, when `fieldPath` is set, a `schemaField` URN via the
    already-imported `make_schema_field_urn()`. `created`/`lastModified` use the same deterministic
    `ZERO_AUDIT_STAMP` already defined in `builders/common.py` for glossary terms/links. Exercised in
    the integration fixture (`view-layer/views.yml`, referencing the existing view dataset both at the
    table level and one column).
  - ~~`INCIDENT`~~ **Done, 2026-08-15.** `IncidentDoc` gets only `HasTags` -- the registry permits
    nothing else transverse on `incident`. Raw MCPs again (`incidentInfo`, and `incidentNotes` only
    when `notes:` is non-empty), same shape as `QUERY`. `entities:` takes full URNs directly (no
    `ReferenceIndex` validation), matching `DataProductDoc.assets`'s existing precedent, since the
    entities an incident points at are typically datasets that aren't necessarily declared as their
    own `DATASET` document in this tree. `assignees:` reuses `owner_urn()`. `source.sourceUrn` lets an
    incident reference the `ASSERTION` that triggered it (`incidentExternalLinks` was explicitly
    scoped out -- see "Explicitly out of scope" below). Exercised in the integration fixture
    (`quality-layer/quality.yml`), pointing back at the existing FRESHNESS assertion.
  - ~~`DOCUMENT`~~ **Done, 2026-08-15.** `DocumentDoc` gets 7 of the 9 mixins (owners, tags, terms,
    domain, links, structuredProperties, subTypes -- **not** applications or deprecation, which the
    registry doesn't permit on `document`). Uses the SDK V2 `Document.create_document()` /
    `create_external_document()` factories (no plain constructor) rather than `Document(urn=...)`
    directly. Neither factory has a `links=` kwarg, so `builders/document.py` passes a narrowed
    `native={"owners","tags","terms","domain","subtype"}` to `common_sdk_kwargs()` -- the
    `institutionalMemory` aspect for `links:` still gets emitted, just via `extra_aspects` like every
    other kind whose SDK class doesn't natively support a mixin the document has. **New finding (C8)**:
    unlike every other SDK V2 entity in this connector, these two factories stamp `datetime.now()` on
    `created`/`lastModified` when `created_time`/`last_modified_time` are omitted -- pinned to the Unix
    epoch (`_EPOCH` in `builders/document.py`) for golden-file determinism, the same problem
    `ZERO_AUDIT_STAMP` solves elsewhere via a different code path. `platform:` is required only when
    `externalUrl:` is set (validated in the builder, reported as a warning via `_safe_build()` like
    `container_key()`'s missing-`database` check); a native document without `text:` is rejected the
    same way. Exercised in the integration fixture (new `knowledge-layer/documents.yml`).
  - **Explicitly out of scope for all five kinds** (documented, not silently dropped): `incidentExternalLinks`
    (needs a DataHub `connection` entity, absent from this connector), `chartQuery`, `embed`,
    `inputFields`, `editable*Properties` (UI-owned), `*UsageStatistics` (would use the existing
    `aspectName:` raw passthrough mechanism instead, on demand).

**Phase 4 complete, 2026-08-15** -- all five kinds shipped across five focused commits (one per kind:
`f4ed4cc` CHART, `c63997a` DASHBOARD, `24490ef` QUERY, `19bafcd` INCIDENT, DOCUMENT). Full suite:
140 tests, 97% coverage, no file below 83%. `docs/specs/entity-aspect-coverage-gaps.md` is now fully
implemented end to end (Phases 1-4).

### Verification run

```
python -m pytest tests/unit tests/integration -q       # 119 passed (acryl-datahub==1.7.0.3)
python -m pytest tests/unit tests/integration -q --cov=datahub_yaml_source --cov-report=term-missing
                                                          # 96% coverage, no file below 83%
python scripts/generate_json_schema.py                   # regenerated, checked in
python scripts/generate_markdown_docs.py                 # regenerated, checked in (with the D4 kind-fields-first reordering)
```

Not yet run: a real `datahub ingest` against the full AP-HP `datahub-sample` repo (Verification step 4 in
the plan above) — that requires the actual sample repo and/or a live GMS, neither available in this pass.
The 88-dataset / 64-structured-property real-world load is the next thing to try this against.
