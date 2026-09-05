from collections import defaultdict, deque
from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import DisplayPropertiesClass, DomainPropertiesClass

from datahub_yaml_source.builders.common import common_aspect_mcps, mcp_workunit
from datahub_yaml_source.models import DomainDoc
from datahub_yaml_source.urns import ReferenceIndex, domain_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def topological_sort_domains(domains: list[DomainDoc]) -> list[DomainDoc]:
    """Order domains so every parent precedes its children. Kahn's algorithm,
    mirroring `builders.container.topological_sort_containers()`. A domain
    whose `parentDomain` isn't itself declared is treated as a root; any
    cycle is broken by appending the remaining nodes in original order."""
    by_id: dict[str, DomainDoc] = {d.id: d for d in domains}
    children: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = dict.fromkeys(by_id, 0)

    for id_, doc in by_id.items():
        if doc.parentDomain and doc.parentDomain in by_id:
            children[doc.parentDomain].append(id_)
            indegree[id_] += 1

    queue: deque = deque(k for k, d in indegree.items() if d == 0)
    order: list[DomainDoc] = []
    seen = set()

    while queue:
        key = queue.popleft()
        if key in seen:
            continue
        seen.add(key)
        order.append(by_id[key])
        for child_key in children[key]:
            indegree[child_key] -= 1
            if indegree[child_key] == 0:
                queue.append(child_key)

    leftover = [doc for key, doc in by_id.items() if key not in seen]
    order.extend(leftover)
    return order


def build_domain(
    doc: DomainDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"DOMAIN '{doc.id}'"
    entity_urn = domain_urn(doc.id)

    parent_domain_urn = None
    if doc.parentDomain:
        if not index.has_domain(doc.parentDomain):
            report.report_dangling_reference(
                f"{context} references undeclared parentDomain '{doc.parentDomain}'"
            )
        parent_domain_urn = domain_urn(doc.parentDomain)

    yield mcp_workunit(
        entity_urn,
        DomainPropertiesClass(
            name=doc.name, description=doc.description, parentDomain=parent_domain_urn
        ),
    )

    if doc.displayProperties:
        yield mcp_workunit(
            entity_urn, DisplayPropertiesClass(colorHex=doc.displayProperties.colorHex)
        )

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)
