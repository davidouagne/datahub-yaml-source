"""Builder tests for the semantic-layer family (Phase 5B): SEMANTIC_MODEL, METRIC."""

from datahub_yaml_source.builders.semantic import build_metric, build_semantic_model
from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import MetricDoc, SemanticModelDoc, TagDoc
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _repo_with_known_tag() -> ParsedRepository:
    repo = ParsedRepository()
    repo.tags.append(TagDoc(kind="TAG", name="pii"))
    return repo


def test_build_semantic_model_emits_info_and_ai_context():
    repo = _repo_with_known_tag()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = SemanticModelDoc.model_validate(
        {
            "kind": "SEMANTIC_MODEL",
            "platform": "dbt",
            "path": "models/marts",
            "id": "patients_actifs",
            "displayName": "Patients actifs",
            "description": "Active patient cohort",
            "nativeDefinition": "select * from ehr_public_patient where actif",
            "datasets": [{"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"}],
            "aiContext": {"synonyms": ["active cohort"], "instructions": "Use for headcount"},
            "externalUrl": "https://dbt.example.org/marts/patients_actifs",
            "tags": ["pii"],
        }
    )

    wus = list(build_semantic_model(doc, index, report))
    assert not report.dangling_references
    assert (
        wus[0].metadata.entityUrn
        == "urn:li:semanticModel:(urn:li:dataPlatform:dbt,models/marts,patients_actifs)"
    )

    info = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "SemanticModelInfoClass"
    )
    assert info.name == "Patients actifs"
    assert info.externalUrl == "https://dbt.example.org/marts/patients_actifs"
    assert info.datasets == [
        "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"
    ]

    ai_context = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "AiContextClass"
    )
    assert ai_context.synonyms == ["active cohort"]

    assert any(wu.metadata.aspect.__class__.__name__ == "GlobalTagsClass" for wu in wus)


def test_build_metric_requires_semantic_model_and_emits_upstreams_and_relationships():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = MetricDoc.model_validate(
        {
            "kind": "METRIC",
            "platform": "dbt",
            "path": "models/marts",
            "id": "taux_readmission_30j",
            "displayName": "Taux de readmission a 30 jours",
            "semanticModel": {"platform": "dbt", "path": "models/marts", "id": "patients_actifs"},
            "expression": "count(readmission_30j) / count(*)",
            "derivedFrom": [{"platform": "dbt", "path": "models/marts", "id": "base_metric"}],
            "relatedMetrics": [
                {"platform": "dbt", "path": "models/marts", "id": "taux_readmission_90j"}
            ],
            "datasetUpstreams": [
                {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"}
            ],
        }
    )

    wus = list(build_metric(doc, index, report))
    assert (
        wus[0].metadata.entityUrn
        == "urn:li:metric:(urn:li:dataPlatform:dbt,models/marts,taux_readmission_30j)"
    )

    info = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "MetricInfoClass"
    )
    assert (
        info.semanticModel
        == "urn:li:semanticModel:(urn:li:dataPlatform:dbt,models/marts,patients_actifs)"
    )
    assert info.expression.dialects[0].expression == "count(readmission_30j) / count(*)"

    relationships = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "MetricRelationshipsClass"
    )
    assert [e.destinationUrn for e in relationships.derivedFrom] == [
        "urn:li:metric:(urn:li:dataPlatform:dbt,models/marts,base_metric)"
    ]
    assert [e.destinationUrn for e in relationships.relatedMetrics] == [
        "urn:li:metric:(urn:li:dataPlatform:dbt,models/marts,taux_readmission_90j)"
    ]

    upstreams = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "MetricUpstreamsClass"
    )
    assert [e.destinationUrn for e in upstreams.datasetUpstreams] == [
        "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"
    ]
