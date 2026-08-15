"""Builder tests for the ML-entity family (Phase 5A):
MLFEATURE_TABLE, MLFEATURE, MLPRIMARY_KEY, MLMODEL_GROUP, MLMODEL.
"""

from datahub_yaml_source.builders.ml import (
    build_ml_feature,
    build_ml_feature_table,
    build_ml_model,
    build_ml_model_group,
    build_ml_primary_key,
)
from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import (
    ContainerDoc,
    MLFeatureDoc,
    MLFeatureTableDoc,
    MLModelDoc,
    MLModelGroupDoc,
    MLPrimaryKeyDoc,
    TagDoc,
)
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _repo_with_known_refs() -> ParsedRepository:
    repo = ParsedRepository()
    repo.tags.append(TagDoc(kind="TAG", name="pii"))
    repo.containers.append(
        ContainerDoc.model_validate(
            {"kind": "CONTAINER", "platform": "mlflow", "database": "models", "env": "PROD", "name": "Models"}
        )
    )
    return repo


def test_build_ml_feature_emits_properties_and_sources():
    repo = _repo_with_known_refs()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = MLFeatureDoc.model_validate(
        {
            "kind": "MLFEATURE",
            "featureNamespace": "patient_features",
            "name": "age_at_admission",
            "description": "Age at admission",
            "dataType": "CONTINUOUS",
            "sources": [{"platform": "postgres", "name": "ehr_public_patient", "env": "PROD", "fieldPath": "date_naissance"}],
            "tags": ["pii"],
        }
    )

    wus = list(build_ml_feature(doc, index, report))
    assert not report.dangling_references
    assert wus[0].metadata.entityUrn == "urn:li:mlFeature:(patient_features,age_at_admission)"

    props = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "MLFeaturePropertiesClass")
    assert props.dataType == "CONTINUOUS"
    assert props.sources == [
        "urn:li:schemaField:(urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD),date_naissance)"
    ]
    assert any(wu.metadata.aspect.__class__.__name__ == "GlobalTagsClass" for wu in wus)


def test_build_ml_primary_key_requires_sources_and_supports_dataset_level_source():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = MLPrimaryKeyDoc.model_validate(
        {
            "kind": "MLPRIMARY_KEY",
            "featureNamespace": "patient_features",
            "name": "patient_id",
            "sources": [{"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"}],
        }
    )

    wus = list(build_ml_primary_key(doc, index, report))
    assert wus[0].metadata.entityUrn == "urn:li:mlPrimaryKey:(patient_features,patient_id)"
    props = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "MLPrimaryKeyPropertiesClass")
    assert props.sources == ["urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"]


def test_build_ml_feature_table_resolves_feature_and_primary_key_urns():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = MLFeatureTableDoc.model_validate(
        {
            "kind": "MLFEATURE_TABLE",
            "name": "patient_features",
            "platform": "feast",
            "mlFeatures": [{"featureNamespace": "patient_features", "name": "age_at_admission"}],
            "mlPrimaryKeys": [{"featureNamespace": "patient_features", "name": "patient_id"}],
        }
    )

    wus = list(build_ml_feature_table(doc, index, report))
    assert wus[0].metadata.entityUrn == "urn:li:mlFeatureTable:(urn:li:dataPlatform:feast,patient_features)"
    props = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "MLFeatureTablePropertiesClass"
    )
    assert props.mlFeatures == ["urn:li:mlFeature:(patient_features,age_at_admission)"]
    assert props.mlPrimaryKeys == ["urn:li:mlPrimaryKey:(patient_features,patient_id)"]


def test_build_ml_model_group_reports_dangling_container():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = MLModelGroupDoc.model_validate(
        {
            "kind": "MLMODEL_GROUP",
            "name": "readmission_risk",
            "platform": "mlflow",
            "container": {"platform": "mlflow", "database": "missing", "env": "PROD"},
        }
    )

    wus = list(build_ml_model_group(doc, index, report))
    assert wus[0].metadata.entityUrn == "urn:li:mlModelGroup:(urn:li:dataPlatform:mlflow,readmission_risk,PROD)"
    assert len(report.dangling_references) == 1
    assert any(wu.metadata.aspect.__class__.__name__ == "ContainerClass" for wu in wus)


def test_build_ml_model_emits_model_card_and_hyperparameters():
    repo = _repo_with_known_refs()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = MLModelDoc.model_validate(
        {
            "kind": "MLMODEL",
            "name": "readmission_risk_v3",
            "platform": "mlflow",
            "description": "Readmission risk classifier",
            "type": "classification",
            "hyperParameters": {"n_estimators": 200, "max_depth": 8},
            "modelGroup": {"platform": "mlflow", "name": "readmission_risk", "env": "PROD"},
            "mlFeatures": [{"featureNamespace": "patient_features", "name": "age_at_admission"}],
            "container": {"platform": "mlflow", "database": "models", "env": "PROD"},
            "intendedUse": {"primaryUses": ["Prioritize follow-up"], "outOfScopeUses": ["Automated clinical decisions"]},
            "ethicalConsiderations": {"risksAndHarms": ["Possible bias on under-represented groups"]},
            "caveatsAndRecommendations": {
                "caveats": {"needsFurtherTesting": True},
                "recommendations": "Do not use without clinical oversight",
            },
            "trainingData": [{"dataset": {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"}, "motivation": "cohort"}],
            "evaluationData": [{"dataset": {"platform": "postgres", "name": "ehr_public_patient_holdout", "env": "PROD"}}],
            "factorPrompts": {"relevantFactors": [{"groups": ["Age > 75"]}]},
            "metrics": {"performanceMeasures": ["AUC 0.82"]},
            "sourceCode": [{"type": "ML_MODEL_SOURCE_CODE", "sourceCodeUrl": "https://gitlab.example.org/model"}],
            "tags": ["pii"],
        }
    )

    wus = list(build_ml_model(doc, index, report))
    assert not report.dangling_references
    assert wus[0].metadata.entityUrn == "urn:li:mlModel:(urn:li:dataPlatform:mlflow,readmission_risk_v3,PROD)"

    aspect_names = {wu.metadata.aspect.__class__.__name__ for wu in wus}
    assert {
        "MLModelPropertiesClass", "ContainerClass", "IntendedUseClass", "EthicalConsiderationsClass",
        "CaveatsAndRecommendationsClass", "TrainingDataClass", "EvaluationDataClass",
        "MLModelFactorPromptsClass", "MetricsClass", "SourceCodeClass", "GlobalTagsClass",
    } <= aspect_names

    props = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "MLModelPropertiesClass")
    assert props.type == "classification"
    assert props.hyperParameters == {"n_estimators": 200, "max_depth": 8}
    assert props.mlFeatures == ["urn:li:mlFeature:(patient_features,age_at_admission)"]

    caveats = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "CaveatsAndRecommendationsClass"
    )
    assert caveats.caveats.needsFurtherTesting is True
    assert caveats.recommendations == "Do not use without clinical oversight"


def test_build_ml_model_reports_dangling_container():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = MLModelDoc.model_validate(
        {
            "kind": "MLMODEL",
            "name": "x",
            "platform": "mlflow",
            "container": {"platform": "mlflow", "database": "missing", "env": "PROD"},
        }
    )

    wus = list(build_ml_model(doc, index, report))
    assert len(report.dangling_references) == 1
    assert any(wu.metadata.aspect.__class__.__name__ == "ContainerClass" for wu in wus)


def test_build_ml_model_uses_native_model_group_reference():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = MLModelDoc.model_validate(
        {
            "kind": "MLMODEL",
            "name": "x",
            "platform": "mlflow",
            "modelGroup": {"platform": "mlflow", "name": "g", "env": "PROD"},
        }
    )

    wus = list(build_ml_model(doc, index, report))
    props = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "MLModelPropertiesClass")
    assert props.groups == ["urn:li:mlModelGroup:(urn:li:dataPlatform:mlflow,g,PROD)"]
