import logging
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
from datahub.ingestion.source.aws.s3_util import is_s3_uri
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
from datahub_yaml_source.builders.document import build_document
from datahub_yaml_source.builders.domain import build_domain, topological_sort_domains
from datahub_yaml_source.builders.glossary import build_glossary_node, build_glossary_term
from datahub_yaml_source.builders.incident import build_incident
from datahub_yaml_source.builders.ml import (
    build_ml_feature,
    build_ml_feature_table,
    build_ml_model,
    build_ml_model_group,
    build_ml_primary_key,
)
from datahub_yaml_source.builders.platform import build_data_platform
from datahub_yaml_source.builders.query import build_query
from datahub_yaml_source.builders.raw_aspect import build_raw_aspect
from datahub_yaml_source.builders.semantic import build_metric, build_semantic_model
from datahub_yaml_source.builders.software import (
    build_agent_skill,
    build_ai_agent,
    build_api,
    build_repository,
    build_service,
)
from datahub_yaml_source.builders.structured_property import build_structured_property
from datahub_yaml_source.builders.tag import build_tag
from datahub_yaml_source.loader import (
    ParsedRepository,
    has_glob_characters,
    is_http_uri,
    load_repository,
)
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_config import YamlSourceConfig
from datahub_yaml_source.yaml_source_report import YamlSourceReport

logger = logging.getLogger(__name__)


def _resolve_aws_connection(aws_connection_config: dict[str, Any] | None) -> Any | None:
    """Lazily build an `AwsConnectionConfig` from the config dict, if set.

    `AwsConnectionConfig` (datahub.ingestion.source.aws.aws_common) hard-imports
    boto3 at module level with no lazy variant, so the import itself lives here
    -- inside a function only called when an 's3://' path is actually configured
    -- rather than at module level, keeping boto3 optional for local/git/http-only
    recipes.
    """
    if aws_connection_config is None:
        return None
    try:
        from datahub.ingestion.source.aws.aws_common import AwsConnectionConfig
    except ImportError as e:
        raise ImportError(
            "Reading s3:// paths requires the 's3' extra: pip install datahub-yaml-source[s3]"
        ) from e
    return AwsConnectionConfig.model_validate(aws_connection_config)


@platform_name("YAML Metadata")
@config_class(YamlSourceConfig)
@support_status(SupportStatus.INCUBATING)
@capability(SourceCapability.SCHEMA_METADATA, "Enabled by default via DATASET documents")
@capability(SourceCapability.CONTAINERS, "Enabled by default via CONTAINER documents")
@capability(SourceCapability.LINEAGE_COARSE, "Fully declared in YAML, no SQL parsing involved")
@capability(SourceCapability.LINEAGE_FINE, "Fully declared in YAML via fineGrainedLineages")
@capability(SourceCapability.OWNERSHIP, "Enabled by default via 'owners' fields")
@capability(SourceCapability.TAGS, "Enabled by default via TAG documents and 'tags' references")
@capability(
    SourceCapability.DOMAINS, "Enabled by default via DOMAIN documents and 'domains' references"
)
@capability(
    SourceCapability.GLOSSARY_TERMS,
    "Enabled by default via GLOSSARY_TERM documents and 'glossaryTerms' references",
)
@capability(SourceCapability.DESCRIPTIONS, "Enabled by default via 'description' fields")
@capability(
    SourceCapability.PLATFORM_INSTANCE, "Enabled via 'instance' fields on DATASET/CONTAINER"
)
@capability(
    SourceCapability.DATA_PROFILING,
    "Via 'aspectName: DATASET_PROFILE' raw-aspect passthrough documents",
)
@capability(
    SourceCapability.USAGE_STATS,
    "Via 'aspectName: DATASET_USAGE_STATISTICS' raw-aspect passthrough documents",
)
@capability(
    SourceCapability.OPERATION_CAPTURE,
    "Via 'aspectName: OPERATION' raw-aspect passthrough documents",
)
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

    def _resolve_roots(self, checkout_dir: Path | None = None) -> list[str]:
        """Resolve every 'path' entry to a root `load_repository()` can scan.

        A local-directory entry is checked to exist/be-a-directory here (so a
        typo is reported with an exact, actionable message); a bad entry is
        skipped (reported as a failure) rather than aborting the other entries.
        's3://'/'http(s)://' entries pass through unchanged -- there's nothing
        to check locally, and `load_repository()` reports any listing/read
        problem for them itself, per-URI, via `on_error`.
        """
        configured_paths = (
            self.config.path if isinstance(self.config.path, list) else [self.config.path]
        )

        roots: list[str] = []
        for entry in configured_paths:
            if is_s3_uri(entry) or is_http_uri(entry):
                roots.append(entry)
                continue

            local_path = Path(entry)
            if checkout_dir is not None and not local_path.is_absolute():
                local_path = checkout_dir / local_path

            if not local_path.exists():
                self.report.failure(
                    title="Configured path does not exist",
                    message="An entry in 'path' does not exist on disk. Check for "
                    "typos, and note that under WSL, Windows paths must be given as "
                    "'/mnt/c/...' rather than 'C:\\...'.",
                    context=str(local_path),
                )
                continue

            if not local_path.is_dir():
                self.report.failure(
                    title="Configured path is not a directory",
                    message="An entry in 'path' points at a file, not a directory.",
                    context=str(local_path),
                )
                continue

            roots.append(str(local_path))

        return roots

    def _load_repository(self, checkout_dir: Path | None = None) -> ParsedRepository:
        roots = self._resolve_roots(checkout_dir)
        if not roots:
            return ParsedRepository()

        try:
            aws_connection = _resolve_aws_connection(self.config.aws_connection)
        except ImportError as e:
            self.report.failure(
                title="Cannot read s3:// path(s)",
                message=str(e),
                exc=e,
            )
            aws_connection = None

        def on_error(path: str, message: str) -> None:
            if self.config.fail_on_unresolved_reference:
                raise ValueError(f"{path}: {message}")
            self.report.report_document_parse_failure(path, message)

        def on_file_scanned(path: str) -> None:
            self.report.files_scanned += 1

        def on_unknown_fields(path: str, kind: str, field_names: list) -> None:
            message = f"{path}: kind={kind} unexpected field(s): {sorted(field_names)}"
            if self.config.fail_on_unresolved_reference:
                raise ValueError(message)
            self.report.report_unknown_fields(message)

        repository = load_repository(
            roots,
            on_error=on_error,
            on_file_scanned=on_file_scanned,
            on_unknown_fields=on_unknown_fields,
            aws_connection=aws_connection,
            http_connection=self.config.http_connection,
            max_input_file_bytes=self.config.max_input_file_bytes,
        )

        if self.report.files_scanned == 0:
            self.report.warning(
                title="No YAML files found",
                message="No '*.yml' / '*.yaml' files were found under the configured path.",
                context=str(roots),
            )

        return repository

    def _load_repository_maybe_from_git(self) -> ParsedRepository | None:
        """Clone `git_info` into a temp dir (if configured) and load the repository.

        Unlike a lazy file-by-file scan, `_load_repository` fully reads and
        parses every YAML file into an in-memory `ParsedRepository` before
        returning -- so the checkout only needs to stay on disk for the
        duration of this call, not for the lifetime of the (lazy)
        `get_workunits_internal` generator.
        """
        if self.config.git_info is None:
            return self._load_repository()

        try:
            with tempfile.TemporaryDirectory(prefix="yaml_source_git_") as tmp_dir:
                checkout_dir = self.config.git_info.clone(tmp_path=tmp_dir)
                self.report.git_checkout = str(checkout_dir)
                return self._load_repository(checkout_dir)
        except Exception as e:
            self.report.failure(
                title="Failed to clone git_info repository",
                message="Could not shallow-clone the configured git repository. "
                "Check 'repo', branch/commit, and deploy key configuration. "
                "Requires the 'git' extra: pip install datahub-yaml-source[git].",
                exc=e,
            )
            return None

    def get_workunits_internal(self) -> Iterable[MetadataWorkUnit]:
        repository = self._load_repository_maybe_from_git()
        if repository is None:
            return
        index = ReferenceIndex(repository)

        for platform_doc in repository.platforms:
            self.report.platforms_scanned += 1
            yield from self._safe_build(
                "DATA_PLATFORM", platform_doc.name, build_data_platform, platform_doc
            )

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
            yield from self._safe_build(
                "DOMAIN", domain_doc.id, build_domain, domain_doc, index, self.report
            )

        for application_doc in repository.applications:
            self.report.applications_scanned += 1
            yield from self._safe_build(
                "APPLICATION",
                application_doc.id,
                build_application,
                application_doc,
                index,
                self.report,
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

        for query_doc in repository.queries:
            self.report.queries_scanned += 1
            yield from self._safe_build(
                "QUERY", query_doc.id, build_query, query_doc, index, self.report
            )

        for incident_doc in repository.incidents:
            self.report.incidents_scanned += 1
            yield from self._safe_build(
                "INCIDENT", incident_doc.id, build_incident, incident_doc, index, self.report
            )

        for document_doc in repository.documents:
            self.report.documents_scanned += 1
            yield from self._safe_build(
                "DOCUMENT", document_doc.id, build_document, document_doc, index, self.report
            )

        # MLFEATURE/MLPRIMARY_KEY before MLFEATURE_TABLE (which references them);
        # MLMODEL_GROUP before MLMODEL (which references its group).
        for feature_doc in repository.ml_features:
            self.report.ml_features_scanned += 1
            yield from self._safe_build(
                "MLFEATURE",
                f"{feature_doc.featureNamespace}.{feature_doc.name}",
                build_ml_feature,
                feature_doc,
                index,
                self.report,
            )

        for primary_key_doc in repository.ml_primary_keys:
            self.report.ml_primary_keys_scanned += 1
            yield from self._safe_build(
                "MLPRIMARY_KEY",
                f"{primary_key_doc.featureNamespace}.{primary_key_doc.name}",
                build_ml_primary_key,
                primary_key_doc,
                index,
                self.report,
            )

        for feature_table_doc in repository.ml_feature_tables:
            self.report.ml_feature_tables_scanned += 1
            yield from self._safe_build(
                "MLFEATURE_TABLE",
                feature_table_doc.name,
                build_ml_feature_table,
                feature_table_doc,
                index,
                self.report,
            )

        for model_group_doc in repository.ml_model_groups:
            self.report.ml_model_groups_scanned += 1
            yield from self._safe_build(
                "MLMODEL_GROUP",
                model_group_doc.name,
                build_ml_model_group,
                model_group_doc,
                index,
                self.report,
            )

        for model_doc in repository.ml_models:
            self.report.ml_models_scanned += 1
            yield from self._safe_build(
                "MLMODEL", model_doc.name, build_ml_model, model_doc, index, self.report
            )

        # SEMANTIC_MODEL before METRIC: Metric's SDK constructor requires semantic_model=.
        for semantic_model_doc in repository.semantic_models:
            self.report.semantic_models_scanned += 1
            yield from self._safe_build(
                "SEMANTIC_MODEL",
                semantic_model_doc.id,
                build_semantic_model,
                semantic_model_doc,
                index,
                self.report,
            )

        for metric_doc in repository.metrics:
            self.report.metrics_scanned += 1
            yield from self._safe_build(
                "METRIC", metric_doc.id, build_metric, metric_doc, index, self.report
            )

        # Parents before children: REPOSITORY/API/AGENT_SKILL before AI_AGENT/SERVICE,
        # which may reference them.
        for repository_doc in repository.repositories:
            self.report.repositories_scanned += 1
            yield from self._safe_build(
                "REPOSITORY",
                repository_doc.id,
                build_repository,
                repository_doc,
                index,
                self.report,
            )

        for api_doc in repository.apis:
            self.report.apis_scanned += 1
            yield from self._safe_build("API", api_doc.id, build_api, api_doc, index, self.report)

        for agent_skill_doc in repository.agent_skills:
            self.report.agent_skills_scanned += 1
            yield from self._safe_build(
                "AGENT_SKILL",
                agent_skill_doc.id,
                build_agent_skill,
                agent_skill_doc,
                index,
                self.report,
            )

        for ai_agent_doc in repository.ai_agents:
            self.report.ai_agents_scanned += 1
            yield from self._safe_build(
                "AI_AGENT", ai_agent_doc.id, build_ai_agent, ai_agent_doc, index, self.report
            )

        for service_doc in repository.services:
            self.report.services_scanned += 1
            yield from self._safe_build(
                "SERVICE", service_doc.id, build_service, service_doc, index, self.report
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
            yield from self._safe_build("RAW_ASPECT", raw_doc.aspectName, build_raw_aspect, raw_doc)

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

            if config.git_info is not None:
                try:
                    with tempfile.TemporaryDirectory(prefix="yaml_source_git_test_") as tmp_dir:
                        config.git_info.clone(tmp_path=tmp_dir)
                    test_report.basic_connectivity = CapabilityReport(capable=True)
                except Exception as e:
                    test_report.basic_connectivity = CapabilityReport(
                        capable=False, failure_reason=f"Could not clone git_info repository: {e}"
                    )
                return test_report

            problems = []
            entries = config.path if isinstance(config.path, list) else [config.path]
            for entry in entries:
                if is_s3_uri(entry):
                    problems.extend(YamlSource._check_s3_connectivity(entry, config))
                elif is_http_uri(entry):
                    problems.extend(YamlSource._check_http_connectivity(entry, config))
                else:
                    root = Path(entry)
                    if not root.exists():
                        problems.append(f"Path does not exist: {root}")
                    elif not root.is_dir():
                        problems.append(f"Path is not a directory: {root}")

            if problems:
                test_report.basic_connectivity = CapabilityReport(
                    capable=False, failure_reason="; ".join(problems)
                )
            else:
                test_report.basic_connectivity = CapabilityReport(capable=True)
        except Exception as e:
            test_report.basic_connectivity = CapabilityReport(capable=False, failure_reason=str(e))

        return test_report

    @staticmethod
    def _check_s3_connectivity(uri: str, config: "YamlSourceConfig") -> list[str]:
        try:
            aws_connection = _resolve_aws_connection(config.aws_connection)
        except ImportError as e:
            return [str(e)]
        if aws_connection is None:
            return [f"'aws_connection' is required for s3:// path: {uri}"]

        parsed = urlparse(uri)
        try:
            aws_connection.get_s3_client().list_objects_v2(
                Bucket=parsed.netloc, Prefix=parsed.path.lstrip("/"), MaxKeys=1
            )
        except Exception as e:
            return [f"Could not list s3:// path {uri}: {e}"]
        return []

    @staticmethod
    def _check_http_connectivity(uri: str, config: "YamlSourceConfig") -> list[str]:
        if has_glob_characters(uri):
            return [f"Glob patterns are not supported for http(s):// URIs: {uri}"]

        import requests

        kwargs = config.http_connection.to_request_kwargs() if config.http_connection else {}
        try:
            resp = requests.head(uri, timeout=10, allow_redirects=True, **kwargs)
            resp.raise_for_status()
        except Exception as e:
            return [f"Could not reach http(s):// path {uri}: {e}"]
        return []
