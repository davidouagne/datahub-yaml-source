"""Directory walk + multi-document YAML parsing into a ParsedRepository."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import yaml
from pydantic import ValidationError

from datahub_yaml_source.models import (
    ApplicationDoc,
    AssertionDoc,
    ChartDoc,
    ContainerDoc,
    DashboardDoc,
    DataFlowDoc,
    DataJobDoc,
    DataPlatformDoc,
    DataProcessInstanceDoc,
    DataProductDoc,
    DatasetDoc,
    DocumentDoc,
    DocumentParseError,
    DomainDoc,
    GlossaryNodeDoc,
    GlossaryTermDoc,
    IncidentDoc,
    QueryDoc,
    RawAspectDoc,
    StructuredPropertyDoc,
    TagDoc,
    parse_document,
)

logger = logging.getLogger(__name__)

# Callback invoked for every document that fails to parse: (file_path, message) -> None
OnErrorCallback = Callable[[str, str], None]

# Callback invoked once for every discovered YAML file, before it's read.
OnFileScannedCallback = Callable[[Path], None]

# Callback invoked for every entity document with a field that's either
# misspelled or not valid for its `kind`: (file_path, kind, field_names) -> None.
# Not used for RawAspectDoc, whose extra fields *are* the intended payload.
OnUnknownFieldsCallback = Callable[[str, str, List[str]], None]


@dataclass
class ParsedRepository:
    platforms: List[DataPlatformDoc] = field(default_factory=list)
    tags: List[TagDoc] = field(default_factory=list)
    glossary_nodes: List[GlossaryNodeDoc] = field(default_factory=list)
    glossary_terms: List[GlossaryTermDoc] = field(default_factory=list)
    structured_properties: List[StructuredPropertyDoc] = field(default_factory=list)
    domains: List[DomainDoc] = field(default_factory=list)
    applications: List[ApplicationDoc] = field(default_factory=list)
    containers: List[ContainerDoc] = field(default_factory=list)
    datasets: List[DatasetDoc] = field(default_factory=list)
    charts: List[ChartDoc] = field(default_factory=list)
    dashboards: List[DashboardDoc] = field(default_factory=list)
    queries: List[QueryDoc] = field(default_factory=list)
    incidents: List[IncidentDoc] = field(default_factory=list)
    documents: List[DocumentDoc] = field(default_factory=list)
    data_products: List[DataProductDoc] = field(default_factory=list)
    data_flows: List[DataFlowDoc] = field(default_factory=list)
    data_jobs: List[DataJobDoc] = field(default_factory=list)
    data_process_instances: List[DataProcessInstanceDoc] = field(default_factory=list)
    assertions: List[AssertionDoc] = field(default_factory=list)
    raw_aspects: List[RawAspectDoc] = field(default_factory=list)

    def add(self, doc: object) -> None:
        if isinstance(doc, DataPlatformDoc):
            self.platforms.append(doc)
        elif isinstance(doc, TagDoc):
            self.tags.append(doc)
        elif isinstance(doc, GlossaryNodeDoc):
            self.glossary_nodes.append(doc)
        elif isinstance(doc, GlossaryTermDoc):
            self.glossary_terms.append(doc)
        elif isinstance(doc, StructuredPropertyDoc):
            self.structured_properties.append(doc)
        elif isinstance(doc, DomainDoc):
            self.domains.append(doc)
        elif isinstance(doc, ApplicationDoc):
            self.applications.append(doc)
        elif isinstance(doc, ContainerDoc):
            self.containers.append(doc)
        elif isinstance(doc, DatasetDoc):
            self.datasets.append(doc)
        elif isinstance(doc, ChartDoc):
            self.charts.append(doc)
        elif isinstance(doc, DashboardDoc):
            self.dashboards.append(doc)
        elif isinstance(doc, QueryDoc):
            self.queries.append(doc)
        elif isinstance(doc, IncidentDoc):
            self.incidents.append(doc)
        elif isinstance(doc, DocumentDoc):
            self.documents.append(doc)
        elif isinstance(doc, DataProductDoc):
            self.data_products.append(doc)
        elif isinstance(doc, DataFlowDoc):
            self.data_flows.append(doc)
        elif isinstance(doc, DataJobDoc):
            self.data_jobs.append(doc)
        elif isinstance(doc, DataProcessInstanceDoc):
            self.data_process_instances.append(doc)
        elif isinstance(doc, AssertionDoc):
            self.assertions.append(doc)
        elif isinstance(doc, RawAspectDoc):
            self.raw_aspects.append(doc)
        else:  # pragma: no cover - guarded by parse_document's return type
            raise TypeError(f"Unrecognized parsed document type: {type(doc)}")


def discover_yaml_files(root: Path) -> List[Path]:
    """Recursively find all *.yml / *.yaml files under `root`, sorted for determinism."""
    files = list(root.rglob("*.yml")) + list(root.rglob("*.yaml"))
    return sorted(set(files))


def load_repository(
    root: Path,
    on_error: OnErrorCallback,
    on_file_scanned: Optional[OnFileScannedCallback] = None,
    on_unknown_fields: Optional[OnUnknownFieldsCallback] = None,
) -> ParsedRepository:
    """Walk `root` for YAML files and parse every document into a ParsedRepository.

    A document that fails to parse is reported via `on_error` and skipped; it
    never aborts parsing of the rest of the file or the rest of the tree. A
    document that parses but carries a field its `kind` doesn't recognize
    (typo, or a common aspect the entity registry doesn't permit on that
    kind) is reported via `on_unknown_fields` and still processed, ignoring
    only that field.
    """
    repository = ParsedRepository()

    for path in discover_yaml_files(root):
        if on_file_scanned is not None:
            on_file_scanned(path)

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            on_error(str(path), f"Failed to read file: {e}")
            continue

        try:
            raw_docs = list(yaml.safe_load_all(text))
        except yaml.YAMLError as e:
            on_error(str(path), f"Failed to parse YAML: {e}")
            continue

        for raw_doc in raw_docs:
            if raw_doc is None:
                # Empty document between two `---` separators.
                continue
            try:
                parsed = parse_document(raw_doc)
            except (DocumentParseError, ValidationError) as e:
                on_error(str(path), f"Invalid document: {e}")
                continue

            if (
                on_unknown_fields is not None
                and not isinstance(parsed, RawAspectDoc)
                and parsed.model_extra
            ):
                on_unknown_fields(str(path), raw_doc.get("kind", "?"), sorted(parsed.model_extra))

            repository.add(parsed)

    return repository
