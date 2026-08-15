from typing import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    IncidentAssigneeClass,
    IncidentInfoClass,
    IncidentNoteClass,
    IncidentNotesClass,
    IncidentSourceClass,
    IncidentStatusClass,
)

from datahub_yaml_source.builders.common import ZERO_AUDIT_STAMP, common_aspect_mcps, mcp_workunit, owner_urn
from datahub_yaml_source.models import IncidentDoc
from datahub_yaml_source.urns import ReferenceIndex, incident_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def build_incident(
    doc: IncidentDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"INCIDENT '{doc.id}'"
    entity_urn = incident_urn(doc.id)

    status = doc.status
    yield mcp_workunit(
        entity_urn,
        IncidentInfoClass(
            type=doc.type,
            customType=doc.customType,
            entities=doc.entities,
            status=IncidentStatusClass(
                state=status.state if status else "ACTIVE",
                lastUpdated=ZERO_AUDIT_STAMP,
                stage=status.stage if status else None,
                message=status.message if status else None,
            ),
            created=ZERO_AUDIT_STAMP,
            title=doc.title,
            description=doc.description,
            priority=doc.priority,
            assignees=(
                [IncidentAssigneeClass(actor=owner_urn(a), assignedAt=ZERO_AUDIT_STAMP) for a in doc.assignees]
                if doc.assignees
                else None
            ),
            source=(
                IncidentSourceClass(type=doc.source.type, sourceUrn=doc.source.sourceUrn)
                if doc.source
                else None
            ),
            startedAt=doc.startedAt,
        ),
    )

    if doc.notes:
        yield mcp_workunit(
            entity_urn,
            IncidentNotesClass(
                notes=[IncidentNoteClass(message=note, created=ZERO_AUDIT_STAMP) for note in doc.notes]
            ),
        )

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)
