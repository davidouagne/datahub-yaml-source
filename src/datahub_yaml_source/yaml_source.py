import logging
from pathlib import Path
from typing import Iterable

from datahub.ingestion.api.common import PipelineContext
from datahub.ingestion.api.decorators import (
    SupportStatus,
    capability,
    config_class,
    platform_name,
    support_status,
)
from datahub.ingestion.api.source import (
    CapabilityReport,
    SourceCapability,
    TestableSource,
    TestConnectionReport,
)
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.ingestion.source.state.stateful_ingestion_base import (
    StatefulIngestionSourceBase,
)

from datahub_yaml_source.builders.application import build_application
from datahub_yaml_source.builders.assertion import build_assertion
from datahub_yaml_source.builders.chart import build_chart
from datahub_yaml_source.builders.container import build_container, topological_sort_containers
from datahub_yaml_source.builders.dashboard import build_dashboard
from datahub_yaml_source.builders.data_flow_job import build_data_flow, build_data_job
from datahub_yaml_source.builders.data_process_instance import build_data_process_instance
from datahub_yaml_source.builders.data_product import build_data_product
from datahub_yaml_source.builders.dataset import build_dataset
from datahub_yaml_source.builders.domain import build_domain, topological_sort_domains
from datahub_yaml_source.builders.glossary import build_glossary_node, build_glossary_term
from datahub_yaml_source.builders.platform import build_data_platform
from datahub_yaml_source.builders.raw_aspect import build_raw_aspect
from datahub_yaml_source.builders.structured_property import build_structured_property
from datahub_yaml_source.builders.tag import build_tag
from datahub_yaml_source.loader import ParsedRepository, load_repository
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_config import YamlSourceConfig
from datahub_yaml_source.yaml_source_report import YamlSourceReport

logger = logging.getLogger(__name__)


@platform_name("YAML Metadata")
@config_class(YamlSourceConfig)
@support_status(SupportStatus.INCUBATING)
@capability(SourceCapability.SCHEMA_METADATA, "Enabled by default via DATASET documents")
@capability(SourceCapability.CONTAINERS, "Enabled by default via CONTAINER documents")
@capability(SourceCapability.LINEAGE_COARSE, "Fully declared in YAML, no SQL parsing involved")
@capability(SourceCapability.LINEAGE_FINE, "Fully declared in YAML via fineGrainedLineages")
@capability(SourceCapability.OWNERSHIP, "Enabled by default via 'owners' fields")
@capability(SourceCapability.TAGS, "Enabled by default via TAG documents and 'tags' references")
@capability(SourceCapability.DOMAINS, "Enabled by default via DOMAIN documents and 'domains' references")
@capability(SourceCapability.GLOSSARY_TERMS, "Enabled by default via GLOSSARY_TERM documents and 'glossaryTerms' references")
@capability(SourceCapability.DESCRIPTIONS, "Enabled by default via 'description' fields")
@capability(SourceCapability.PLATFORM_INSTANCE, "Enabled via 'instance' fields on DATASET/CONTAINER")
@capability(SourceCapability.DATA_PROFILING, "Via 'aspectName: DATASET_PROFILE' raw-aspect passthrough documents")
@capability(SourceCapability.USAGE_STATS, "Via 'aspectName: DATASET_USAGE_STATISTICS' raw-aspect passthrough documents")
@capability(SourceCapability.OPERATION_CAPTURE, "Via 'aspectName: OPERATION' raw-aspect passthrough documents")
@capability(SourceCapability.DELETION_DETECTION, "Enabled via stateful ingestion")
@capability(SourceCapability.TEST_CONNECTION, "Enabled by default")
class YamlSource(StatefulIngestionSourceBase, TestableSource):
    """DataHub source that reads a directory tree of declarative YAML metadata
    files ("metadata as code") and emits the DataHub entities they describe:
    data platforms, tags, glossary terms, structured properties, domains,
    applications, containers, datasets, data products, pipelines, pipeline
    run history, and data quality assertions.

    This source has no connection of its own -- every platform, environment,
    and instance is declared per-entity inside the YAML files themselves.
    """

    config: YamlSourceConfig
    report: YamlSourceReport

    def __init__(self, config: YamlSourceConfig, ctx: PipelineContext):
        super().__init__(config, ctx)
        self.config = config
        self.report = YamlSourceReport()

    @classmethod
    def create(cls, config_dict: dict, ctx: PipelineContext) -> "YamlSource":
        config = YamlSourceConfig.model_validate(config_dict)
        return cls(config, ctx)

    def get_report(self) -> YamlSourceReport:
        return self.report

    def _load_repository(self) -> ParsedRepository:
        root = Path(self.config.path)

        if not root.exists():
            self.report.failure(
                title="Configured path does not exist",
                message="The 'path' in your recipe does not exist on disk. Check for "
                "typos, and note that under WSL, Windows paths must be given as "
                "'/mnt/c/...' rather than 'C:\\...'.",
                context=str(root),
            )
            return ParsedRepository()

        if not root.is_dir():
            self.report.failure(
                title="Configured path is not a directory",
                message="The 'path' in your recipe points at a file, not a directory.",
                context=str(root),
            )
            return ParsedRepository()

        def on_error(path: str, message: str) -> None:
            if self.config.fail_on_unresolved_reference:
                raise ValueError(f"{path}: {message}")
            self.report.report_document_parse_failure(path, message)

        def on_file_scanned(path: Path) -> None:
            self.report.files_scanned += 1

        def on_unknown_fields(path: str, kind: str, field_names: list) -> None:
            message = f"{path}: kind={kind} unexpected field(s): {sorted(field_names)}"
            if self.config.fail_on_unresolved_reference:
                raise ValueError(message)
            self.report.report_unknown_fields(message)

        repository = load_repository(
            root, on_error=on_error, on_file_scanned=on_file_scanned, on_unknown_fields=on_unknown_fields
        )

        if self.report.files_scanned == 0:
            self.report.warning(
                title="No YAML files found",
                message="No '*.yml' / '*.yaml' files were found under the configured "
                "path. Check that 'path' points at the right directory.",
                context=str(root),
            )

        return repository

    def get_workunits_internal(self) -> Iterable[MetadataWorkUnit]:
        repository = self._load_repository()
        index = ReferenceIndex(repository)

        for platform_doc in repository.platforms:
            self.report.platforms_scanned += 1
            yield from self._safe_build("DATA_PLATFORM", platform_doc.name, build_data_platform, platform_doc)

        for tag_doc in repository.tags:
            self.report.tags_scanned += 1
            yield from self._safe_build("TAG", tag_doc.name, build_tag, tag_doc, index, self.report)

        for node_doc in repository.glossary_nodes:
            self.report.glossary_nodes_scanned += 1
            yield from self._safe_build(
                "GLOSSARY_NODE", node_doc.id, build_glossary_node, node_doc, index, self.report
            )

        for term_doc in repository.glossary_terms:
            self.report.glossary_terms_scanned += 1
            yield from self._safe_build(
                "GLOSSARY_TERM", term_doc.id, build_glossary_term, term_doc, index, self.report
            )

        for prop_doc in repository.structured_properties:
            self.report.structured_properties_scanned += 1
            yield from self._safe_build(
                "STRUCTURED_PROPERTY", prop_doc.qualifiedName, build_structured_property, prop_doc
            )

        for domain_doc in topological_sort_domains(repository.domains):
            self.report.domains_scanned += 1
            yield from self._safe_build("DOMAIN", domain_doc.id, build_domain, domain_doc, index, self.report)

        for application_doc in repository.applications:
            self.report.applications_scanned += 1
            yield from self._safe_build(
                "APPLICATION", application_doc.id, build_application, application_doc, index, self.report
            )

        for container_doc in topological_sort_containers(repository.containers):
            self.report.containers_scanned += 1
            yield from self._safe_build(
                "CONTAINER", container_doc.name, build_container, container_doc, index, self.report
            )

        for dataset_doc in repository.datasets:
            self.report.datasets_scanned += 1
            yield from self._safe_build(
                "DATASET", dataset_doc.name, build_dataset, dataset_doc, index, self.report
            )

        for chart_doc in repository.charts:
            self.report.charts_scanned += 1
            yield from self._safe_build(
                "CHART", chart_doc.name, build_chart, chart_doc, index, self.report
            )

        for dashboard_doc in repository.dashboards:
            self.report.dashboards_scanned += 1
            yield from self._safe_build(
                "DASHBOARD", dashboard_doc.name, build_dashboard, dashboard_doc, index, self.report
            )

        for product_doc in repository.data_products:
            self.report.data_products_scanned += 1
            yield from self._safe_build(
                "DATA_PRODUCT", product_doc.id, build_data_product, product_doc, index, self.report
            )

        for flow_doc in repository.data_flows:
            self.report.data_flows_scanned += 1
            yield from self._safe_build(
                "DATA_FLOW", flow_doc.flowId, build_data_flow, flow_doc, index, self.report
            )

        for job_doc in repository.data_jobs:
            self.report.data_jobs_scanned += 1
            yield from self._safe_build(
                "DATA_JOB", job_doc.jobId, build_data_job, job_doc, index, self.report
            )

        for instance_doc in repository.data_process_instances:
            self.report.data_process_instances_scanned += 1
            yield from self._safe_build(
                "DATA_PROCESS_INSTANCE", instance_doc.id, build_data_process_instance, instance_doc
            )

        for assertion_doc in repository.assertions:
            self.report.assertions_scanned += 1
            yield from self._safe_build(
                "ASSERTION", assertion_doc.id, build_assertion, assertion_doc, index, self.report
            )

        for raw_doc in repository.raw_aspects:
            self.report.raw_aspects_scanned += 1
            yield from self._safe_build(
                "RAW_ASPECT", raw_doc.aspectName, build_raw_aspect, raw_doc
            )

    def _safe_build(self, kind: str, identifier: str, builder, *args) -> Iterable[MetadataWorkUnit]:
        """Run a builder, converting any failure into a reported warning instead
        of aborting the whole ingestion (one bad document shouldn't take down
        everything else)."""
        try:
            yield from builder(*args)
        except Exception as e:
            self.report.warning(
                title="Failed to build entity",
                message="A document could not be translated into DataHub metadata and was skipped.",
                context=f"{kind} '{identifier}': {e}",
                exc=e,
            )

    @staticmethod
    def test_connection(config_dict: dict) -> TestConnectionReport:
        test_report = TestConnectionReport()
        try:
            config = YamlSourceConfig.model_validate(config_dict)
            root = Path(config.path)
            if not root.exists():
                test_report.basic_connectivity = CapabilityReport(
                    capable=False, failure_reason=f"Path does not exist: {root}"
                )
            elif not root.is_dir():
                test_report.basic_connectivity = CapabilityReport(
                    capable=False, failure_reason=f"Path is not a directory: {root}"
                )
            else:
                test_report.basic_connectivity = CapabilityReport(capable=True)
        except Exception as e:
            test_report.basic_connectivity = CapabilityReport(capable=False, failure_reason=str(e))

        return test_report
