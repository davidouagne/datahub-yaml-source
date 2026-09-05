from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import ContainerClass
from datahub.sdk.dataflow import DataFlow
from datahub.sdk.datajob import DataJob

from datahub_yaml_source.builders.common import (
    build_fine_grained_lineage_list,
    common_sdk_kwargs,
    stringify_custom_properties,
)
from datahub_yaml_source.models import DataFlowDoc, DataJobDoc
from datahub_yaml_source.urns import (
    ReferenceIndex,
    container_key,
    data_flow_urn,
    data_job_urn,
    dataset_urn,
)
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def build_data_flow(
    doc: DataFlowDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"DATA_FLOW '{doc.flowId}'"
    common = common_sdk_kwargs(doc, index, report, context)

    # `parent_container=` defaults to a private `Unset` sentinel, not `None`
    # -- passing `None` explicitly still triggers `_set_container(None)`,
    # which emits a (harmless but unwanted-here) empty `browsePathsV2`.
    # Only pass the kwarg at all when there's an actual container.
    if doc.container is not None:
        if not index.has_container(doc.container):
            report.report_dangling_reference(f"{context} references an undeclared container")
        common["parent_container"] = container_key(doc.container)

    flow = DataFlow(
        platform=doc.orchestrator,
        name=doc.flowId,
        env=doc.cluster,
        display_name=doc.name,
        description=doc.description,
        external_url=doc.externalUrl,
        custom_properties={"project": doc.project} if doc.project else None,
        **common,
    )
    yield from flow.as_workunits()


def build_data_job(
    doc: DataJobDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"DATA_JOB '{doc.jobId}'"
    common = common_sdk_kwargs(doc, index, report, context)

    input_urns = [dataset_urn(ref) for ref in (doc.inputDatasets or [])]
    output_urns = [dataset_urn(ref) for ref in (doc.outputDatasets or [])]
    input_job_urns = [data_job_urn(ref) for ref in (doc.inputDataJobs or [])]
    fine_grained = build_fine_grained_lineage_list(doc.fineGrainedLineages)

    if doc.container is not None:
        if not index.has_container(doc.container):
            report.report_dangling_reference(f"{context} references an undeclared container")
        # DataJob has no `parent_container=` constructor kwarg; emit the
        # `container` aspect as a follow-up extra_aspect instead.
        extra_aspects = list(common.get("extra_aspects") or [])
        extra_aspects.append(ContainerClass(container=container_key(doc.container).as_urn()))
        common["extra_aspects"] = extra_aspects

    job = DataJob(
        name=doc.jobId,
        flow_urn=data_flow_urn(doc.dataFlow),
        display_name=doc.name,
        description=doc.description,
        external_url=doc.externalUrl,
        custom_properties=stringify_custom_properties(doc.properties),
        subtype=doc.type,
        inlets=input_urns or None,
        outlets=output_urns or None,
        fine_grained_lineages=fine_grained,
        **common,
    )
    if input_job_urns:
        # SDK V2's DataJob has no public API for job-to-job DAG edges yet (its
        # own source literally says "# TODO: support datajob input/output").
        # Setting the field directly on the aspect it already maintains is
        # the only way to get it into the same DataJobInputOutputClass MCP
        # that set_inlets()/set_outlets() above just populated -- a second,
        # separate MCP for the same aspect would race with this one.
        job._ensure_datajob_inputoutput_props().inputDatajobs = input_job_urns
    yield from job.as_workunits()
