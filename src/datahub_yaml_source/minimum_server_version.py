"""Skip what an older supported DataHub server can't accept (ADR-0007 §5).

Every kind works on every *Supported DataHub version* at or above its
*Minimum server version* (see CONTEXT.md). That minimum is the range floor
for every kind and aspect unless one of the tables below says otherwise.
Applied by one filter over emitted MCPs, never by version branches inside
the builders.

Rules for the tables:

- An entry is added **in the PR that introduces** the kind or aspect needing
  a newer server than the range floor, not in a range-widening PR.
- Only entity types and aspect names are gated, never fields: an older
  server silently trims a field it doesn't know, so a new field enters only
  once every supported minor keeps it.
- The local Version check derives its expected skips from these same tables.
"""

from collections import Counter
from collections.abc import Iterable, Iterator, Mapping

from datahub.ingestion.api.source import SourceReport
from datahub.ingestion.api.workunit import MetadataWorkUnit

from datahub_yaml_source.server_version import ServerMinor

# Report title of a skip; the Version check tolerates exactly these warnings.
SKIP_WARNING_TITLE = "Skipped: needs a newer DataHub server"

# entity type (as in the URN, e.g. "document") -> minimum server minor
MINIMUM_SERVER_MINOR_BY_ENTITY: dict[str, ServerMinor] = {}
# aspect name (e.g. "documentInfo") -> minimum server minor
MINIMUM_SERVER_MINOR_BY_ASPECT: dict[str, ServerMinor] = {}


def required_minor(
    entity_type: str | None,
    aspect_name: str | None,
    *,
    by_entity: Mapping[str, ServerMinor],
    by_aspect: Mapping[str, ServerMinor],
) -> tuple[str, ServerMinor] | None:
    """The (gated name, minimum minor) an MCP needs, or None if ungated.

    When both its entity type and its aspect are gated, the higher minimum
    wins.
    """
    gates = [
        (name, table[name])
        for name, table in ((entity_type, by_entity), (aspect_name, by_aspect))
        if name is not None and name in table
    ]
    return max(gates, key=lambda gate: gate[1]) if gates else None


def filter_by_minimum_server_version(
    stream: Iterable[MetadataWorkUnit],
    server_minor: ServerMinor | None,
    report: SourceReport,
    *,
    by_entity: Mapping[str, ServerMinor] = MINIMUM_SERVER_MINOR_BY_ENTITY,
    by_aspect: Mapping[str, ServerMinor] = MINIMUM_SERVER_MINOR_BY_ASPECT,
) -> Iterator[MetadataWorkUnit]:
    """Drop workunits the server is too old for; one warning per gated name.

    `server_minor` is None when the server version is unknowable (no graph,
    unreadable version, DataHub Cloud): everything is then emitted.
    """
    skipped: Counter[tuple[str, ServerMinor]] = Counter()
    for wu in stream:
        metadata = wu.metadata
        gate = required_minor(
            getattr(metadata, "entityType", None),
            getattr(metadata, "aspectName", None),
            by_entity=by_entity,
            by_aspect=by_aspect,
        )
        if server_minor is not None and gate is not None and server_minor < gate[1]:
            skipped[gate] += 1
            continue
        yield wu

    for (name, (major, minor)), count in sorted(skipped.items()):
        report.warning(
            title=SKIP_WARNING_TITLE,
            message="Metadata this DataHub server version can't accept was not "
            "emitted; it will be once the server is upgraded.",
            context=f"{name}: {count} skipped, needs server {major}.{minor} or newer",
        )
