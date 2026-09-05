from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import DataPlatformInfoClass

from datahub_yaml_source.builders.common import mcp_workunit
from datahub_yaml_source.models import DataPlatformDoc
from datahub_yaml_source.urns import data_platform_urn


def build_data_platform(doc: DataPlatformDoc) -> Iterable[MetadataWorkUnit]:
    yield mcp_workunit(
        data_platform_urn(doc.name),
        DataPlatformInfoClass(
            name=doc.name,
            type=doc.type,
            datasetNameDelimiter=doc.datasetNameDelimiter,
            displayName=doc.displayName,
            logoUrl=doc.logoUrl,
        ),
    )
