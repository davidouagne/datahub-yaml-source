from collections import defaultdict, deque
from collections.abc import Iterable

from datahub.emitter.mcp_builder import gen_containers
from datahub.ingestion.api.workunit import MetadataWorkUnit

from datahub_yaml_source.builders.common import (
    build_data_platform_instance_aspect,
    build_ownership_aspect,
    common_aspect_mcps,
    mcp_workunit,
    owner_urn,
    stringify_custom_properties,
)
from datahub_yaml_source.models import ContainerDoc, normalize_owners, normalize_sub_types
from datahub_yaml_source.urns import (
    ReferenceIndex,
    container_key,
    container_natural_key,
    domain_urn,
)
from datahub_yaml_source.yaml_source_report import YamlSourceReport

NaturalKey = tuple[str, object, str, object, str]


def topological_sort_containers(containers: list[ContainerDoc]) -> list[ContainerDoc]:
    """Order containers so that every parent precedes its children.

    Uses Kahn's algorithm. Containers whose parent isn't itself declared in
    `containers` are treated as roots (in-degree 0). Any cycle (which should
    never happen in practice) is broken by appending the remaining nodes in
    their original order, so this always terminates.
    """
    by_key: dict[NaturalKey, ContainerDoc] = {container_natural_key(c): c for c in containers}
    children: dict[NaturalKey, list[NaturalKey]] = defaultdict(list)
    indegree: dict[NaturalKey, int] = dict.fromkeys(by_key, 0)

    for key, doc in by_key.items():
        if doc.parentContainer is not None:
            parent_key = container_natural_key(doc.parentContainer)
            if parent_key in by_key:
                children[parent_key].append(key)
                indegree[key] += 1

    queue: deque = deque(k for k, d in indegree.items() if d == 0)
    order: list[ContainerDoc] = []
    seen = set()

    while queue:
        key = queue.popleft()
        if key in seen:
            continue
        seen.add(key)
        order.append(by_key[key])
        for child_key in children[key]:
            indegree[child_key] -= 1
            if indegree[child_key] == 0:
                queue.append(child_key)

    leftover = [doc for key, doc in by_key.items() if key not in seen]
    order.extend(leftover)
    return order


def build_container(
    doc: ContainerDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"CONTAINER '{doc.name}'"
    key = container_key(doc)
    parent_key = None
    if doc.parentContainer is not None:
        if not index.has_container(doc.parentContainer):
            report.report_dangling_reference(
                f"CONTAINER '{doc.name}' references an undeclared parentContainer "
                f"(platform={doc.parentContainer.platform}, "
                f"database={doc.parentContainer.database}, "
                f"schema={doc.parentContainer.schema_name})"
            )
        parent_key = container_key(doc.parentContainer)

    owners = normalize_owners(doc.owners)
    # gen_containers() only supports a single owner; when there's more than
    # one, skip it here and emit the full ownership aspect afterward instead.
    primary_owner_urn = owner_urn(owners[0].owner) if len(owners) == 1 else None
    primary_ownership_type = owners[0].type if len(owners) == 1 else None

    domain = None
    if doc.domains:
        if not index.has_domain(doc.domains):
            report.report_dangling_reference(
                f"{context} references undeclared domain '{doc.domains}'"
            )
        domain = domain_urn(doc.domains)

    sub_types = normalize_sub_types(doc.subTypes) or ["container"]

    yield from gen_containers(
        container_key=key,
        name=doc.name,
        sub_types=sub_types,
        parent_container_key=parent_key,
        extra_properties=stringify_custom_properties(doc.properties),
        description=doc.description,
        owner_urn=primary_owner_urn,
        ownership_type=primary_ownership_type,
        external_url=doc.externalUrl,
        tags=doc.tags,
        domain_urn=domain,
        # `structured_properties=` is deliberately not passed here: it only
        # accepts a single value per property (`add_structured_properties_to_entity_wu`
        # builds `values=[value]`), which silently drops all but one value for
        # a MULTIPLE-cardinality property. Emitted as a follow-up MCP below instead.
    )

    # gen_containers() only supports a single owner; emit the full ownership
    # aspect afterward (overwriting the single-owner one) when there's more than one.
    if len(owners) > 1:
        yield mcp_workunit(key.as_urn(), build_ownership_aspect(owners))

    # `instance` never affects the container's URN (see `container_key()`, which
    # deliberately omits it from the ContainerKey so the GUID stays stable). That
    # same omission means `gen_containers()` above -- which derives its own
    # dataPlatformInstance aspect from `container_key.instance` -- always emits
    # it with `instance=None`, even when the YAML declares one. Overwrite it with
    # a follow-up MCP carrying the real value, same pattern as the multi-owner
    # fallback above.
    if doc.instance:
        dpi = build_data_platform_instance_aspect(doc.platform, doc.instance)
        yield mcp_workunit(key.as_urn(), dpi)

    # terms/applications/links/deprecation/structuredProperties have no
    # gen_containers() kwarg at all; owners/tags/subTypes/domain were just
    # handled above (natively or via the multi-owner fallback), so skip them
    # here to avoid emitting the same aspect twice.
    yield from common_aspect_mcps(
        key.as_urn(),
        doc,
        index,
        report,
        context,
        skip=frozenset({"owners", "tags", "subTypes", "domain"}),
    )
