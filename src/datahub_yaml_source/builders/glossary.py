from typing import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.sdk.glossary_node import GlossaryNode
from datahub.sdk.glossary_term import GlossaryTerm

from datahub_yaml_source.models import GlossaryNodeDoc, GlossaryTermDoc
from datahub_yaml_source.urns import glossary_node_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport
from datahub_yaml_source.urns import ReferenceIndex


def build_glossary_node(
    doc: GlossaryNodeDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    parent_node_urn = None
    if doc.parentNode:
        if not index.has_glossary_node(doc.parentNode):
            report.report_dangling_reference(
                f"GLOSSARY_NODE '{doc.id}' references undeclared parentNode '{doc.parentNode}'"
            )
        parent_node_urn = glossary_node_urn(doc.parentNode)

    node = GlossaryNode(
        id=doc.id,
        display_name=doc.name,
        definition=doc.definition or "",
        parent_node=parent_node_urn,
    )
    yield from node.as_workunits()


def build_glossary_term(
    doc: GlossaryTermDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    parent_node_urn = None
    if doc.parentNode:
        if not index.has_glossary_node(doc.parentNode):
            report.report_dangling_reference(
                f"GLOSSARY_TERM '{doc.id}' references undeclared parentNode '{doc.parentNode}'"
            )
        parent_node_urn = glossary_node_urn(doc.parentNode)

    term = GlossaryTerm(
        id=doc.id,
        display_name=doc.name,
        definition=doc.definition or "",
        parent_node=parent_node_urn,
    )
    yield from term.as_workunits()
