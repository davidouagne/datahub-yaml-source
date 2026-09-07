"""Builders for the semantic-layer family: SEMANTIC_MODEL, METRIC (Phase 5B)."""

from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import EdgeClass
from datahub.sdk.metric import AiContextInput, Metric
from datahub.sdk.semantic_model import SemanticFieldInput, SemanticModel, SemanticModelDataset

from datahub_yaml_source.builders.common import common_sdk_kwargs
from datahub_yaml_source.models import (
    AiContextDoc,
    MetricDoc,
    SemanticModelDatasetDoc,
    SemanticModelDoc,
)
from datahub_yaml_source.urns import ReferenceIndex, dataset_urn, metric_urn, semantic_model_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport

# Same situation as MLModel/MLModelGroup (C9): neither SemanticModel nor Metric expose
# subtype=/applications=/container= as constructor kwargs, despite the registry
# permitting subTypes/applications on both -- native= is narrowed the same way, and
# externalUrl (present on both info aspects but not as a kwarg either) is set via the
# same `_ensure_*()` post-construction pattern used for MLModel's type/hyperParameters.
_SEMANTIC_ENTITY_NATIVE_KWARGS: frozenset[str] = frozenset(
    {"owners", "tags", "terms", "domain", "links"}
)


def _ai_context_input(doc: AiContextDoc | None) -> AiContextInput | None:
    if doc is None:
        return None
    return AiContextInput(
        synonyms=doc.synonyms,
        instructions=doc.instructions,
        examples=doc.examples,
        custom_instructions=doc.customInstructions,
    )


def _semantic_model_dataset(
    member: SemanticModelDatasetDoc, doc: SemanticModelDoc, sm_urn: str
) -> SemanticModelDataset:
    """Build one logical dataset of a SEMANTIC_MODEL.

    Lands on its own URN (the model's platform, name defaulting to
    ``<path>/<id>.<alias>``) so it never collides with a physical DATASET document.
    """
    name = member.name or f"{doc.path}/{doc.id}.{member.alias}"
    return SemanticModelDataset(
        platform=doc.platform,
        name=name,
        env=member.env,
        platform_instance=doc.instance,
        semantic_model=sm_urn,
        alias=member.alias,
        description=member.description,
        view_definition=member.viewDefinition,
        schema=[
            SemanticFieldInput(
                field_path=f.fieldPath,
                type=f.type,
                semantic_type=f.semanticType,
                description=f.description,
                nullable=f.nullable,
                is_part_of_key=f.partOfKey,
                expression=f.expression,
                aggregation_function=f.aggregationFunction,
                is_time_dimension=f.isTimeDimension,
            )
            for f in member.fields
        ],
        upstreams=(
            [dataset_urn(d) for d in member.sourceDatasets] if member.sourceDatasets else None
        ),
    )


def build_semantic_model(
    doc: SemanticModelDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"SEMANTIC_MODEL '{doc.id}'"
    common = common_sdk_kwargs(doc, index, report, context, native=_SEMANTIC_ENTITY_NATIVE_KWARGS)

    sm_urn = semantic_model_urn(doc)
    members = [_semantic_model_dataset(m, doc, sm_urn) for m in (doc.datasets or [])]

    model = SemanticModel(
        platform=doc.platform,
        path=doc.path,
        id=doc.id,
        platform_instance=doc.instance,
        name=doc.displayName,
        description=doc.description,
        native_definition=doc.nativeDefinition,
        datasets=members or None,
        ai_context=_ai_context_input(doc.aiContext),
        **common,
    )
    if doc.externalUrl:
        model._ensure_model_props().externalUrl = doc.externalUrl

    yield from model.as_workunits()
    # Each logical dataset is a distinct `dataset` entity (aliased view + its own schema +
    # per-field semanticFieldAnnotation + lineage to the physical sources); it carries the
    # membership back-reference (`semanticModelProperties.semanticModel`), so `SemanticModel`
    # itself no longer needs a `datasets` URN list.
    for member in members:
        yield from member.as_workunits()


def build_metric(
    doc: MetricDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"METRIC '{doc.id}'"
    common = common_sdk_kwargs(doc, index, report, context, native=_SEMANTIC_ENTITY_NATIVE_KWARGS)

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
        # `metricUpstreams` became SDK-owned in acryl-datahub 1.7.0.5 (like
        # `metricRelationships` below); a second `extra_aspects` entry would race with the
        # SDK's own empty one and lose. Use the constructor kwarg.
        upstream_datasets=(
            [dataset_urn(d) for d in doc.datasetUpstreams] if doc.datasetUpstreams else None
        ),
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
        relationships.relatedMetrics = [
            EdgeClass(destinationUrn=metric_urn(m)) for m in doc.relatedMetrics
        ]

    yield from metric.as_workunits()
