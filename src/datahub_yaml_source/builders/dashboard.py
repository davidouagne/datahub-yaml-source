from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.sdk.dashboard import Dashboard

from datahub_yaml_source.builders.common import common_sdk_kwargs, stringify_custom_properties
from datahub_yaml_source.models import DashboardDoc
from datahub_yaml_source.urns import (
    ReferenceIndex,
    chart_urn,
    container_key,
    dashboard_urn,
    dataset_urn,
)
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def build_dashboard(
    doc: DashboardDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"DASHBOARD '{doc.name}'"
    common = common_sdk_kwargs(doc, index, report, context)

    # Same `Unset` sentinel trap as `build_dataset()`/`build_chart()`: only
    # pass `parent_container=` when there's an actual container.
    if doc.container is not None:
        if not index.has_container(doc.container):
            report.report_dangling_reference(f"{context} references an undeclared container")
        common["parent_container"] = container_key(doc.container)

    dashboard = Dashboard(
        platform=doc.platform,
        name=doc.name,
        platform_instance=doc.instance,
        display_name=doc.displayName,
        description=doc.description,
        external_url=doc.externalUrl,
        dashboard_url=doc.dashboardUrl,
        custom_properties=stringify_custom_properties(doc.properties),
        input_datasets=[dataset_urn(ref) for ref in (doc.inputDatasets or [])] or None,
        charts=[chart_urn(ref) for ref in (doc.charts or [])] or None,
        dashboards=[dashboard_urn(ref) for ref in (doc.dashboards or [])] or None,
        **common,
    )
    yield from dashboard.as_workunits()
