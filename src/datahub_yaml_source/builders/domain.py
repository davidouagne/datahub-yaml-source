from typing import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import DomainPropertiesClass

from datahub_yaml_source.builders.common import mcp_workunit
from datahub_yaml_source.models import DomainDoc
from datahub_yaml_source.urns import domain_urn


def build_domain(doc: DomainDoc) -> Iterable[MetadataWorkUnit]:
    yield mcp_workunit(
        domain_urn(doc.id),
        DomainPropertiesClass(name=doc.name, description=doc.description),
    )
