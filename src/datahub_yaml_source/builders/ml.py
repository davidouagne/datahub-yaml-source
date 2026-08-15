"""Builders for the ML-entity family: MLFEATURE_TABLE, MLFEATURE, MLPRIMARY_KEY,
MLMODEL_GROUP, MLMODEL (Phase 5A).

Kept together in one module (rather than one file per kind, as earlier phases did)
because the five are tightly interrelated: a feature table references its features and
primary keys, a model references its model group and its features.
"""

from typing import FrozenSet, Iterable, List

from datahub.emitter.mce_builder import make_schema_field_urn
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    BaseDataClass,
    CaveatDetailsClass,
    CaveatsAndRecommendationsClass,
    ContainerClass,
    EthicalConsiderationsClass,
    EvaluationDataClass,
    IntendedUseClass,
    MetricsClass,
    MLFeaturePropertiesClass,
    MLFeatureTablePropertiesClass,
    MLModelFactorPromptsClass,
    MLModelFactorsClass,
    MLPrimaryKeyPropertiesClass,
    SourceCodeClass,
    SourceCodeUrlClass,
    TrainingDataClass,
)
from datahub.sdk.mlmodel import MLModel
from datahub.sdk.mlmodelgroup import MLModelGroup

from datahub_yaml_source.builders.common import common_aspect_mcps, common_sdk_kwargs, mcp_workunit, stringify_custom_properties
from datahub_yaml_source.models import (
    MLFeatureDoc,
    MLFeatureTableDoc,
    MLModelDataDoc,
    MLModelDoc,
    MLModelGroupDoc,
    MLPrimaryKeyDoc,
    QuerySubjectRef,
)
from datahub_yaml_source.urns import (
    ReferenceIndex,
    container_key,
    dataset_urn,
    ml_feature_table_urn,
    ml_feature_urn,
    ml_model_group_urn,
    ml_primary_key_urn,
)
from datahub_yaml_source.yaml_source_report import YamlSourceReport

# Neither `MLModel` nor `MLModelGroup` expose `subtype=`/`applications=`/`container=` as
# constructor kwargs (verified by signature inspection), unlike Chart/Dashboard/Dataset --
# all three, plus structuredProperties (as always, C4) and the model card, go via
# `extra_aspects=` instead.
_ML_ENTITY_NATIVE_KWARGS: FrozenSet[str] = frozenset({"owners", "tags", "terms", "domain", "links"})


def _dataset_or_field_urn(ref: QuerySubjectRef) -> str:
    """A QuerySubjectRef's target: a dataset, or one of its columns if `fieldPath` is set.
    Same shape as `build_query()`'s subject resolution."""
    entity_urn = dataset_urn(ref)
    return make_schema_field_urn(entity_urn, ref.fieldPath) if ref.fieldPath else entity_urn


def build_ml_feature_table(
    doc: MLFeatureTableDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"MLFEATURE_TABLE '{doc.name}'"
    entity_urn = ml_feature_table_urn(doc)

    yield mcp_workunit(
        entity_urn,
        MLFeatureTablePropertiesClass(
            customProperties=stringify_custom_properties(doc.properties),
            description=doc.description,
            mlFeatures=[ml_feature_urn(f) for f in doc.mlFeatures] if doc.mlFeatures else None,
            mlPrimaryKeys=[ml_primary_key_urn(k) for k in doc.mlPrimaryKeys] if doc.mlPrimaryKeys else None,
        ),
    )
    yield from common_aspect_mcps(entity_urn, doc, index, report, context)


def build_ml_feature(
    doc: MLFeatureDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"MLFEATURE '{doc.featureNamespace}.{doc.name}'"
    entity_urn = ml_feature_urn(doc)

    yield mcp_workunit(
        entity_urn,
        MLFeaturePropertiesClass(
            customProperties=stringify_custom_properties(doc.properties),
            description=doc.description,
            dataType=doc.dataType,
            sources=[_dataset_or_field_urn(s) for s in doc.sources] if doc.sources else None,
        ),
    )
    yield from common_aspect_mcps(entity_urn, doc, index, report, context)


def build_ml_primary_key(
    doc: MLPrimaryKeyDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"MLPRIMARY_KEY '{doc.featureNamespace}.{doc.name}'"
    entity_urn = ml_primary_key_urn(doc)

    yield mcp_workunit(
        entity_urn,
        MLPrimaryKeyPropertiesClass(
            sources=[_dataset_or_field_urn(s) for s in doc.sources],
            customProperties=stringify_custom_properties(doc.properties),
            description=doc.description,
            dataType=doc.dataType,
        ),
    )
    yield from common_aspect_mcps(entity_urn, doc, index, report, context)


def build_ml_model_group(
    doc: MLModelGroupDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"MLMODEL_GROUP '{doc.name}'"
    common = common_sdk_kwargs(doc, index, report, context, native=_ML_ENTITY_NATIVE_KWARGS)

    extra_aspects = list(common.get("extra_aspects") or [])
    if doc.container is not None:
        if not index.has_container(doc.container):
            report.report_dangling_reference(f"{context} references an undeclared container")
        extra_aspects.append(ContainerClass(container=container_key(doc.container).as_urn()))
    common["extra_aspects"] = extra_aspects or None

    group = MLModelGroup(
        id=doc.name,
        platform=doc.platform,
        platform_instance=doc.instance,
        env=doc.env,
        name=doc.displayName,
        description=doc.description,
        external_url=doc.externalUrl,
        custom_properties=stringify_custom_properties(doc.properties),
        **common,
    )
    yield from group.as_workunits()


def _base_data_list(entries: List[MLModelDataDoc]) -> List[BaseDataClass]:
    return [
        BaseDataClass(dataset=dataset_urn(e.dataset), motivation=e.motivation, preProcessing=e.preProcessing)
        for e in entries
    ]


def build_ml_model(
    doc: MLModelDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"MLMODEL '{doc.name}'"
    common = common_sdk_kwargs(doc, index, report, context, native=_ML_ENTITY_NATIVE_KWARGS)

    extra_aspects = list(common.get("extra_aspects") or [])

    if doc.container is not None:
        if not index.has_container(doc.container):
            report.report_dangling_reference(f"{context} references an undeclared container")
        extra_aspects.append(ContainerClass(container=container_key(doc.container).as_urn()))

    # The "model card": every one of these aspects is valid only on `mlModel`, so they
    # live as plain fields on MLModelDoc rather than a shared Has* mixin (D1 is for
    # aspects shared *across* kinds).
    if doc.intendedUse:
        extra_aspects.append(IntendedUseClass(**doc.intendedUse.model_dump(exclude_none=True)))
    if doc.ethicalConsiderations:
        extra_aspects.append(EthicalConsiderationsClass(**doc.ethicalConsiderations.model_dump(exclude_none=True)))
    if doc.caveatsAndRecommendations:
        car = doc.caveatsAndRecommendations
        caveats = CaveatDetailsClass(**car.caveats.model_dump(exclude_none=True)) if car.caveats else None
        extra_aspects.append(
            CaveatsAndRecommendationsClass(
                caveats=caveats,
                recommendations=car.recommendations,
                idealDatasetCharacteristics=car.idealDatasetCharacteristics,
            )
        )
    if doc.trainingData:
        extra_aspects.append(TrainingDataClass(trainingData=_base_data_list(doc.trainingData)))
    if doc.evaluationData:
        extra_aspects.append(EvaluationDataClass(evaluationData=_base_data_list(doc.evaluationData)))
    if doc.factorPrompts:
        def _factors(f) -> MLModelFactorsClass:
            return MLModelFactorsClass(groups=f.groups, instrumentation=f.instrumentation, environment=f.environment)

        extra_aspects.append(
            MLModelFactorPromptsClass(
                relevantFactors=(
                    [_factors(f) for f in doc.factorPrompts.relevantFactors]
                    if doc.factorPrompts.relevantFactors
                    else None
                ),
                evaluationFactors=(
                    [_factors(f) for f in doc.factorPrompts.evaluationFactors]
                    if doc.factorPrompts.evaluationFactors
                    else None
                ),
            )
        )
    if doc.metrics:
        extra_aspects.append(
            MetricsClass(
                performanceMeasures=doc.metrics.performanceMeasures,
                decisionThreshold=doc.metrics.decisionThreshold,
            )
        )
    if doc.sourceCode:
        extra_aspects.append(
            SourceCodeClass(
                sourceCode=[SourceCodeUrlClass(type=s.type, sourceCodeUrl=s.sourceCodeUrl) for s in doc.sourceCode]
            )
        )

    common["extra_aspects"] = extra_aspects or None

    model = MLModel(
        id=doc.name,
        platform=doc.platform,
        platform_instance=doc.instance,
        env=doc.env,
        name=doc.displayName,
        description=doc.description,
        external_url=doc.externalUrl,
        custom_properties=stringify_custom_properties(doc.properties),
        model_group=ml_model_group_urn(doc.modelGroup) if doc.modelGroup else None,
        **common,
    )

    # `type`/`hyperParameters`/`mlFeatures` have no constructor kwarg on MLModelProperties'
    # remaining fields -- set directly on the aspect object the SDK already owns, the same
    # `_ensure_*()` pattern `build_data_job()` uses for `inputDataJobs` (no public API yet).
    if doc.type or doc.hyperParameters or doc.mlFeatures:
        props = model._ensure_model_props()
        if doc.type:
            props.type = doc.type
        if doc.hyperParameters:
            props.hyperParameters = doc.hyperParameters
        if doc.mlFeatures:
            props.mlFeatures = [ml_feature_urn(f) for f in doc.mlFeatures]

    yield from model.as_workunits()
