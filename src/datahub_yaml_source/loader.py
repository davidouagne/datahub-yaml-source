"""File discovery (local directory / S3 prefix / HTTP(S) URL) + multi-document
YAML parsing into a ParsedRepository.

Deliberately does NOT import `datahub.ingestion.source.common.object_store_files`
or `datahub.ingestion.source.aws.aws_common`: both hard-import `boto3` at module
level (DataHub core has no lazy variant), which would force every user of this
source -- including local-only and git-only recipes -- to install the 's3'
extra. Instead, S3 support here only touches boto3 inside the two functions
that need it (`_discover_s3_files` / `_read_s3_bytes`), taking an already
-constructed `AwsConnectionConfig` as a plain argument; the lazy import of that
type itself lives in `yaml_source.py`, where the config is actually built.
HTTP(S) reads are hand-rolled with `requests` (a base acryl-datahub dependency,
so no extra needed) rather than reused from `object_store_files`, for the same
reason.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Union
from urllib.parse import urlparse

import yaml
from pydantic import ValidationError

from datahub.ingestion.source.aws.s3_util import is_s3_uri

from datahub_yaml_source.models import (
    AgentSkillDoc,
    AIAgentDoc,
    ApiDoc,
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
    MetricDoc,
    MLFeatureDoc,
    MLFeatureTableDoc,
    MLModelDoc,
    MLModelGroupDoc,
    MLPrimaryKeyDoc,
    QueryDoc,
    RawAspectDoc,
    RepositoryDoc,
    SemanticModelDoc,
    ServiceDoc,
    StructuredPropertyDoc,
    TagDoc,
    parse_document,
)

logger = logging.getLogger(__name__)

# Callback invoked for every document that fails to parse, and for every file
# that fails to be listed or read: (file_or_uri, message) -> None
OnErrorCallback = Callable[[str, str], None]

# Callback invoked once for every discovered file (local path or remote URI),
# before it's read.
OnFileScannedCallback = Callable[[str], None]

# Callback invoked for every entity document with a field that's either
# misspelled or not valid for its `kind`: (file_path, kind, field_names) -> None.
# Not used for RawAspectDoc, whose extra fields *are* the intended payload.
OnUnknownFieldsCallback = Callable[[str, str, List[str]], None]

_HTTP_URI_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
_GLOB_CHARACTERS = frozenset("*?[]")
_HTTP_TIMEOUT_SECONDS = 30
_HTTP_CHUNK_BYTES = 1024 * 1024


def is_http_uri(uri: str) -> bool:
    return bool(_HTTP_URI_PATTERN.match(uri))


def has_glob_characters(value: str) -> bool:
    return any(c in value for c in _GLOB_CHARACTERS)


class FileSizeExceededError(ValueError):
    """A file exceeded the configured `max_input_file_bytes` cap."""


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
    ml_feature_tables: List[MLFeatureTableDoc] = field(default_factory=list)
    ml_features: List[MLFeatureDoc] = field(default_factory=list)
    ml_primary_keys: List[MLPrimaryKeyDoc] = field(default_factory=list)
    ml_model_groups: List[MLModelGroupDoc] = field(default_factory=list)
    ml_models: List[MLModelDoc] = field(default_factory=list)
    semantic_models: List[SemanticModelDoc] = field(default_factory=list)
    metrics: List[MetricDoc] = field(default_factory=list)
    repositories: List[RepositoryDoc] = field(default_factory=list)
    apis: List[ApiDoc] = field(default_factory=list)
    agent_skills: List[AgentSkillDoc] = field(default_factory=list)
    ai_agents: List[AIAgentDoc] = field(default_factory=list)
    services: List[ServiceDoc] = field(default_factory=list)
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
        elif isinstance(doc, MLFeatureTableDoc):
            self.ml_feature_tables.append(doc)
        elif isinstance(doc, MLFeatureDoc):
            self.ml_features.append(doc)
        elif isinstance(doc, MLPrimaryKeyDoc):
            self.ml_primary_keys.append(doc)
        elif isinstance(doc, MLModelGroupDoc):
            self.ml_model_groups.append(doc)
        elif isinstance(doc, MLModelDoc):
            self.ml_models.append(doc)
        elif isinstance(doc, SemanticModelDoc):
            self.semantic_models.append(doc)
        elif isinstance(doc, MetricDoc):
            self.metrics.append(doc)
        elif isinstance(doc, RepositoryDoc):
            self.repositories.append(doc)
        elif isinstance(doc, ApiDoc):
            self.apis.append(doc)
        elif isinstance(doc, AgentSkillDoc):
            self.agent_skills.append(doc)
        elif isinstance(doc, AIAgentDoc):
            self.ai_agents.append(doc)
        elif isinstance(doc, ServiceDoc):
            self.services.append(doc)
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


def _discover_s3_files(prefix: str, aws_connection: Optional[Any]) -> List[str]:
    """List every '*.yml' / '*.yaml' object under an s3:// prefix.

    Lists by prefix (paginated `list_objects_v2`) rather than using DataHub's
    `expand_object_store_glob()` helper: that helper only matches a fixed
    number of '/'-separated segments, so a '**' pattern can't traverse an
    arbitrarily deep layered directory tree (setup/, raw-layer/, ...) the way
    a prefix listing -- or `Path.rglob` for the local case -- can.
    """
    if aws_connection is None:
        raise ValueError(f"'aws_connection' is required to read S3 path: {prefix}")

    parsed = urlparse(prefix)
    bucket = parsed.netloc
    key_prefix = parsed.path.lstrip("/")

    client = aws_connection.get_s3_client()
    paginator = client.get_paginator("list_objects_v2")

    keys: List[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=key_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith((".yml", ".yaml")):
                keys.append(key)

    return sorted(f"s3://{bucket}/{key}" for key in keys)


def _read_s3_bytes(uri: str, aws_connection: Optional[Any], max_bytes: Optional[int]) -> bytes:
    if aws_connection is None:
        raise ValueError(f"'aws_connection' is required to read S3 path: {uri}")

    parsed = urlparse(uri)
    response = aws_connection.get_s3_client().get_object(
        Bucket=parsed.netloc, Key=parsed.path.lstrip("/")
    )
    body = response["Body"]
    declared_size = response.get("ContentLength")
    if declared_size is not None and max_bytes is not None and declared_size > max_bytes:
        raise FileSizeExceededError(
            f"{uri} is {declared_size} bytes, over the configured "
            f"max_input_file_bytes limit of {max_bytes}"
        )
    if max_bytes is None:
        return body.read()
    # Read at most max_bytes+1 so an oversized object trips the cap without
    # pulling the whole body into memory (a lying/absent ContentLength above).
    data = body.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise FileSizeExceededError(
            f"{uri} exceeds the configured max_input_file_bytes limit of {max_bytes}"
        )
    return data


def _read_http_bytes(uri: str, http_connection: Optional[Any], max_bytes: Optional[int]) -> bytes:
    import requests

    kwargs = http_connection.to_request_kwargs() if http_connection else {}
    with requests.get(uri, timeout=_HTTP_TIMEOUT_SECONDS, stream=True, **kwargs) as resp:
        resp.raise_for_status()
        declared = resp.headers.get("Content-Length")
        if declared is not None and declared.isdigit() and max_bytes is not None:
            if int(declared) > max_bytes:
                raise FileSizeExceededError(
                    f"{uri} is {declared} bytes, over the configured "
                    f"max_input_file_bytes limit of {max_bytes}"
                )
        buffer = bytearray()
        for chunk in resp.iter_content(chunk_size=_HTTP_CHUNK_BYTES):
            buffer.extend(chunk)
            if max_bytes is not None and len(buffer) > max_bytes:
                raise FileSizeExceededError(
                    f"{uri} exceeds the configured max_input_file_bytes limit of {max_bytes}"
                )
        return bytes(buffer)


def discover_yaml_files(root: Union[str, Path], aws_connection: Optional[Any] = None) -> List[str]:
    """Resolve one configured 'path' entry into the file URIs to read from it.

    - A local directory is scanned recursively for '*.yml' / '*.yaml' files
      (unchanged from before remote support existed).
    - An 's3://' entry is treated as a prefix and listed recursively the same
      way (requires `aws_connection`).
    - An 'http(s)://' entry has no notion of a directory listing (there's no
      `list_objects` equivalent for a bare URL), so it is returned as-is -- it
      must be the URL of a single YAML file. Since the format is
      multi-document YAML, one URL can still carry a whole catalog. A glob
      pattern in an http(s) URL is rejected with a clear error rather than
      silently matching nothing.
    """
    root = os.fspath(root)

    if is_http_uri(root):
        if has_glob_characters(root):
            raise ValueError(
                f"Glob patterns are not supported for http(s):// URIs: {root}. "
                "Provide the URL of a single YAML file instead."
            )
        return [root]

    if is_s3_uri(root):
        return _discover_s3_files(root, aws_connection)

    files = list(Path(root).rglob("*.yml")) + list(Path(root).rglob("*.yaml"))
    return sorted({str(p) for p in files})


def load_repository(
    roots: Union[str, Path, List[Union[str, Path]]],
    on_error: OnErrorCallback,
    on_file_scanned: Optional[OnFileScannedCallback] = None,
    on_unknown_fields: Optional[OnUnknownFieldsCallback] = None,
    aws_connection: Optional[Any] = None,
    http_connection: Optional[Any] = None,
    max_input_file_bytes: Optional[int] = None,
) -> ParsedRepository:
    """Resolve every entry in `roots` to file URIs and parse every document in
    every file into a ParsedRepository.

    A file that can't be listed, read, or parsed is reported via `on_error`
    and skipped; it never aborts the rest of the scan. A document that parses
    but carries a field its `kind` doesn't recognize (typo, or a common
    aspect the entity registry doesn't permit on that kind) is reported via
    `on_unknown_fields` and still processed, ignoring only that field.
    """
    repository = ParsedRepository()
    root_list = roots if isinstance(roots, list) else [roots]

    seen_uris: set = set()
    for root in root_list:
        try:
            uris = discover_yaml_files(root, aws_connection=aws_connection)
        except ValueError as e:
            on_error(os.fspath(root), str(e))
            continue

        for uri in uris:
            if uri in seen_uris:
                continue
            seen_uris.add(uri)

            if on_file_scanned is not None:
                on_file_scanned(uri)

            try:
                if is_http_uri(uri):
                    text = _read_http_bytes(uri, http_connection, max_input_file_bytes).decode(
                        "utf-8"
                    )
                elif is_s3_uri(uri):
                    text = _read_s3_bytes(uri, aws_connection, max_input_file_bytes).decode(
                        "utf-8"
                    )
                else:
                    file_path = Path(uri)
                    if max_input_file_bytes is not None:
                        size = file_path.stat().st_size
                        if size > max_input_file_bytes:
                            raise FileSizeExceededError(
                                f"{uri} is {size} bytes, over the configured "
                                f"max_input_file_bytes limit of {max_input_file_bytes}"
                            )
                    text = file_path.read_text(encoding="utf-8")
            except FileSizeExceededError as e:
                on_error(uri, str(e))
                continue
            except Exception as e:
                on_error(uri, f"Failed to read file: {e}")
                continue

            try:
                raw_docs = list(yaml.safe_load_all(text))
            except yaml.YAMLError as e:
                on_error(uri, f"Failed to parse YAML: {e}")
                continue

            for raw_doc in raw_docs:
                if raw_doc is None:
                    # Empty document between two `---` separators.
                    continue
                try:
                    parsed = parse_document(raw_doc)
                except (DocumentParseError, ValidationError) as e:
                    on_error(uri, f"Invalid document: {e}")
                    continue

                if (
                    on_unknown_fields is not None
                    and not isinstance(parsed, RawAspectDoc)
                    and parsed.model_extra
                ):
                    on_unknown_fields(uri, raw_doc.get("kind", "?"), sorted(parsed.model_extra))

                repository.add(parsed)

    return repository
