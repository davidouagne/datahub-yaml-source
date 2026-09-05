from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import DataProductAssociationClass, DataProductPropertiesClass

from datahub_yaml_source.builders.common import common_aspect_mcps, mcp_workunit
from datahub_yaml_source.models import DataProductDoc
from datahub_yaml_source.urns import ReferenceIndex, data_product_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def build_data_product(
    doc: DataProductDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    entity_urn = data_product_urn(doc.id)
    context = f"DATA_PRODUCT '{doc.id}'"

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

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)
