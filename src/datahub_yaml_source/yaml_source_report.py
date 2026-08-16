from dataclasses import dataclass, field
from typing import Optional

from datahub.ingestion.source.state.stale_entity_removal_handler import (
    StaleEntityRemovalSourceReport,
)
from datahub.utilities.lossy_collections import LossyList


@dataclass
class YamlSourceReport(StaleEntityRemovalSourceReport):
    files_scanned: int = 0
    git_checkout: Optional[str] = None

    platforms_scanned: int = 0
    tags_scanned: int = 0
    glossary_nodes_scanned: int = 0
    glossary_terms_scanned: int = 0
    structured_properties_scanned: int = 0
    domains_scanned: int = 0
    applications_scanned: int = 0
    containers_scanned: int = 0
    datasets_scanned: int = 0
    charts_scanned: int = 0
    dashboards_scanned: int = 0
    queries_scanned: int = 0
    incidents_scanned: int = 0
    documents_scanned: int = 0
    ml_feature_tables_scanned: int = 0
    ml_features_scanned: int = 0
    ml_primary_keys_scanned: int = 0
    ml_model_groups_scanned: int = 0
    ml_models_scanned: int = 0
    semantic_models_scanned: int = 0
    metrics_scanned: int = 0
    repositories_scanned: int = 0
    apis_scanned: int = 0
    agent_skills_scanned: int = 0
    ai_agents_scanned: int = 0
    services_scanned: int = 0
    data_products_scanned: int = 0
    data_flows_scanned: int = 0
    data_jobs_scanned: int = 0
    data_process_instances_scanned: int = 0
    assertions_scanned: int = 0
    raw_aspects_scanned: int = 0

    documents_failed_to_parse: int = 0
    dangling_references: LossyList[str] = field(default_factory=LossyList)
    unknown_fields: LossyList[str] = field(default_factory=LossyList)

    def report_document_parse_failure(self, path: str, message: str) -> None:
        self.documents_failed_to_parse += 1
        self.warning(
            title="Failed to parse YAML document",
            message="A document in a scanned file could not be parsed and was skipped.",
            context=f"{path}: {message}",
        )

    def report_dangling_reference(self, context: str) -> None:
        self.dangling_references.append(context)
        self.warning(
            title="Reference to an undeclared entity",
            message="A document references a tag/domain/glossary term/container "
            "that was never declared as its own document anywhere in the "
            "scanned files. The association is still emitted using the "
            "computed URN, but double check for a typo or a missing file.",
            context=context,
        )

    def report_unknown_fields(self, context: str) -> None:
        self.unknown_fields.append(context)
        self.warning(
            title="Unrecognized field on a document",
            message="A document has a field that is either misspelled or not "
            "valid for its 'kind' (DataHub's entity registry doesn't permit "
            "that aspect on that entity type). The document was still "
            "processed, ignoring only that field. Set "
            "'fail_on_unresolved_reference: true' to turn this into a hard "
            "error instead.",
            context=context,
        )
