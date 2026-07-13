from typing import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.sdk.tag import Tag

from datahub_yaml_source.models import TagDoc


def build_tag(doc: TagDoc) -> Iterable[MetadataWorkUnit]:
    tag = Tag(name=doc.name, description=doc.description)
    yield from tag.as_workunits()
