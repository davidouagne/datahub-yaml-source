"""Shared helpers used across builders/*.py."""

from collections.abc import Iterable
from typing import Any, NamedTuple

from datahub.emitter.mce_builder import make_schema_field_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    ApplicationsClass,
    AuditStampClass,
    BooleanTypeClass,
    BytesTypeClass,
    DataPlatformInstanceClass,
    DateTypeClass,
    DeprecationClass,
    DomainsClass,
    FineGrainedLineageClass,
    FineGrainedLineageDownstreamTypeClass,
    FineGrainedLineageUpstreamTypeClass,
    GlobalTagsClass,
    GlossaryTermAssociationClass,
    GlossaryTermsClass,
    InstitutionalMemoryClass,
    InstitutionalMemoryMetadataClass,
    NullTypeClass,
    NumberTypeClass,
    OwnerClass,
    OwnershipClass,
    RecordTypeClass,
    SchemaFieldDataTypeClass,
    StringTypeClass,
    StructuredPropertiesClass,
    StructuredPropertyValueAssignmentClass,
    SubTypesClass,
    TagAssociationClass,
    TimeTypeClass,
    _Aspect,
)

from datahub_yaml_source.models import (
    DeprecationDoc,
    FineGrainedLineageDoc,
    HasApplications,
    HasDeprecation,
    HasDomain,
    HasLinks,
    HasOwners,
    HasStructuredProps,
    HasSubTypes,
    HasTags,
    HasTerms,
    LinkDoc,
    OwnerEntry,
    normalize_owners,
    normalize_sub_types,
)
from datahub_yaml_source.urns import (
    ReferenceIndex,
    application_urn,
    data_platform_instance_urn,
    data_platform_urn,
    dataset_urn,
    domain_urn,
    glossary_term_urn,
    owner_urn,
    structured_property_urn,
    tag_urn,
)
from datahub_yaml_source.yaml_source_report import YamlSourceReport

DEFAULT_ACTOR_URN = "urn:li:corpuser:datahub"
ZERO_AUDIT_STAMP = AuditStampClass(time=0, actor=DEFAULT_ACTOR_URN)

# Every value is one of the classes `SchemaFieldDataTypeClass(type=...)` accepts;
# the explicit union keeps that guarantee visible to the type checker.
_SchemaNativeType = (
    type[NumberTypeClass]
    | type[StringTypeClass]
    | type[BooleanTypeClass]
    | type[DateTypeClass]
    | type[TimeTypeClass]
    | type[BytesTypeClass]
    | type[RecordTypeClass]
    | type[NullTypeClass]
)

_TYPE_MAP: dict[str, _SchemaNativeType] = {
    "number": NumberTypeClass,
    "string": StringTypeClass,
    "boolean": BooleanTypeClass,
    "date": DateTypeClass,
    "time": TimeTypeClass,
    "bytes": BytesTypeClass,
    "record": RecordTypeClass,
}


def schema_field_data_type(source_type: str) -> SchemaFieldDataTypeClass:
    type_cls = _TYPE_MAP.get(source_type.lower(), NullTypeClass)
    return SchemaFieldDataTypeClass(type=type_cls())


def owners_to_sdk_input(owners: list[OwnerEntry]) -> list[tuple[str, str]]:
    """Owner input for SDK V2 entities: list of (owner_urn, ownership_type) tuples."""
    return [(owner_urn(o.owner), o.type) for o in owners]


def build_ownership_aspect(owners: list[OwnerEntry]) -> OwnershipClass | None:
    """Ownership aspect for kinds without SDK V2 support (raw MCP emission)."""
    if not owners:
        return None
    return OwnershipClass(
        owners=[OwnerClass(owner=owner_urn(o.owner), type=o.type) for o in owners]
    )


def build_global_tags_aspect(tag_names: list[str] | None) -> GlobalTagsClass | None:
    if not tag_names:
        return None
    return GlobalTagsClass(tags=[TagAssociationClass(tag=tag_urn(t)) for t in tag_names])


def build_glossary_terms_aspect(
    term_ids: list[str] | None,
) -> GlossaryTermsClass | None:
    if not term_ids:
        return None
    return GlossaryTermsClass(
        terms=[GlossaryTermAssociationClass(urn=glossary_term_urn(t)) for t in term_ids],
        auditStamp=AuditStampClass(time=0, actor=DEFAULT_ACTOR_URN),
    )


def build_domains_aspect(domain_id: str | None) -> DomainsClass | None:
    if not domain_id:
        return None
    return DomainsClass(domains=[domain_urn(domain_id)])


def stringify_custom_properties(properties: dict[str, Any] | None) -> dict[str, str] | None:
    """customProperties aspects require Dict[str, str]; coerce non-str values."""
    if not properties:
        return None
    return {k: v if isinstance(v, str) else str(v) for k, v in properties.items()}


def build_fine_grained_lineage_list(
    fgl_docs: list[FineGrainedLineageDoc] | None,
) -> list[FineGrainedLineageClass] | None:
    if not fgl_docs:
        return None
    return [
        FineGrainedLineageClass(
            upstreamType=FineGrainedLineageUpstreamTypeClass.FIELD_SET,
            downstreamType=FineGrainedLineageDownstreamTypeClass.FIELD,
            # `upstream` is absent for e.g. `operation: CONSTANT` -- a literal
            # value assigned to the downstream field with no source column.
            upstreams=(
                [make_schema_field_urn(dataset_urn(fg.upstream), fg.upstream.fieldPath)]
                if fg.upstream is not None
                else []
            ),
            downstreams=[
                make_schema_field_urn(dataset_urn(fg.downstream), fg.downstream.fieldPath)
            ],
            transformOperation=fg.operation,
            confidenceScore=fg.confidence,
        )
        for fg in fgl_docs
    ]


def mcp_workunit(entity_urn: str, aspect: _Aspect) -> MetadataWorkUnit:
    return MetadataChangeProposalWrapper(entityUrn=entity_urn, aspect=aspect).as_workunit()


# --- Cross-cutting aspect builders ------------------------------------------
#
# One function per common aspect, each usable both as an SDK V2 `extra_aspects`
# entry and as a standalone follow-up MCP. `common_sdk_kwargs()` and
# `common_aspect_mcps()` below dispatch across all of them based on which
# `Has*` mixin (see models.py) a given document actually inherited, so a kind
# automatically gets whatever the entity registry allows it and nothing else.


def build_deprecation_aspect(dep: DeprecationDoc | None) -> DeprecationClass | None:
    if dep is None:
        return None
    return DeprecationClass(
        deprecated=dep.deprecated,
        # `Deprecation.pdl` declares `note: string` as required, not optional,
        # despite the generated Python stub's `Optional[str]` hint -- passing
        # `None` here parses fine but fails MCP.validate()'s Avro schema
        # check at emit time, silently taking down the whole ingestion run.
        note=dep.note or "",
        decommissionTime=dep.decommissionTime,
        actor=owner_urn(dep.actor) if dep.actor else DEFAULT_ACTOR_URN,
    )


def _link_association(link: LinkDoc) -> InstitutionalMemoryMetadataClass:
    return InstitutionalMemoryMetadataClass(
        url=link.url,
        description=link.description or link.url,
        createStamp=ZERO_AUDIT_STAMP,
    )


def build_link_associations(
    links: list[LinkDoc] | None,
) -> list[InstitutionalMemoryMetadataClass] | None:
    """`links=` input for an SDK V2 constructor -- deterministic (time=0) audit stamp."""
    if not links:
        return None
    return [_link_association(link) for link in links]


def build_links_aspect(links: list[LinkDoc] | None) -> InstitutionalMemoryClass | None:
    """Standalone `institutionalMemory` aspect, for raw-MCP kinds and container follow-ups."""
    associations = build_link_associations(links)
    if not associations:
        return None
    return InstitutionalMemoryClass(elements=associations)


def _normalize_structured_property_values(value: Any) -> list[str | float]:  # noqa: ANN401
    # `value` is one raw YAML structuredProperties value -- genuinely
    # heterogeneous (a scalar or a list of scalars of unknown type),
    # normalized below via isinstance checks.
    values = value if isinstance(value, list) else [value]
    return [v if isinstance(v, int | float) else str(v) for v in values]


def build_structured_properties_aspect(
    properties: dict[str, Any] | None,
    index: ReferenceIndex,
    report: YamlSourceReport,
    context: str,
) -> StructuredPropertiesClass | None:
    """Always built directly (never via the SDK's `structured_properties=` kwarg,
    nor `gen_containers()`'s `structured_properties=` kwarg): both of those call
    `HasStructuredProperties.set_structured_property()` / a single-value UPSERT
    path, which either stamps a non-deterministic `datetime.now()` audit stamp
    or silently drops all but one value for a MULTIPLE-cardinality property."""
    if not properties:
        return None
    for qualified_name in properties:
        if not index.has_structured_property(qualified_name):
            report.report_dangling_reference(
                f"{context} references undeclared structuredProperty '{qualified_name}'"
            )
    return StructuredPropertiesClass(
        properties=[
            StructuredPropertyValueAssignmentClass(
                propertyUrn=structured_property_urn(qualified_name),
                values=_normalize_structured_property_values(value),
            )
            for qualified_name, value in properties.items()
        ]
    )


def build_applications_aspect(
    app_ids: list[str] | None,
    index: ReferenceIndex,
    report: YamlSourceReport,
    context: str,
) -> ApplicationsClass | None:
    if not app_ids:
        return None
    urns = []
    for app_id in app_ids:
        if not index.has_application(app_id):
            report.report_dangling_reference(
                f"{context} references undeclared application '{app_id}'"
            )
        urns.append(application_urn(app_id))
    return ApplicationsClass(applications=urns)


def build_subtypes_aspect(sub_types: list[str]) -> SubTypesClass | None:
    if not sub_types:
        return None
    return SubTypesClass(typeNames=sub_types)


def build_data_platform_instance_aspect(
    platform: str | None, instance: str | None
) -> DataPlatformInstanceClass | None:
    """For the software/AI catalog kinds (SERVICE/API/REPOSITORY/AI_AGENT/AGENT_SKILL,
    Phase 5C): their URNs are a bare id with no platform component, so this is the
    only way to say "this repository lives on GitLab" / "this service runs on
    cluster X". No `Has*` mixin carries this -- it isn't shared by any other kind
    in the connector -- so it's built directly by each Phase 5C builder rather
    than dispatched from `common_sdk_kwargs()`/`common_aspect_mcps()`."""
    if not platform:
        return None
    return DataPlatformInstanceClass(
        platform=data_platform_urn(platform),
        instance=data_platform_instance_urn(platform, instance),
    )


#: Every SDK V2 entity class in this connector accepts all six as constructor
#: kwargs (Dataset, DataFlow, DataJob) -- the default for `native=`.
FULL_NATIVE_KWARGS: frozenset[str] = frozenset(
    {"owners", "tags", "terms", "domain", "links", "subtype"}
)


class _RefContext(NamedTuple):
    """Bundles the (index, report, context) triple threaded through the
    per-mixin helpers below, so each helper stays within ruff's PLR0913
    argument-count threshold without changing `common_sdk_kwargs`'/
    `common_aspect_mcps`'s own public signatures. The index field is named
    `ref_index`, not `index`: a NamedTuple field named `index` shadows the
    inherited `tuple.index()` method, which mypy --strict flags.
    """

    ref_index: ReferenceIndex
    report: YamlSourceReport
    context: str


def _add_owners_kwarg(
    doc: object, native: frozenset[str], kwargs: dict[str, Any], extra_aspects: list[Any]
) -> None:
    if not isinstance(doc, HasOwners):
        return
    owners = owners_to_sdk_input(normalize_owners(doc.owners)) or None
    if "owners" in native:
        kwargs["owners"] = owners
    elif owners:
        extra_aspects.append(build_ownership_aspect(normalize_owners(doc.owners)))


def _add_tags_kwarg(
    doc: object,
    ref: _RefContext,
    native: frozenset[str],
    kwargs: dict[str, Any],
    extra_aspects: list[Any],
) -> None:
    if not isinstance(doc, HasTags):
        return
    tags = []
    for tag_name in doc.tags or []:
        if not ref.ref_index.has_tag(tag_name):
            ref.report.report_dangling_reference(
                f"{ref.context} references undeclared tag '{tag_name}'"
            )
        tags.append(tag_urn(tag_name))
    if "tags" in native:
        kwargs["tags"] = tags or None
    elif tags:
        extra_aspects.append(GlobalTagsClass(tags=[TagAssociationClass(tag=t) for t in tags]))


def _add_terms_kwarg(
    doc: object,
    ref: _RefContext,
    native: frozenset[str],
    kwargs: dict[str, Any],
    extra_aspects: list[Any],
) -> None:
    if not isinstance(doc, HasTerms):
        return
    terms = []
    for term_id in doc.glossaryTerms or []:
        if not ref.ref_index.has_glossary_term(term_id):
            ref.report.report_dangling_reference(
                f"{ref.context} references undeclared glossaryTerm '{term_id}'"
            )
        terms.append(glossary_term_urn(term_id))
    if "terms" in native:
        kwargs["terms"] = terms or None
    elif terms:
        extra_aspects.append(
            GlossaryTermsClass(
                terms=[GlossaryTermAssociationClass(urn=t) for t in terms],
                auditStamp=ZERO_AUDIT_STAMP,
            )
        )


def _add_domain_kwarg(
    doc: object,
    ref: _RefContext,
    native: frozenset[str],
    kwargs: dict[str, Any],
    extra_aspects: list[Any],
) -> None:
    if not isinstance(doc, HasDomain):
        return
    domain = None
    if doc.domains:
        if not ref.ref_index.has_domain(doc.domains):
            ref.report.report_dangling_reference(
                f"{ref.context} references undeclared domain '{doc.domains}'"
            )
        domain = domain_urn(doc.domains)
    if "domain" in native:
        kwargs["domain"] = domain
    elif domain:
        extra_aspects.append(DomainsClass(domains=[domain]))


def _add_links_kwarg(
    doc: object, native: frozenset[str], kwargs: dict[str, Any], extra_aspects: list[Any]
) -> None:
    if not isinstance(doc, HasLinks):
        return
    links = build_link_associations(doc.links)
    if "links" in native:
        kwargs["links"] = links
    elif links:
        extra_aspects.append(InstitutionalMemoryClass(elements=links))


def _add_subtype_kwarg(
    doc: object, native: frozenset[str], kwargs: dict[str, Any], extra_aspects: list[Any]
) -> None:
    if not isinstance(doc, HasSubTypes):
        return
    sub_types = normalize_sub_types(doc.subTypes)
    if "subtype" in native and len(sub_types) <= 1:
        kwargs["subtype"] = sub_types[0] if sub_types else None
    elif sub_types:
        # Either the target class has no `subtype=` kwarg at all, or
        # there's more than one subtype -- SDK V2's `subtype=` kwarg only
        # stores a single typeName, and subtypes are additive, so
        # dropping all but the first would be a silent bug.
        extra_aspects.append(build_subtypes_aspect(sub_types))


def _add_applications_extra(doc: object, ref: _RefContext, extra_aspects: list[Any]) -> None:
    if not isinstance(doc, HasApplications):
        return
    apps_aspect = build_applications_aspect(
        doc.applications, ref.ref_index, ref.report, ref.context
    )
    if apps_aspect:
        extra_aspects.append(apps_aspect)


def _add_deprecation_extra(doc: object, extra_aspects: list[Any]) -> None:
    if not isinstance(doc, HasDeprecation):
        return
    dep_aspect = build_deprecation_aspect(doc.deprecation)
    if dep_aspect:
        extra_aspects.append(dep_aspect)


def _add_structured_props_extra(doc: object, ref: _RefContext, extra_aspects: list[Any]) -> None:
    if not isinstance(doc, HasStructuredProps):
        return
    sp_aspect = build_structured_properties_aspect(
        doc.structuredProperties, ref.ref_index, ref.report, ref.context
    )
    if sp_aspect:
        extra_aspects.append(sp_aspect)


def common_sdk_kwargs(
    doc: object,
    index: ReferenceIndex,
    report: YamlSourceReport,
    context: str,
    *,
    native: frozenset[str] = FULL_NATIVE_KWARGS,
) -> dict[str, Any]:
    """Cross-cutting aspect kwargs for an SDK V2-backed kind.

    Not every SDK V2 entity wrapper implements the same `Has*` mixins as the
    next one -- e.g. `Tag` has no `tags=`/`terms=`/`domain=`/`links=`/`subtype=`
    at all, and `GlossaryNode`/`GlossaryTerm` support only some of them
    (verified by inspecting each class's actual `__mro__`). `native` names
    which of owners/tags/terms/domain/links/subtype the *target* SDK
    constructor genuinely accepts; a mixin the document has but the target
    class doesn't natively support still gets its aspect emitted -- just via
    `extra_aspects` as a standalone aspect instead of a constructor kwarg.

    `applications`, `deprecation`, and `structuredProperties` are never
    constructor kwargs regardless of `native`: the SDK has no
    `applications=`/`deprecation=` kwarg on any entity, and its
    `structured_properties=` kwarg routes through
    `HasStructuredProperties.set_structured_property()`, which stamps a
    non-deterministic `datetime.now()` audit stamp (see
    `build_structured_properties_aspect()`).
    """
    kwargs: dict[str, Any] = {}
    extra_aspects: list[Any] = []
    ref = _RefContext(index, report, context)

    _add_owners_kwarg(doc, native, kwargs, extra_aspects)
    _add_tags_kwarg(doc, ref, native, kwargs, extra_aspects)
    _add_terms_kwarg(doc, ref, native, kwargs, extra_aspects)
    _add_domain_kwarg(doc, ref, native, kwargs, extra_aspects)
    _add_links_kwarg(doc, native, kwargs, extra_aspects)
    _add_subtype_kwarg(doc, native, kwargs, extra_aspects)
    _add_applications_extra(doc, ref, extra_aspects)
    _add_deprecation_extra(doc, extra_aspects)
    _add_structured_props_extra(doc, ref, extra_aspects)

    kwargs["extra_aspects"] = extra_aspects or None
    return kwargs


def _owners_mcps(entity_urn: str, doc: object) -> Iterable[MetadataWorkUnit]:
    if not isinstance(doc, HasOwners):
        return
    ownership = build_ownership_aspect(normalize_owners(doc.owners))
    if ownership:
        yield mcp_workunit(entity_urn, ownership)


def _tags_mcps(entity_urn: str, doc: object, ref: _RefContext) -> Iterable[MetadataWorkUnit]:
    if not isinstance(doc, HasTags):
        return
    for tag_name in doc.tags or []:
        if not ref.ref_index.has_tag(tag_name):
            ref.report.report_dangling_reference(
                f"{ref.context} references undeclared tag '{tag_name}'"
            )
    tags_aspect = build_global_tags_aspect(doc.tags)
    if tags_aspect:
        yield mcp_workunit(entity_urn, tags_aspect)


def _terms_mcps(entity_urn: str, doc: object, ref: _RefContext) -> Iterable[MetadataWorkUnit]:
    if not isinstance(doc, HasTerms):
        return
    for term_id in doc.glossaryTerms or []:
        if not ref.ref_index.has_glossary_term(term_id):
            ref.report.report_dangling_reference(
                f"{ref.context} references undeclared glossaryTerm '{term_id}'"
            )
    terms_aspect = build_glossary_terms_aspect(doc.glossaryTerms)
    if terms_aspect:
        yield mcp_workunit(entity_urn, terms_aspect)


def _domain_mcps(entity_urn: str, doc: object, ref: _RefContext) -> Iterable[MetadataWorkUnit]:
    if not (isinstance(doc, HasDomain) and doc.domains):
        return
    if not ref.ref_index.has_domain(doc.domains):
        ref.report.report_dangling_reference(
            f"{ref.context} references undeclared domain '{doc.domains}'"
        )
    domains_aspect = build_domains_aspect(doc.domains)
    if domains_aspect is None:
        # Guaranteed unreachable: build_domains_aspect() only returns None
        # for a falsy domain_id, and doc.domains is already known-truthy
        # above. A plain `if`/`raise`, not `assert`, so this narrowing isn't
        # silently compiled away under `python -O`.
        raise AssertionError("build_domains_aspect() returned None for a truthy domain_id")
    yield mcp_workunit(entity_urn, domains_aspect)


def _applications_mcps(
    entity_urn: str, doc: object, ref: _RefContext
) -> Iterable[MetadataWorkUnit]:
    if not isinstance(doc, HasApplications):
        return
    apps_aspect = build_applications_aspect(
        doc.applications, ref.ref_index, ref.report, ref.context
    )
    if apps_aspect:
        yield mcp_workunit(entity_urn, apps_aspect)


def _links_mcps(entity_urn: str, doc: object) -> Iterable[MetadataWorkUnit]:
    if not isinstance(doc, HasLinks):
        return
    links_aspect = build_links_aspect(doc.links)
    if links_aspect:
        yield mcp_workunit(entity_urn, links_aspect)


def _deprecation_mcps(entity_urn: str, doc: object) -> Iterable[MetadataWorkUnit]:
    if not isinstance(doc, HasDeprecation):
        return
    dep_aspect = build_deprecation_aspect(doc.deprecation)
    if dep_aspect:
        yield mcp_workunit(entity_urn, dep_aspect)


def _structured_props_mcps(
    entity_urn: str, doc: object, ref: _RefContext
) -> Iterable[MetadataWorkUnit]:
    if not isinstance(doc, HasStructuredProps):
        return
    sp_aspect = build_structured_properties_aspect(
        doc.structuredProperties, ref.ref_index, ref.report, ref.context
    )
    if sp_aspect:
        yield mcp_workunit(entity_urn, sp_aspect)


def _subtypes_mcps(entity_urn: str, doc: object) -> Iterable[MetadataWorkUnit]:
    if not isinstance(doc, HasSubTypes):
        return
    subtypes_aspect = build_subtypes_aspect(normalize_sub_types(doc.subTypes))
    if subtypes_aspect:
        yield mcp_workunit(entity_urn, subtypes_aspect)


def common_aspect_mcps(  # noqa: PLR0913
    entity_urn: str,
    doc: object,
    index: ReferenceIndex,
    report: YamlSourceReport,
    context: str,
    *,
    skip: frozenset[str] = frozenset(),
) -> Iterable[MetadataWorkUnit]:
    """Cross-cutting aspects as standalone follow-up MCPs, for raw-MCP kinds
    (DOMAIN, APPLICATION, DATA_PRODUCT, ASSERTION) and for CONTAINER, which
    gets some of these natively from `gen_containers()` and needs the rest
    (`skip=` names which ones `gen_containers()` already handled) emitted here.

    `entity_urn, doc, index, report, context` is this connector's standard
    cross-cutting-aspect argument bundle (see every `builders/*.py` build_*
    function) plus the `skip=` this specific cross-cutting helper needs --
    the argument list *is* the interface here, not accidental complexity.
    """
    ref = _RefContext(index, report, context)
    if "owners" not in skip:
        yield from _owners_mcps(entity_urn, doc)
    if "tags" not in skip:
        yield from _tags_mcps(entity_urn, doc, ref)
    if "terms" not in skip:
        yield from _terms_mcps(entity_urn, doc, ref)
    if "domain" not in skip:
        yield from _domain_mcps(entity_urn, doc, ref)
    if "applications" not in skip:
        yield from _applications_mcps(entity_urn, doc, ref)
    if "links" not in skip:
        yield from _links_mcps(entity_urn, doc)
    if "deprecation" not in skip:
        yield from _deprecation_mcps(entity_urn, doc)
    if "structuredProperties" not in skip:
        yield from _structured_props_mcps(entity_urn, doc, ref)
    if "subTypes" not in skip:
        yield from _subtypes_mcps(entity_urn, doc)
