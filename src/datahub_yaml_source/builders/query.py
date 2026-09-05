from collections.abc import Iterable

from datahub.emitter.mce_builder import make_schema_field_urn
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    QueryPropertiesClass,
    QueryStatementClass,
    QuerySubjectClass,
    QuerySubjectsClass,
)

from datahub_yaml_source.builders.common import ZERO_AUDIT_STAMP, common_aspect_mcps, mcp_workunit
from datahub_yaml_source.models import QueryDoc
from datahub_yaml_source.urns import ReferenceIndex, dataset_urn, query_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def build_query(
    doc: QueryDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"QUERY '{doc.id}'"
    entity_urn = query_urn(doc.id)

    yield mcp_workunit(
        entity_urn,
        QueryPropertiesClass(
            statement=QueryStatementClass(value=doc.statement, language=doc.language),
            source=doc.source,
            created=ZERO_AUDIT_STAMP,
            lastModified=ZERO_AUDIT_STAMP,
            name=doc.name,
            description=doc.description,
        ),
    )

    if doc.subjects:
        subjects = [
            QuerySubjectClass(
                entity=(
                    make_schema_field_urn(dataset_urn(ref), ref.fieldPath)
                    if ref.fieldPath
                    else dataset_urn(ref)
                )
            )
            for ref in doc.subjects
        ]
        yield mcp_workunit(entity_urn, QuerySubjectsClass(subjects=subjects))

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)
