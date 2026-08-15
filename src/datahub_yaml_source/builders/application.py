from typing import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import ApplicationPropertiesClass

from datahub_yaml_source.builders.common import mcp_workunit
from datahub_yaml_source.models import ApplicationDoc
from datahub_yaml_source.urns import application_urn


def build_application(doc: ApplicationDoc) -> Iterable[MetadataWorkUnit]:
    yield mcp_workunit(
        application_urn(doc.id),
        ApplicationPropertiesClass(name=doc.name, description=doc.description),
    )
