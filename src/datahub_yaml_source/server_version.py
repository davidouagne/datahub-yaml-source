"""The target DataHub server's version against the supported range.

A *Supported DataHub version* is a server (GMS) minor -- see CONTEXT.md and
docs/adr/0007-datahub-version-support-policy.md §2, §4. The range is the
`acryl-datahub` requirement declared in pyproject.toml, read back from the
installed package metadata so it is never duplicated here. It is compared
per minor: its patch-level floor is a client SDK constraint, and GMS
reports versions such as `v1.7.0` or `v1.7.0.1` that would otherwise fall
below it.
"""

import logging
from importlib.metadata import requires

from datahub.configuration.common import ConfigurationError
from datahub.ingestion.api.source import SourceReport
from datahub.utilities.server_config_util import RestServiceConfig
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

logger = logging.getLogger(__name__)

_DISTRIBUTION = "datahub-yaml-source"
_CLIENT = "acryl-datahub"


def supported_range() -> SpecifierSet:
    """The `acryl-datahub` specifier this installed package declares."""
    for line in requires(_DISTRIBUTION) or []:
        requirement = Requirement(line)
        if requirement.name == _CLIENT and requirement.marker is None:
            return requirement.specifier
    raise LookupError(f"{_DISTRIBUTION} declares no {_CLIENT} requirement")


def _minor_is_supported(major: int, minor: int, specifier: SpecifierSet) -> bool:
    # A minor is supported when the range admits any version of it: its
    # first or its last possible one is enough for `>=` / `<` bounds.
    first, last = Version(f"{major}.{minor}.0"), Version(f"{major}.{minor}.9999.9999")
    return specifier.contains(first) or specifier.contains(last)


def _server_minor(server_config: RestServiceConfig) -> tuple[int, int] | None:
    """The server's (major, minor), or None when it can't be compared."""
    if server_config.is_datahub_cloud or not server_config.service_version:
        return None
    try:
        parsed = server_config.parsed_version
    except ValueError:
        return None
    if parsed is None:
        return None
    major, minor, _, _ = parsed
    return major, minor


def check_server_version(
    server_config: RestServiceConfig | None, report: SourceReport, *, strict: bool = False
) -> tuple[int, int] | None:
    """Warn on `report` when the server's minor is outside the supported range.

    Returns the server's (major, minor), or None when it is unknowable -- the
    input of the Minimum server version filter.

    `server_config` is None when the run has no graph (a `file` / `console`
    sink, `datahub-kafka` without `rest_fallback`, no `datahub_api`): there is
    no server to compare, so this is only logged. With `strict`, every case
    that would warn -- and the no-graph case -- raises `ConfigurationError`
    instead, before anything is emitted.
    """
    specifier = supported_range()
    supported = f"supported {_CLIENT}{specifier} (compared per minor)"
    if server_config is None:
        if strict:
            raise ConfigurationError(
                "strict_version is set but this run has no DataHub graph, so the "
                f"target server version can't be checked ({supported}). Use the "
                "datahub-rest sink or add a top-level 'datahub_api:' block to the recipe."
            )
        logger.info(
            "No DataHub graph in this run: the target server version can't be "
            "checked against the %s.",
            supported,
        )
        return None

    server_minor = _server_minor(server_config)
    if server_minor is None:
        kind = "DataHub Cloud" if server_config.is_datahub_cloud else "unreadable"
        context = f"server {server_config.service_version!r} ({kind}), {supported}"
        if strict:
            raise ConfigurationError(f"DataHub server version not recognised: {context}")
        report.warning(
            title="DataHub server version not recognised",
            message="The target DataHub server's version could not be compared with "
            "the range this source is verified against; ingestion continues.",
            context=context,
        )
        return None
    if not _minor_is_supported(*server_minor, specifier):
        context = f"server {server_config.service_version}, {supported}"
        if strict:
            raise ConfigurationError(f"DataHub server version not supported: {context}")
        report.warning(
            title="DataHub server version not supported",
            message="The target DataHub server is outside the range this source is "
            "verified against; ingestion continues.",
            context=context,
        )
    return server_minor
