from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    ApplicationLineageClass,
    ApplicationPropertiesClass,
    EdgeClass,
)

from datahub_yaml_source.builders.common import common_aspect_mcps, mcp_workunit
from datahub_yaml_source.models import ApplicationDoc, ApplicationLineageEdgeDoc
from datahub_yaml_source.urns import ReferenceIndex, api_urn, application_urn, dataset_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _application_lineage_edges(
    edges: list[ApplicationLineageEdgeDoc] | None, direction: str, context: str
) -> list[EdgeClass] | None:
    if not edges:
        return None
    result = []
    for i, edge in enumerate(edges):
        if bool(edge.api) == bool(edge.dataset):
            raise ValueError(
                f"{context} applicationLineage.{direction}[{i}] must set "
                f"exactly one of 'api' or 'dataset'"
            )
        destination_urn = api_urn(edge.api) if edge.api else dataset_urn(edge.dataset)
        result.append(EdgeClass(destinationUrn=destination_urn))
    return result


def build_application(
    doc: ApplicationDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"APPLICATION '{doc.id}'"
    entity_urn = application_urn(doc.id)

    # Resolve (and validate) applicationLineage before yielding anything --
    # `get_workunits_internal` streams work units straight to the sink as they're
    # yielded, so raising after an earlier yield would leave a partially-emitted
    # entity instead of cleanly skipping the whole malformed document (see
    # `build_document`'s equivalent native/external check for the same reason).
    input_edges = output_edges = None
    if doc.applicationLineage:
        input_edges = _application_lineage_edges(
            doc.applicationLineage.consumes, "consumes", context
        )
        output_edges = _application_lineage_edges(
            doc.applicationLineage.produces, "produces", context
        )

    yield mcp_workunit(
        entity_urn,
        ApplicationPropertiesClass(name=doc.name, description=doc.description),
    )

    if input_edges or output_edges:
        yield mcp_workunit(
            entity_urn,
            ApplicationLineageClass(inputEdges=input_edges, outputEdges=output_edges),
        )

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)
