from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    PropertyValueClass,
    StructuredPropertyDefinitionClass,
    StructuredPropertySettingsClass,
)

from datahub_yaml_source.builders.common import mcp_workunit
from datahub_yaml_source.models import StructuredPropertyDoc
from datahub_yaml_source.urns import structured_property_urn


def build_structured_property(
    doc: StructuredPropertyDoc,
) -> Iterable[MetadataWorkUnit]:
    allowed_values = None
    if doc.allowedValues:
        allowed_values = [
            PropertyValueClass(value=v.value, description=v.description) for v in doc.allowedValues
        ]

    # The friendly YAML shorthand for typeQualifier is a flat list of allowed
    # entity-type/urn-type values; DataHub's raw aspect expects a map keyed by
    # qualifier name. "allowedTypes" is the only qualifier used for `urn`-typed
    # structured properties today.
    type_qualifier = {"allowedTypes": doc.typeQualifier} if doc.typeQualifier else None

    settings = None
    if doc.settings:
        settings = StructuredPropertySettingsClass(
            isHidden=doc.settings.isHidden,
            showInSearchFilters=doc.settings.showInSearchFilters,
            showInAssetSummary=doc.settings.showInAssetSummary,
            showAsAssetBadge=doc.settings.showAsAssetBadge,
            showInColumnsTable=doc.settings.showInColumnsTable,
        )

    aspect = StructuredPropertyDefinitionClass(
        qualifiedName=doc.qualifiedName,
        displayName=doc.displayName,
        valueType=f"urn:li:dataType:datahub.{doc.valueType}",
        cardinality=doc.cardinality,
        allowedValues=allowed_values,
        typeQualifier=type_qualifier,
        entityTypes=[f"urn:li:entityType:datahub.{t}" for t in doc.entityTypes],
        description=doc.description,
    )

    yield mcp_workunit(structured_property_urn(doc.qualifiedName), aspect)

    if settings is not None:
        yield mcp_workunit(structured_property_urn(doc.qualifiedName), settings)
