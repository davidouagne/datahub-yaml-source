from typing import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.sdk.dataflow import DataFlow
from datahub.sdk.datajob import DataJob

from datahub_yaml_source.builders.common import (
    build_fine_grained_lineage_list,
    owners_to_sdk_input,
)
from datahub_yaml_source.models import DataFlowDoc, DataJobDoc, normalize_owners
from datahub_yaml_source.urns import ReferenceIndex, data_flow_urn, dataset_urn, domain_urn, tag_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def build_data_flow(doc: DataFlowDoc) -> Iterable[MetadataWorkUnit]:
    owners = normalize_owners(doc.owners)
    domain = domain_urn(doc.domains) if doc.domains else None
    tags = [tag_urn(t) for t in (doc.tags or [])]

    flow = DataFlow(
        platform=doc.orchestrator,
        name=doc.flowId,
        env=doc.cluster,
        display_name=doc.name,
        description=doc.description,
        external_url=doc.externalUrl,
        custom_properties={"project": doc.project} if doc.project else None,
        owners=owners_to_sdk_input(owners) or None,
        tags=tags or None,
        domain=domain,
    )
    yield from flow.as_workunits()


def build_data_job(
    doc: DataJobDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    owners = normalize_owners(doc.owners)

    tags = []
    for tag_name in doc.tags or []:
        if not index.has_tag(tag_name):
            report.report_dangling_reference(
                f"DATA_JOB '{doc.jobId}' references undeclared tag '{tag_name}'"
            )
        tags.append(tag_urn(tag_name))

    input_urns = [dataset_urn(ref) for ref in (doc.inputDatasets or [])]
    output_urns = [dataset_urn(ref) for ref in (doc.outputDatasets or [])]
    fine_grained = build_fine_grained_lineage_list(doc.fineGrainedLineages)

    job = DataJob(
        name=doc.jobId,
        flow_urn=data_flow_urn(doc.dataFlow),
        display_name=doc.name,
        description=doc.description,
        subtype=doc.type,
        owners=owners_to_sdk_input(owners) or None,
        tags=tags or None,
        inlets=input_urns or None,
        outlets=output_urns or None,
        fine_grained_lineages=fine_grained,
    )
    yield from job.as_workunits()
