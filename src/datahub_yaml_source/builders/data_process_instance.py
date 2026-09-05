from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    AuditStampClass,
    DataProcessInstanceInputClass,
    DataProcessInstanceOutputClass,
    DataProcessInstancePropertiesClass,
    DataProcessInstanceRelationshipsClass,
    DataProcessInstanceRunEventClass,
)

from datahub_yaml_source.builders.common import DEFAULT_ACTOR_URN, mcp_workunit, owner_urn
from datahub_yaml_source.models import DataProcessInstanceDoc
from datahub_yaml_source.urns import data_job_urn, data_process_instance_urn, dataset_urn


def build_data_process_instance(
    doc: DataProcessInstanceDoc,
) -> Iterable[MetadataWorkUnit]:
    entity_urn = data_process_instance_urn(doc.id)

    yield mcp_workunit(
        entity_urn,
        DataProcessInstancePropertiesClass(
            name=doc.name,
            created=AuditStampClass(
                time=doc.created.timestampMillis,
                actor=owner_urn(doc.created.actor) if doc.created.actor else DEFAULT_ACTOR_URN,
            ),
            externalUrl=doc.externalUrl,
            type=doc.type,
        ),
    )

    yield mcp_workunit(
        entity_urn,
        DataProcessInstanceRelationshipsClass(
            upstreamInstances=[],
            parentTemplate=data_job_urn(doc.parentTemplate),
        ),
    )

    if doc.inputs:
        yield mcp_workunit(
            entity_urn,
            DataProcessInstanceInputClass(inputs=[dataset_urn(ref) for ref in doc.inputs]),
        )

    if doc.outputs:
        yield mcp_workunit(
            entity_urn,
            DataProcessInstanceOutputClass(outputs=[dataset_urn(ref) for ref in doc.outputs]),
        )

    for run_event in doc.runEvents or []:
        yield mcp_workunit(
            entity_urn,
            DataProcessInstanceRunEventClass(
                timestampMillis=run_event.timestampMillis,
                status=run_event.status,
                attempt=run_event.attempt,
            ),
        )
