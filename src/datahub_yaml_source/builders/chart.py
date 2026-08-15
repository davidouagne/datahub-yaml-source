from typing import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.sdk.chart import Chart

from datahub_yaml_source.builders.common import common_sdk_kwargs, stringify_custom_properties
from datahub_yaml_source.models import ChartDoc
from datahub_yaml_source.urns import ReferenceIndex, container_key, dataset_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def build_chart(
    doc: ChartDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"CHART '{doc.name}'"
    common = common_sdk_kwargs(doc, index, report, context)

    # `parent_container=` defaults to a private `Unset` sentinel, not `None`
    # -- passing `None` explicitly still triggers `_set_container(None)`,
    # which emits a (harmless but unwanted-here) empty `browsePathsV2`. Only
    # pass the kwarg at all when there's an actual container (same trap as
    # `build_dataset()`/`build_data_flow()`).
    if doc.container is not None:
        if not index.has_container(doc.container):
            report.report_dangling_reference(f"{context} references an undeclared container")
        common["parent_container"] = container_key(doc.container)

    chart = Chart(
        platform=doc.platform,
        name=doc.name,
        platform_instance=doc.instance,
        display_name=doc.displayName,
        description=doc.description,
        external_url=doc.externalUrl,
        chart_url=doc.chartUrl,
        chart_type=doc.chartType,
        custom_properties=stringify_custom_properties(doc.properties),
        input_datasets=[dataset_urn(ref) for ref in (doc.inputDatasets or [])] or None,
        **common,
    )
    yield from chart.as_workunits()
