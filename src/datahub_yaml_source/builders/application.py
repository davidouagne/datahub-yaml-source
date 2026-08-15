from typing import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import ApplicationPropertiesClass

from datahub_yaml_source.builders.common import common_aspect_mcps, mcp_workunit
from datahub_yaml_source.models import ApplicationDoc
from datahub_yaml_source.urns import ReferenceIndex, application_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def build_application(
    doc: ApplicationDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    entity_urn = application_urn(doc.id)
    yield mcp_workunit(
        entity_urn,
        ApplicationPropertiesClass(name=doc.name, description=doc.description),
    )
    yield from common_aspect_mcps(entity_urn, doc, index, report, f"APPLICATION '{doc.id}'")
