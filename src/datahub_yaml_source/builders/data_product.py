from typing import Any, Iterable, List, Union

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    DataProductAssociationClass,
    DataProductPropertiesClass,
    StructuredPropertiesClass,
    StructuredPropertyValueAssignmentClass,
)

from datahub_yaml_source.builders.common import (
    build_domains_aspect,
    build_glossary_terms_aspect,
    build_global_tags_aspect,
    build_ownership_aspect,
    mcp_workunit,
)
from datahub_yaml_source.models import DataProductDoc, normalize_owners
from datahub_yaml_source.urns import ReferenceIndex, data_product_urn, structured_property_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _normalize_structured_property_values(value: Any) -> List[Union[str, float]]:
    values = value if isinstance(value, list) else [value]
    return [v if isinstance(v, (int, float)) else str(v) for v in values]


def build_data_product(
    doc: DataProductDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    entity_urn = data_product_urn(doc.id)

    yield mcp_workunit(
        entity_urn,
        DataProductPropertiesClass(
            name=doc.name,
            description=doc.description,
            assets=[
                DataProductAssociationClass(destinationUrn=asset_urn)
                for asset_urn in (doc.assets or [])
            ]
            or None,
        ),
    )

    if doc.domains:
        if not index.has_domain(doc.domains):
            report.report_dangling_reference(
                f"DATA_PRODUCT '{doc.id}' references undeclared domain '{doc.domains}'"
            )
        yield mcp_workunit(entity_urn, build_domains_aspect(doc.domains))

    for tag_name in doc.tags or []:
        if not index.has_tag(tag_name):
            report.report_dangling_reference(
                f"DATA_PRODUCT '{doc.id}' references undeclared tag '{tag_name}'"
            )
    tags_aspect = build_global_tags_aspect(doc.tags)
    if tags_aspect:
        yield mcp_workunit(entity_urn, tags_aspect)

    for term_id in doc.glossaryTerms or []:
        if not index.has_glossary_term(term_id):
            report.report_dangling_reference(
                f"DATA_PRODUCT '{doc.id}' references undeclared glossaryTerm '{term_id}'"
            )
    terms_aspect = build_glossary_terms_aspect(doc.glossaryTerms)
    if terms_aspect:
        yield mcp_workunit(entity_urn, terms_aspect)

    ownership_aspect = build_ownership_aspect(normalize_owners(doc.owners))
    if ownership_aspect:
        yield mcp_workunit(entity_urn, ownership_aspect)

    if doc.structuredProperties:
        for qualified_name in doc.structuredProperties:
            if not index.has_structured_property(qualified_name):
                report.report_dangling_reference(
                    f"DATA_PRODUCT '{doc.id}' references undeclared structuredProperty "
                    f"'{qualified_name}'"
                )
        yield mcp_workunit(
            entity_urn,
            StructuredPropertiesClass(
                properties=[
                    StructuredPropertyValueAssignmentClass(
                        propertyUrn=structured_property_urn(qualified_name),
                        values=_normalize_structured_property_values(value),
                    )
                    for qualified_name, value in doc.structuredProperties.items()
                ]
            ),
        )
