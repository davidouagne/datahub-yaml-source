# Spec — ML, Semantic-Layer, and Software/AI Catalog Entities (Phase 5)

**Reference DataHub version**: `acryl-datahub==1.7.0.3` installed SDK, cross-checked against
`metadata-models/src/main/resources/entity-registry.yml` and the relevant `.pdl` sources in
`C:/Users/4087446/Projects/datahub-project/datahub`.
**Connector under spec**: `C:/Users/4087446/Projects/aphp/datahub-yaml-source` (branch `main`)
**Status**: **IMPLEMENTED** (2026-08-16) — all 12 kinds shipped. This document records the
requirements and verified facts for the 12 entity kinds `docs/specs/entity-aspect-coverage-gaps.md`
had deferred to its Future Considerations table (as "no current AP-HP use case" for the ML entities,
and "brand new in this DataHub release; premature to encode" for the v1.7 entities). See
`_PLANNING.md`'s "ML / semantic / software-catalog entities — Phase 5" section for the full
implementation history, corrections (C9, C10), and emission order.

---

## Context

The connector's original spec (`entity-aspect-coverage-gaps.md`) deliberately deferred two groups of
entities rather than build them speculatively:

- **ML entities** (`MLMODEL`, `MLMODEL_GROUP`, `MLFEATURE_TABLE`, `MLFEATURE`, `MLPRIMARY_KEY`) — no
  AP-HP use case had been expressed yet.
- **v1.7 entities** (`SEMANTIC_MODEL`, `METRIC`, `SERVICE`, `API`, `REPOSITORY`, `AI_AGENT`,
  `AGENT_SKILL`) — new additions to the DataHub entity model at the time, judged premature to encode
  into a stable authoring format.

The user requested lifting both deferrals in one pass, explicitly choosing (a) a **full model card**
for `MLMODEL` (not just its core properties) and (b) **one commit per family** (3 commits: ML,
semantic layer, software/AI catalog) rather than one per kind as Phase 4 used.

## Goals

1. Author all 12 kinds as YAML documents, following the same discriminated-`kind:` pattern as every
   existing entity in the connector.
2. Every field maps to a real, registry-permitted aspect — verified against the installed SDK and the
   entity registry before writing code, not assumed from the DataHub docs site.
3. `MLMODEL` carries the complete model card (intended use, ethical considerations, caveats,
   training/evaluation data, factor prompts, metrics, source code) — all 8 aspects, not a subset.
4. Cross-cutting metadata (`owners`/`tags`/`glossaryTerms`/`domains`/`links`/`deprecation`/
   `structuredProperties`/`subTypes`) follows exactly what the entity registry permits per kind, same
   as every other kind in the connector — no kind gets an aspect the registry doesn't list for it.
5. Golden-file and unit-test coverage for all 12 kinds, at the same rigor as Phases 1-4.

## Non-Goals

| Not doing | Why |
|---|---|
| `versionProperties` on `API`/`AI_AGENT`/`AGENT_SKILL` | References a `VERSION_SET` entity this connector doesn't model — already in the original spec's Future Considerations. |
| `semanticContent` (vector embeddings) on all 5 software/AI kinds | System-computed by an embedding pipeline; not hand-authorable. |
| `incidentsSummary` (`SERVICE`/`AI_AGENT`) and `browsePathsV2` (`REPOSITORY`) | System-computed, consistent with the connector's existing Non-Goals policy. |
| `upstreamLineage` on `AI_AGENT` | Would need a lineage mechanism this connector doesn't model for non-dataset entities. |
| `apiSignature.inputFields`/`.outputFields` (structured schema) | Only the free-text `schemaDefinition` is exposed; a full typed field list was judged out of scope for a first pass. |
| `cost` on `MLMODEL` | A financial discriminated-union aspect outside the usual "model card" concept (the original Model Card paper doesn't cover cost either); no expressed use case. |
| Any new `@capability` decorator | DataHub's `SourceCapability` enum has no dedicated value for ML/semantic/software-catalog entities — same situation as `DATA_PRODUCT`/`ASSERTION`/the BI kinds already in the connector. |

## Coverage Matrix (as shipped)

Verified cell-by-cell against `entity-registry.yml` and the installed SDK's real class signatures —
see `_PLANNING.md`'s mixin→kind matrix for the full table including these rows.

| Kind | SDK mechanism | Cross-cutting mixins | Notable divergence from a "normal" kind |
|---|---|---|---|
| `MLFEATURE_TABLE` | Raw MCP | Full 9-mixin set | None |
| `MLFEATURE` | Raw MCP | Full 9-mixin set | URN key is `(featureNamespace, name)`, not `(platform, name)` |
| `MLPRIMARY_KEY` | Raw MCP | Full 9-mixin set | Same key shape as `MLFEATURE`; `sources` required (not optional) |
| `MLMODEL_GROUP` | SDK V2 `MLModelGroup` | Full 9-mixin set | `native=` narrowed to `{owners,tags,terms,domain,links}` — no `subtype=`/`applications=`/`container=` constructor kwarg despite the registry permitting all three |
| `MLMODEL` | SDK V2 `MLModel` | Full 9-mixin set | Same narrowed `native=`; the 8 model-card aspects are plain fields on `MLModelDoc`, not a shared mixin (valid only on `mlModel`) |
| `SEMANTIC_MODEL` | SDK V2 `SemanticModel` | Full 9-mixin set | Same narrowed `native=`; 3-part URN key `(platform, path, id)` |
| `METRIC` | SDK V2 `Metric` | Full 9-mixin set | Same narrowed `native=`; `semantic_model=` is a **required** constructor kwarg — real emission-order dependency |
| `REPOSITORY` | Raw MCP | owners/tags/terms/domain/links/structProps/subTypes (no applications/deprecation) | Bare-id URN; `dataPlatformInstance` in scope (see Decision below) |
| `API` | Raw MCP | Same subset as `REPOSITORY` | Bare-id URN; `dataPlatformInstance` in scope |
| `AGENT_SKILL` | Raw MCP | owners/tags/terms/domain/links/structProps (no applications/deprecation/subTypes) | Bare-id URN; `requiredTools` is `array[Urn]` (entityTypes `[api]`) in the PDL, not free text |
| `AI_AGENT` | Raw MCP | Same subset as `AGENT_SKILL` | Bare-id URN; `aiAgentInfo.created`/`.lastModified` required (pinned to epoch); `dependencies.{skills,tools,models}` all `array[Urn]` |
| `SERVICE` | Raw MCP | **owners/tags/subTypes only** | The most restricted kind in the connector — no domain/terms/links/deprecation/structuredProperties at all |

## Decisions

### Model card depth: full, not core-only

Per explicit user choice. All 8 model-card aspects (`intendedUse`, `ethicalConsiderations`,
`caveatsAndRecommendations`, `trainingData`, `evaluationData`, `factorPrompts`, `metrics`,
`sourceCode`) are implemented as plain fields on `MLModelDoc`, following decision D1's rule that
`Has*` mixins are for aspects shared *across* kinds — none of these 8 are valid on any kind besides
`mlModel`.

### Commit granularity: one per family

Per explicit user choice, given the larger batch size (12 kinds) than Phase 4's 5: **5A** (ML
entities, `9804975`), **5B** (semantic layer, `64493e3`), **5C** (software/AI catalog).

### `dataPlatformInstance` brought into scope for the 5 software/AI kinds

Not in the original spec sketch — arbitrated during Phase 5C planning. `REPOSITORY`/`API`/
`AGENT_SKILL`/`AI_AGENT`/`SERVICE` are the only kinds in the connector whose URN is a bare id with no
platform component (every other kind's URN embeds `platform` directly). Without `dataPlatformInstance`
there would be no way at all to say "this repository lives on GitLab" or "this service runs on
cluster X". A `platform`/`instance` field pair on each of the 5 Docs feeds a new
`build_data_platform_instance_aspect()` helper (`builders/common.py`), called directly by each Phase
5C builder — not a `Has*` mixin, since no other kind in the connector uses this aspect.

### Software/AI catalog is a genuine scope widening, documented explicitly

Phase 5C's 5 kinds catalog software artifacts (a Git repository, a REST endpoint, an AI agent, a
running service), not data assets — a change in the connector's *subject matter*, not just its kind
count. `docs/sources/yaml/yaml.md` calls this out explicitly in its own scope note rather than folding
it silently into the kind table.

## Verification

Same methodology as every prior phase (see `_PLANNING.md`'s Verification section): unit tests for
every builder and loader path, the two generator scripts re-run and diffed, the full suite with
coverage, and a structural golden-file diff (old vs. regenerated, `systemMetadata` stripped, sorted by
`(entityUrn, aspectName)`) confirming only ADDED rows for the new URNs with zero REMOVED/CHANGED.

Final state after all 3 sub-phases: **157 tests, 98% coverage**, zero dangling references / unknown
fields on the integration fixture tree, `acryl-datahub==1.7.0.3`. No live ingestion against the real
AP-HP `datahub-sample` repo was performed for this batch — that repo doesn't declare any of these 12
kinds yet; recommended if/when AP-HP has real examples to contribute.
