from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.sdk.tag import Tag

from datahub_yaml_source.builders.common import common_sdk_kwargs
from datahub_yaml_source.models import TagDoc
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport

# Tag's SDK V2 wrapper only implements HasOwnership -- no tags/terms/domain/
# links/subtype support at all (verified via Tag.__mro__), which happens to
# match TagDoc's mixins (HasOwners, HasDeprecation only).
_NATIVE_KWARGS = frozenset({"owners"})


def build_tag(
    doc: TagDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    common = common_sdk_kwargs(doc, index, report, f"TAG '{doc.name}'", native=_NATIVE_KWARGS)
    tag = Tag(name=doc.name, description=doc.description, color=doc.colorHex, **common)
    yield from tag.as_workunits()
