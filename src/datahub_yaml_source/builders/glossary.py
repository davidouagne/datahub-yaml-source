from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import DisplayPropertiesClass
from datahub.sdk.glossary_node import GlossaryNode
from datahub.sdk.glossary_term import GlossaryTerm

from datahub_yaml_source.builders.common import common_sdk_kwargs
from datahub_yaml_source.models import GlossaryNodeDoc, GlossaryRelatedTermsDoc, GlossaryTermDoc
from datahub_yaml_source.urns import ReferenceIndex, glossary_node_urn, glossary_term_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport

# Neither SDK V2 wrapper implements HasSubtype (verified via __mro__ against
# acryl-datahub 1.7.0.3); GlossaryNode additionally has no HasDomain.
# GlossaryNodeDoc's domain/subTypes and GlossaryTermDoc's subTypes therefore
# route through `common_sdk_kwargs()`'s extra_aspects fallback automatically.
# (Both wrappers gained a native `tags=` kwarg in the 1.7.x SDK -- they didn't
# have one in 1.6.0.13, where this connector's floor previously sat.)
_GLOSSARY_NODE_NATIVE_KWARGS = frozenset({"owners", "links", "tags"})
_GLOSSARY_TERM_NATIVE_KWARGS = frozenset({"owners", "links", "tags", "domain"})


def _resolve_related_term_urns(
    term_ids: list[str] | None,
    index: ReferenceIndex,
    report: YamlSourceReport,
    context: str,
    relation: str,
) -> list[str] | None:
    if not term_ids:
        return None
    urns = []
    for term_id in term_ids:
        if not index.has_glossary_term(term_id):
            report.report_dangling_reference(
                f"{context} references undeclared {relation} '{term_id}'"
            )
        urns.append(glossary_term_urn(term_id))
    return urns


def build_glossary_node(
    doc: GlossaryNodeDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"GLOSSARY_NODE '{doc.id}'"
    parent_node_urn = None
    if doc.parentNode:
        if not index.has_glossary_node(doc.parentNode):
            report.report_dangling_reference(
                f"{context} references undeclared parentNode '{doc.parentNode}'"
            )
        parent_node_urn = glossary_node_urn(doc.parentNode)

    common = common_sdk_kwargs(doc, index, report, context, native=_GLOSSARY_NODE_NATIVE_KWARGS)
    if doc.displayProperties:
        extra_aspects = list(common.get("extra_aspects") or [])
        extra_aspects.append(DisplayPropertiesClass(colorHex=doc.displayProperties.colorHex))
        common["extra_aspects"] = extra_aspects

    node = GlossaryNode(
        id=doc.id,
        display_name=doc.name,
        definition=doc.definition or "",
        parent_node=parent_node_urn,
        **common,
    )
    yield from node.as_workunits()


def build_glossary_term(
    doc: GlossaryTermDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"GLOSSARY_TERM '{doc.id}'"
    parent_node_urn = None
    if doc.parentNode:
        if not index.has_glossary_node(doc.parentNode):
            report.report_dangling_reference(
                f"{context} references undeclared parentNode '{doc.parentNode}'"
            )
        parent_node_urn = glossary_node_urn(doc.parentNode)

    common = common_sdk_kwargs(doc, index, report, context, native=_GLOSSARY_TERM_NATIVE_KWARGS)
    if doc.displayProperties:
        extra_aspects = list(common.get("extra_aspects") or [])
        extra_aspects.append(DisplayPropertiesClass(colorHex=doc.displayProperties.colorHex))
        common["extra_aspects"] = extra_aspects

    related: GlossaryRelatedTermsDoc = doc.glossaryRelatedTerms or GlossaryRelatedTermsDoc()

    term = GlossaryTerm(
        id=doc.id,
        display_name=doc.name,
        definition=doc.definition or "",
        parent_node=parent_node_urn,
        term_source=doc.termSource or "INTERNAL",
        source_ref=doc.sourceRef,
        source_url=doc.sourceUrl,
        is_a=_resolve_related_term_urns(
            related.isRelatedTerms, index, report, context, "glossaryRelatedTerms.isRelatedTerms"
        ),
        has_a=_resolve_related_term_urns(
            related.hasRelatedTerms, index, report, context, "glossaryRelatedTerms.hasRelatedTerms"
        ),
        values=_resolve_related_term_urns(
            related.values, index, report, context, "glossaryRelatedTerms.values"
        ),
        related_terms=_resolve_related_term_urns(
            related.relatedTerms, index, report, context, "glossaryRelatedTerms.relatedTerms"
        ),
        **common,
    )
    yield from term.as_workunits()
