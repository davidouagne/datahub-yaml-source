from typing import Optional

from pydantic import Field

from datahub.ingestion.source.state.stale_entity_removal_handler import (
    StatefulStaleMetadataRemovalConfig,
)
from datahub.ingestion.source.state.stateful_ingestion_base import (
    StatefulIngestionConfigBase,
)


class YamlSourceConfig(StatefulIngestionConfigBase):
    """Source configuration for the YAML metadata-as-code connector.

    This source has no connection of its own -- every platform, environment,
    and instance is declared per-entity inside the YAML files themselves.
    """

    path: str = Field(
        description="Root directory to scan recursively for '*.yml' / '*.yaml' "
        "metadata files (e.g. a checked-out git repository of metadata definitions)."
    )

    fail_on_unresolved_reference: bool = Field(
        default=False,
        description="If true, a reference to a tag/domain/glossary term/container "
        "that was never declared anywhere in the scanned files raises an error "
        "instead of a warning.",
    )

    stateful_ingestion: Optional[StatefulStaleMetadataRemovalConfig] = Field(
        default=None,
        description="Stateful ingestion configuration for stale entity removal. "
        "Enable this to automatically soft-delete entities that were removed "
        "from the YAML files since the last run.",
    )
