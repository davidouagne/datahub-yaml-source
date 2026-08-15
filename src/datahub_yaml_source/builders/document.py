from datetime import datetime, timezone
from typing import FrozenSet, Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.sdk.document import Document

from datahub_yaml_source.builders.common import common_sdk_kwargs, stringify_custom_properties
from datahub_yaml_source.models import DocumentDoc
from datahub_yaml_source.urns import ReferenceIndex, document_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport

# `Document.create_document()`/`create_external_document()` have no `links=`
# kwarg (unlike Dataset/Chart/Dashboard/DataFlow/DataJob) -- an
# institutionalMemory aspect a document has still gets emitted, just via
# `extra_aspects` instead of a constructor kwarg (see `common_sdk_kwargs()`).
_DOCUMENT_NATIVE_KWARGS: FrozenSet[str] = frozenset({"owners", "tags", "terms", "domain", "subtype"})

# Without these, `create_document()`/`create_external_document()` stamp
# `datetime.now()` on `created`/`lastModified` -- unlike every other SDK V2
# entity in this connector, which default to a deterministic `time=0`. Pin
# to the epoch for a stable golden file.
_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


def build_document(
    doc: DocumentDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"DOCUMENT '{doc.id}'"
    common = common_sdk_kwargs(doc, index, report, context, native=_DOCUMENT_NATIVE_KWARGS)

    related_documents = [document_urn(d) for d in (doc.relatedDocuments or [])] or None
    parent_document = document_urn(doc.parentDocument) if doc.parentDocument else None
    custom_properties = stringify_custom_properties(doc.properties)

    if doc.externalUrl:
        if not doc.platform:
            raise ValueError(f"{context} sets 'externalUrl' but is missing 'platform'")
        document = Document.create_external_document(
            id=doc.id,
            title=doc.title,
            platform=doc.platform,
            external_url=doc.externalUrl,
            external_id=doc.externalId,
            text=doc.text,
            status=doc.status,
            show_in_global_context=doc.showInGlobalContext,
            parent_document=parent_document,
            related_assets=doc.relatedAssets or None,
            related_documents=related_documents,
            custom_properties=custom_properties,
            created_time=_EPOCH,
            last_modified_time=_EPOCH,
            **common,
        )
    else:
        if doc.text is None:
            raise ValueError(f"{context} requires 'text' for a native document (no 'externalUrl' set)")
        document = Document.create_document(
            id=doc.id,
            title=doc.title,
            text=doc.text,
            status=doc.status,
            show_in_global_context=doc.showInGlobalContext,
            parent_document=parent_document,
            related_assets=doc.relatedAssets or None,
            related_documents=related_documents,
            custom_properties=custom_properties,
            created_time=_EPOCH,
            last_modified_time=_EPOCH,
            **common,
        )

    yield from document.as_workunits()
