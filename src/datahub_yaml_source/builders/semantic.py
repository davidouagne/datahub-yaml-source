"""Builders for the semantic-layer family: SEMANTIC_MODEL, METRIC (Phase 5B)."""

from typing import FrozenSet, Iterable, Optional

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import EdgeClass, MetricUpstreamsClass
from datahub.sdk.metric import AiContextInput, Metric
from datahub.sdk.semantic_model import SemanticModel

from datahub_yaml_source.builders.common import common_sdk_kwargs
from datahub_yaml_source.models import AiContextDoc, MetricDoc, SemanticModelDoc
from datahub_yaml_source.urns import ReferenceIndex, dataset_urn, metric_urn, semantic_model_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport

# Same situation as MLModel/MLModelGroup (C9): neither SemanticModel nor Metric expose
# subtype=/applications=/container= as constructor kwargs, despite the registry
# permitting subTypes/applications on both -- native= is narrowed the same way, and
# externalUrl (present on both info aspects but not as a kwarg either) is set via the
# same `_ensure_*()` post-construction pattern used for MLModel's type/hyperParameters.
_SEMANTIC_ENTITY_NATIVE_KWARGS: FrozenSet[str] = frozenset({"owners", "tags", "terms", "domain", "links"})


def _ai_context_input(doc: Optional[AiContextDoc]) -> Optional[AiContextInput]:
    if doc is None:
        return None
    return AiContextInput(
        synonyms=doc.synonyms,
        instructions=doc.instructions,
        examples=doc.examples,
        custom_instructions=doc.customInstructions,
    )


def build_semantic_model(
    doc: SemanticModelDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"SEMANTIC_MODEL '{doc.id}'"
    common = common_sdk_kwargs(doc, index, report, context, native=_SEMANTIC_ENTITY_NATIVE_KWARGS)

    model = SemanticModel(
        platform=doc.platform,
        path=doc.path,
        id=doc.id,
        platform_instance=doc.instance,
        name=doc.displayName,
        description=doc.description,
        native_definition=doc.nativeDefinition,
        datasets=[dataset_urn(d) for d in doc.datasets] if doc.datasets else None,
        ai_context=_ai_context_input(doc.aiContext),
        **common,
    )
    if doc.externalUrl:
        model._ensure_model_props().externalUrl = doc.externalUrl

    yield from model.as_workunits()


def build_metric(doc: MetricDoc, index: ReferenceIndex, report: YamlSourceReport) -> Iterable[MetadataWorkUnit]:
    context = f"METRIC '{doc.id}'"
    common = common_sdk_kwargs(doc, index, report, context, native=_SEMANTIC_ENTITY_NATIVE_KWARGS)

    # `metricUpstreams` has no SDK involvement at all (unlike `metricRelationships`,
    # which the SDK partially owns -- see below), so it's a plain extra_aspects entry.
    extra_aspects = list(common.get("extra_aspects") or [])
    if doc.datasetUpstreams:
        extra_aspects.append(
            MetricUpstreamsClass(
                datasetUpstreams=[EdgeClass(destinationUrn=dataset_urn(d)) for d in doc.datasetUpstreams]
            )
        )
    common["extra_aspects"] = extra_aspects or None

    metric = Metric(
        platform=doc.platform,
        path=doc.path,
        id=doc.id,
        semantic_model=semantic_model_urn(doc.semanticModel),
        platform_instance=doc.instance,
        name=doc.displayName,
        description=doc.description,
        expression=doc.expression,
        derived_from=[metric_urn(m) for m in doc.derivedFrom] if doc.derivedFrom else None,
        ai_context=_ai_context_input(doc.aiContext),
        **common,
    )
    if doc.externalUrl:
        metric._ensure_metric_props().externalUrl = doc.externalUrl

    # `metricRelationships` is an aspect the SDK already constructs (even an empty one,
    # for `derivedFrom`); setting `relatedMetrics` via a second `extra_aspects` entry
    # would race with it (the DataJobInputOutput precedent). Same `_ensure_*()` pattern
    # as MLModel's `type`/`hyperParameters` (C9).
    if doc.relatedMetrics:
        relationships = metric._ensure_metric_relationships()
        relationships.relatedMetrics = [EdgeClass(destinationUrn=metric_urn(m)) for m in doc.relatedMetrics]

    yield from metric.as_workunits()
