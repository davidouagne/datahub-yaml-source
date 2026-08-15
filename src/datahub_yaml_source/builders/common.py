"""Shared helpers used across builders/*.py."""

from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple, Union

from datahub.emitter.mce_builder import make_schema_field_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    ApplicationsClass,
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
)
from datahub.metadata.schema_classes import AuditStampClass

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

DEFAULT_ACTOR_URN = "urn:li:corpuser:datahub"
ZERO_AUDIT_STAMP = AuditStampClass(time=0, actor=DEFAULT_ACTOR_URN)

_TYPE_MAP = {
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


def owners_to_sdk_input(owners: List[OwnerEntry]) -> List[Tuple[str, str]]:
    """Owner input for SDK V2 entities: list of (owner_urn, ownership_type) tuples."""
    return [(owner_urn(o.owner), o.type) for o in owners]


def build_ownership_aspect(owners: List[OwnerEntry]) -> Optional[OwnershipClass]:
    """Ownership aspect for kinds without SDK V2 support (raw MCP emission)."""
    if not owners:
        return None
    return OwnershipClass(
        owners=[OwnerClass(owner=owner_urn(o.owner), type=o.type) for o in owners]
    )


def build_global_tags_aspect(tag_names: Optional[List[str]]) -> Optional[GlobalTagsClass]:
    if not tag_names:
        return None
    return GlobalTagsClass(tags=[TagAssociationClass(tag=tag_urn(t)) for t in tag_names])


def build_glossary_terms_aspect(
    term_ids: Optional[List[str]],
) -> Optional[GlossaryTermsClass]:
    if not term_ids:
        return None
    return GlossaryTermsClass(
        terms=[
            GlossaryTermAssociationClass(urn=glossary_term_urn(t)) for t in term_ids
        ],
        auditStamp=AuditStampClass(time=0, actor=DEFAULT_ACTOR_URN),
    )


def build_domains_aspect(domain_id: Optional[str]) -> Optional[DomainsClass]:
    if not domain_id:
        return None
    return DomainsClass(domains=[domain_urn(domain_id)])


def stringify_custom_properties(properties: Optional[dict]) -> Optional[dict]:
    """customProperties aspects require Dict[str, str]; coerce non-str values."""
    if not properties:
        return None
    return {k: v if isinstance(v, str) else str(v) for k, v in properties.items()}


def build_fine_grained_lineage_list(
    fgl_docs: Optional[List[FineGrainedLineageDoc]],
) -> Optional[List[FineGrainedLineageClass]]:
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
            downstreams=[make_schema_field_urn(dataset_urn(fg.downstream), fg.downstream.fieldPath)],
            transformOperation=fg.operation,
            confidenceScore=fg.confidence,
        )
        for fg in fgl_docs
    ]


def mcp_workunit(entity_urn: str, aspect) -> MetadataWorkUnit:
    return MetadataChangeProposalWrapper(entityUrn=entity_urn, aspect=aspect).as_workunit()


# --- Cross-cutting aspect builders ------------------------------------------
#
# One function per common aspect, each usable both as an SDK V2 `extra_aspects`
# entry and as a standalone follow-up MCP. `common_sdk_kwargs()` and
# `common_aspect_mcps()` below dispatch across all of them based on which
# `Has*` mixin (see models.py) a given document actually inherited, so a kind
# automatically gets whatever the entity registry allows it and nothing else.


def build_deprecation_aspect(dep: Optional[DeprecationDoc]) -> Optional[DeprecationClass]:
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


def build_link_associations(links: Optional[List[LinkDoc]]) -> Optional[List[InstitutionalMemoryMetadataClass]]:
    """`links=` input for an SDK V2 constructor -- deterministic (time=0) audit stamp."""
    if not links:
        return None
    return [_link_association(link) for link in links]


def build_links_aspect(links: Optional[List[LinkDoc]]) -> Optional[InstitutionalMemoryClass]:
    """Standalone `institutionalMemory` aspect, for raw-MCP kinds and container follow-ups."""
    associations = build_link_associations(links)
    if not associations:
        return None
    return InstitutionalMemoryClass(elements=associations)


def _normalize_structured_property_values(value: Any) -> List[Union[str, float]]:
    values = value if isinstance(value, list) else [value]
    return [v if isinstance(v, (int, float)) else str(v) for v in values]


def build_structured_properties_aspect(
    properties: Optional[Dict[str, Any]],
    index,
    report,
    context: str,
) -> Optional[StructuredPropertiesClass]:
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
    app_ids: Optional[List[str]], index, report, context: str
) -> Optional[ApplicationsClass]:
    if not app_ids:
        return None
    urns = []
    for app_id in app_ids:
        if not index.has_application(app_id):
            report.report_dangling_reference(f"{context} references undeclared application '{app_id}'")
        urns.append(application_urn(app_id))
    return ApplicationsClass(applications=urns)


def build_subtypes_aspect(sub_types: List[str]) -> Optional[SubTypesClass]:
    if not sub_types:
        return None
    return SubTypesClass(typeNames=sub_types)


def build_data_platform_instance_aspect(
    platform: Optional[str], instance: Optional[str]
) -> Optional[DataPlatformInstanceClass]:
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
FULL_NATIVE_KWARGS: FrozenSet[str] = frozenset({"owners", "tags", "terms", "domain", "links", "subtype"})


def common_sdk_kwargs(
    doc, index, report, context: str, *, native: FrozenSet[str] = FULL_NATIVE_KWARGS
) -> Dict[str, Any]:
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
    kwargs: Dict[str, Any] = {}
    extra_aspects: List[Any] = []

    if isinstance(doc, HasOwners):
        owners = owners_to_sdk_input(normalize_owners(doc.owners)) or None
        if "owners" in native:
            kwargs["owners"] = owners
        elif owners:
            extra_aspects.append(build_ownership_aspect(normalize_owners(doc.owners)))

    if isinstance(doc, HasTags):
        tags = []
        for tag_name in doc.tags or []:
            if not index.has_tag(tag_name):
                report.report_dangling_reference(f"{context} references undeclared tag '{tag_name}'")
            tags.append(tag_urn(tag_name))
        if "tags" in native:
            kwargs["tags"] = tags or None
        elif tags:
            extra_aspects.append(GlobalTagsClass(tags=[TagAssociationClass(tag=t) for t in tags]))

    if isinstance(doc, HasTerms):
        terms = []
        for term_id in doc.glossaryTerms or []:
            if not index.has_glossary_term(term_id):
                report.report_dangling_reference(f"{context} references undeclared glossaryTerm '{term_id}'")
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

    if isinstance(doc, HasDomain):
        domain = None
        if doc.domains:
            if not index.has_domain(doc.domains):
                report.report_dangling_reference(f"{context} references undeclared domain '{doc.domains}'")
            domain = domain_urn(doc.domains)
        if "domain" in native:
            kwargs["domain"] = domain
        elif domain:
            extra_aspects.append(DomainsClass(domains=[domain]))

    if isinstance(doc, HasLinks):
        links = build_link_associations(doc.links)
        if "links" in native:
            kwargs["links"] = links
        elif links:
            extra_aspects.append(InstitutionalMemoryClass(elements=links))

    if isinstance(doc, HasSubTypes):
        sub_types = normalize_sub_types(doc.subTypes)
        if "subtype" in native and len(sub_types) <= 1:
            kwargs["subtype"] = sub_types[0] if sub_types else None
        elif sub_types:
            # Either the target class has no `subtype=` kwarg at all, or
            # there's more than one subtype -- SDK V2's `subtype=` kwarg only
            # stores a single typeName, and subtypes are additive, so
            # dropping all but the first would be a silent bug.
            extra_aspects.append(build_subtypes_aspect(sub_types))

    if isinstance(doc, HasApplications):
        apps_aspect = build_applications_aspect(doc.applications, index, report, context)
        if apps_aspect:
            extra_aspects.append(apps_aspect)

    if isinstance(doc, HasDeprecation):
        dep_aspect = build_deprecation_aspect(doc.deprecation)
        if dep_aspect:
            extra_aspects.append(dep_aspect)

    if isinstance(doc, HasStructuredProps):
        sp_aspect = build_structured_properties_aspect(doc.structuredProperties, index, report, context)
        if sp_aspect:
            extra_aspects.append(sp_aspect)

    kwargs["extra_aspects"] = extra_aspects or None
    return kwargs


def common_aspect_mcps(
    entity_urn: str,
    doc,
    index,
    report,
    context: str,
    *,
    skip: FrozenSet[str] = frozenset(),
) -> Iterable[MetadataWorkUnit]:
    """Cross-cutting aspects as standalone follow-up MCPs, for raw-MCP kinds
    (DOMAIN, APPLICATION, DATA_PRODUCT, ASSERTION) and for CONTAINER, which
    gets some of these natively from `gen_containers()` and needs the rest
    (`skip=` names which ones `gen_containers()` already handled) emitted here.
    """
    if "owners" not in skip and isinstance(doc, HasOwners):
        ownership = build_ownership_aspect(normalize_owners(doc.owners))
        if ownership:
            yield mcp_workunit(entity_urn, ownership)

    if "tags" not in skip and isinstance(doc, HasTags):
        for tag_name in doc.tags or []:
            if not index.has_tag(tag_name):
                report.report_dangling_reference(f"{context} references undeclared tag '{tag_name}'")
        tags_aspect = build_global_tags_aspect(doc.tags)
        if tags_aspect:
            yield mcp_workunit(entity_urn, tags_aspect)

    if "terms" not in skip and isinstance(doc, HasTerms):
        for term_id in doc.glossaryTerms or []:
            if not index.has_glossary_term(term_id):
                report.report_dangling_reference(f"{context} references undeclared glossaryTerm '{term_id}'")
        terms_aspect = build_glossary_terms_aspect(doc.glossaryTerms)
        if terms_aspect:
            yield mcp_workunit(entity_urn, terms_aspect)

    if "domain" not in skip and isinstance(doc, HasDomain):
        if doc.domains:
            if not index.has_domain(doc.domains):
                report.report_dangling_reference(f"{context} references undeclared domain '{doc.domains}'")
            yield mcp_workunit(entity_urn, build_domains_aspect(doc.domains))

    if "applications" not in skip and isinstance(doc, HasApplications):
        apps_aspect = build_applications_aspect(doc.applications, index, report, context)
        if apps_aspect:
            yield mcp_workunit(entity_urn, apps_aspect)

    if "links" not in skip and isinstance(doc, HasLinks):
        links_aspect = build_links_aspect(doc.links)
        if links_aspect:
            yield mcp_workunit(entity_urn, links_aspect)

    if "deprecation" not in skip and isinstance(doc, HasDeprecation):
        dep_aspect = build_deprecation_aspect(doc.deprecation)
        if dep_aspect:
            yield mcp_workunit(entity_urn, dep_aspect)

    if "structuredProperties" not in skip and isinstance(doc, HasStructuredProps):
        sp_aspect = build_structured_properties_aspect(doc.structuredProperties, index, report, context)
        if sp_aspect:
            yield mcp_workunit(entity_urn, sp_aspect)

    if "subTypes" not in skip and isinstance(doc, HasSubTypes):
        subtypes_aspect = build_subtypes_aspect(normalize_sub_types(doc.subTypes))
        if subtypes_aspect:
            yield mcp_workunit(entity_urn, subtypes_aspect)
