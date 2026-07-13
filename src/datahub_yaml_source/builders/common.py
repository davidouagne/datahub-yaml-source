"""Shared helpers used across builders/*.py."""

from typing import List, Optional, Tuple

from datahub.emitter.mce_builder import make_schema_field_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    BooleanTypeClass,
    BytesTypeClass,
    DateTypeClass,
    DomainsClass,
    FineGrainedLineageClass,
    FineGrainedLineageDownstreamTypeClass,
    FineGrainedLineageUpstreamTypeClass,
    GlobalTagsClass,
    GlossaryTermAssociationClass,
    GlossaryTermsClass,
    NullTypeClass,
    NumberTypeClass,
    OwnerClass,
    OwnershipClass,
    RecordTypeClass,
    SchemaFieldDataTypeClass,
    StringTypeClass,
    TagAssociationClass,
    TimeTypeClass,
)
from datahub.metadata.schema_classes import AuditStampClass

from datahub_yaml_source.models import FineGrainedLineageDoc, OwnerEntry
from datahub_yaml_source.urns import dataset_urn, domain_urn, glossary_term_urn, owner_urn, tag_urn

DEFAULT_ACTOR_URN = "urn:li:corpuser:datahub"

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
