"""Builder tests for the BI-layer kinds (CHART, DASHBOARD)."""

from datahub_yaml_source.builders.chart import build_chart
from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import ChartDoc, ContainerDoc, DomainDoc, TagDoc
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _repository_with_known_references() -> ParsedRepository:
    repo = ParsedRepository()
    repo.tags.append(TagDoc(kind="TAG", name="dashboard"))
    repo.domains.append(DomainDoc(kind="DOMAIN", id="d1", name="Domain 1"))
    repo.containers.append(
        ContainerDoc.model_validate(
            {
                "kind": "CONTAINER",
                "platform": "superset",
                "database": "superset_metadata",
                "env": "PROD",
                "name": "Superset",
            }
        )
    )
    return repo


def test_build_chart_emits_chart_info_and_common_aspects():
    repo = _repository_with_known_references()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = ChartDoc.model_validate(
        {
            "kind": "CHART",
            "name": "patients_par_mois",
            "platform": "superset",
            "displayName": "Patients par mois",
            "description": "Nombre de patients actifs par mois",
            "chartUrl": "https://superset.example.org/chart/12",
            "chartType": "BAR",
            "container": {"platform": "superset", "database": "superset_metadata", "env": "PROD"},
            "inputDatasets": [{"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"}],
            "tags": ["dashboard"],
            "domains": "d1",
        }
    )

    wus = list(build_chart(doc, index, report))
    assert not report.dangling_references

    aspect_names = {wu.metadata.aspect.__class__.__name__ for wu in wus}
    assert "ChartInfoClass" in aspect_names
    assert "GlobalTagsClass" in aspect_names
    assert "DomainsClass" in aspect_names

    chart_info = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "ChartInfoClass")
    assert chart_info.title == "Patients par mois"
    assert chart_info.chartUrl == "https://superset.example.org/chart/12"
    assert chart_info.inputs == [
        "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"
    ]

    entity_urn = wus[0].metadata.entityUrn
    assert entity_urn == "urn:li:chart:(superset,patients_par_mois)"


def test_build_chart_reports_dangling_tag_and_container():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = ChartDoc.model_validate(
        {
            "kind": "CHART",
            "name": "x",
            "platform": "superset",
            "tags": ["unknown-tag"],
            "container": {"platform": "superset", "database": "missing", "env": "PROD"},
        }
    )

    list(build_chart(doc, index, report))
    assert len(report.dangling_references) == 2
    assert any("unknown-tag" in ref for ref in report.dangling_references)
    assert any("undeclared container" in ref for ref in report.dangling_references)
