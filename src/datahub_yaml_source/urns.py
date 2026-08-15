"""URN / ContainerKey construction and cross-file reference resolution.

Every function here is a pure, deterministic translation from a YAML
reference (platform/name/env, or a natural id) to a DataHub URN or
ContainerKey. Building a URN never fails due to a missing declaration
elsewhere in the repository -- DataHub URNs are just structured strings.

`ReferenceIndex` is the separate piece that answers "was this thing actually
declared somewhere in the repository?", used by builders to decide whether to
emit a warning about a dangling reference (e.g. a `tags: [nope]` pointing at
a tag that was never declared as its own `TAG` document).
"""

from typing import Optional, Set, Tuple, Union

from datahub.emitter.mce_builder import (
    make_data_platform_urn,
    make_dataset_urn_with_platform_instance,
    make_domain_urn,
    make_user_urn,
)
from datahub.emitter.mcp_builder import ContainerKey, DatabaseKey, SchemaKey
from datahub.metadata.urns import (
    ApplicationUrn,
    ChartUrn,
    DashboardUrn,
    DataFlowUrn,
    DataJobUrn,
    DataProcessInstanceUrn,
    DataProductUrn,
    GlossaryNodeUrn,
    GlossaryTermUrn,
    IncidentUrn,
    QueryUrn,
    StructuredPropertyUrn,
    TagUrn,
)

from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import (
    ChartRef,
    ContainerDoc,
    ContainerRef,
    DashboardRef,
    DataFlowJobRef,
    DataFlowRef,
    DatasetFieldRef,
    DatasetRef,
)


def _passthrough_if_urn(value: str, build) -> str:
    if value.startswith("urn:li:"):
        return value
    return build(value)


def dataset_urn(ref: Union[DatasetRef, DatasetFieldRef]) -> str:
    return make_dataset_urn_with_platform_instance(
        platform=ref.platform,
        name=ref.name,
        platform_instance=ref.instance,
        env=ref.env,
    )


def container_key(ref: ContainerRef) -> ContainerKey:
    """Build the ContainerKey for a container reference.

    `instance` is deliberately never passed through to the key, regardless of
    what the YAML declares. Confirmed against three real container GUIDs from
    a production DataHub instance (the `postgres`/`semantic_layer` database
    container, its `public` schema container, and a dataset's `container:`
    reference to that same schema): none of them include `instance` in the
    hash, even when `instance` is explicitly declared in the YAML. In this
    system, `instance` is only ever used for the separate
    `dataPlatformInstance` *aspect* (display/filtering) -- it is never part
    of a container's identity.

    We use DataHub's plain, unmodified `DatabaseKey`/`SchemaKey` classes
    (rather than a subclass overriding `guid_dict()`) so that the SDK's own
    `ContainerKey.parent_key()` reflection -- used to build multi-level browse
    paths when a bare `ContainerKey` is passed as `parent_container=` --
    keeps working. That reflection walks `self.__class__.__bases__`, which
    breaks if the class isn't exactly `SchemaKey`/`DatabaseKey`.

    See `test_container_urn_matches_known_production_guid_*` and
    `test_container_urn_ignores_instance_entirely` in `tests/unit/test_urns.py`.
    """
    if ref.database is None:
        raise ValueError(f"Container reference for platform={ref.platform!r} is missing 'database'")
    if ref.schema_name is not None:
        return SchemaKey(
            platform=ref.platform,
            env=ref.env,
            database=ref.database,
            schema=ref.schema_name,
        )
    return DatabaseKey(
        platform=ref.platform,
        env=ref.env,
        database=ref.database,
    )


def container_urn(ref: ContainerRef) -> str:
    return container_key(ref).as_urn()


def chart_urn(ref: ChartRef) -> str:
    return ChartUrn(ref.platform, ref.name).urn()


def dashboard_urn(ref: DashboardRef) -> str:
    return DashboardUrn(ref.platform, ref.name).urn()


def tag_urn(name: str) -> str:
    return _passthrough_if_urn(name, lambda v: TagUrn(v).urn())


def glossary_term_urn(term_id: str) -> str:
    return _passthrough_if_urn(term_id, lambda v: GlossaryTermUrn(v).urn())


def query_urn(query_id: str) -> str:
    return _passthrough_if_urn(query_id, lambda v: QueryUrn(v).urn())


def incident_urn(incident_id: str) -> str:
    return _passthrough_if_urn(incident_id, lambda v: IncidentUrn(v).urn())


def glossary_node_urn(node_id: str) -> str:
    return _passthrough_if_urn(node_id, lambda v: GlossaryNodeUrn(v).urn())


def domain_urn(domain_id: str) -> str:
    return _passthrough_if_urn(domain_id, make_domain_urn)


def application_urn(app_id: str) -> str:
    return _passthrough_if_urn(app_id, lambda v: ApplicationUrn(v).urn())


def data_platform_urn(platform_name: str) -> str:
    return make_data_platform_urn(platform_name)


def structured_property_urn(qualified_name: str) -> str:
    return _passthrough_if_urn(qualified_name, lambda v: StructuredPropertyUrn(v).urn())


def data_flow_urn(ref: DataFlowRef) -> str:
    return DataFlowUrn(ref.orchestrator, ref.flowId, ref.cluster).urn()


def data_job_urn(ref: DataFlowJobRef) -> str:
    flow_urn = DataFlowUrn(ref.orchestrator, ref.flowId, ref.cluster)
    return DataJobUrn(flow_urn, ref.jobId).urn()


def data_product_urn(product_id: str) -> str:
    return _passthrough_if_urn(product_id, lambda v: DataProductUrn(v).urn())


def data_process_instance_urn(instance_id: str) -> str:
    return _passthrough_if_urn(instance_id, lambda v: DataProcessInstanceUrn(v).urn())


def owner_urn(owner: str) -> str:
    """Owners are always treated as corpusers unless already a full URN."""
    return _passthrough_if_urn(owner, make_user_urn)


def container_natural_key(ref: ContainerRef) -> Tuple[str, str, Optional[str]]:
    """Hashable natural-key tuple identifying a container, for lookups/sorting.

    Deliberately excludes `instance` and `env`, mirroring `container_key()`'s
    GUID computation -- two container declarations that differ only by
    `instance` (or `env`) resolve to the same URN, so they must also be
    considered "the same" here, or `ReferenceIndex.has_container()` would
    raise false dangling-reference warnings for perfectly valid links.
    """
    return (ref.platform, ref.database or "", ref.schema_name)


class ReferenceIndex:
    """Answers "was this reference declared in the repository?" for warnings."""

    def __init__(self, repository: ParsedRepository) -> None:
        self._tag_names: Set[str] = {t.name for t in repository.tags}
        self._glossary_term_ids: Set[str] = {t.id for t in repository.glossary_terms}
        self._glossary_node_ids: Set[str] = {n.id for n in repository.glossary_nodes}
        self._domain_ids: Set[str] = {d.id for d in repository.domains}
        self._application_ids: Set[str] = {a.id for a in repository.applications}
        self._structured_property_names: Set[str] = {
            p.qualifiedName for p in repository.structured_properties
        }
        self._container_keys: Set[Tuple] = {
            container_natural_key(c) for c in repository.containers
        }

    def has_tag(self, name: str) -> bool:
        return name in self._tag_names

    def has_glossary_term(self, term_id: str) -> bool:
        return term_id in self._glossary_term_ids

    def has_glossary_node(self, node_id: str) -> bool:
        return node_id in self._glossary_node_ids

    def has_domain(self, domain_id: str) -> bool:
        return domain_id in self._domain_ids

    def has_application(self, app_id: str) -> bool:
        return app_id in self._application_ids

    def has_structured_property(self, qualified_name: str) -> bool:
        return qualified_name in self._structured_property_names

    def has_container(self, ref: ContainerRef) -> bool:
        return container_natural_key(ref) in self._container_keys
