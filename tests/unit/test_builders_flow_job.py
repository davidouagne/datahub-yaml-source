from datahub_yaml_source.builders.data_flow_job import build_data_flow, build_data_job
from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import ContainerDoc, DataFlowDoc, DataJobDoc, TagDoc
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def test_build_data_flow_emits_expected_urn_and_properties():
    doc = DataFlowDoc.model_validate(
        {
            "kind": "DATA_FLOW",
            "orchestrator": "airflow",
            "flowId": "ehr_to_duckdb_raw_layer",
            "cluster": "PROD",
            "name": "EHR to duckDB Raw Layer",
            "project": "ehr2rawlayer",
            "owners": [
                {"owner": "eds-data-engineering", "type": "TECHNICAL_OWNER"},
                {"owner": "eds-interoperability", "type": "BUSINESS_OWNER"},
            ],
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    wus = list(build_data_flow(doc, index, report))
    assert wus[0].metadata.entityUrn == "urn:li:dataFlow:(airflow,ehr_to_duckdb_raw_layer,PROD)"
    info = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "DataFlowInfoClass"
    )
    assert info.name == "EHR to duckDB Raw Layer"
    ownership = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "OwnershipClass"
    )
    assert len(ownership.owners) == 2


def test_build_data_job_links_to_flow_and_datasets():
    repo = ParsedRepository()
    repo.tags.append(TagDoc(kind="TAG", name="pmsi"))
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DataJobDoc.model_validate(
        {
            "kind": "DATA_JOB",
            "jobId": "ehr_patient_to_raw_layer",
            "dataFlow": {
                "orchestrator": "airflow",
                "flowId": "ehr_to_duckdb_raw_layer",
                "cluster": "PROD",
            },
            "name": "EHR Patient -> DuckDB raw-layer patient",
            "type": "RawCopy",
            "tags": ["pmsi"],
            "inputDatasets": [
                {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"}
            ],
            "outputDatasets": [
                {"platform": "duckdb", "name": "warehouse_raw-layer_patient", "env": "PROD"}
            ],
            "fineGrainedLineages": [
                {
                    "upstream": {
                        "platform": "postgres",
                        "name": "ehr_public_patient",
                        "env": "PROD",
                        "fieldPath": "patient_id",
                    },
                    "downstream": {
                        "platform": "duckdb",
                        "name": "warehouse_raw-layer_patient",
                        "env": "PROD",
                        "fieldPath": "patient_id",
                    },
                    "operation": "IDENTITY",
                }
            ],
        }
    )

    wus = list(build_data_job(doc, index, report))
    assert not report.dangling_references

    entity_urn = wus[0].metadata.entityUrn
    assert "ehr_to_duckdb_raw_layer" in entity_urn
    assert "ehr_patient_to_raw_layer" in entity_urn

    io_aspect = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "DataJobInputOutputClass"
    )
    assert io_aspect.inputDatasets == [
        "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"
    ]
    assert io_aspect.outputDatasets == [
        "urn:li:dataset:(urn:li:dataPlatform:duckdb,warehouse_raw-layer_patient,PROD)"
    ]
    assert len(io_aspect.fineGrainedLineages) == 1


def test_build_data_job_sets_input_data_jobs():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DataJobDoc.model_validate(
        {
            "kind": "DATA_JOB",
            "jobId": "quality_check",
            "dataFlow": {"orchestrator": "airflow", "flowId": "f1", "cluster": "PROD"},
            "name": "Quality check",
            "inputDataJobs": [
                {
                    "orchestrator": "airflow",
                    "flowId": "f1",
                    "cluster": "PROD",
                    "jobId": "upstream_job",
                }
            ],
        }
    )

    wus = list(build_data_job(doc, index, report))
    io_aspect = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "DataJobInputOutputClass"
    )
    assert io_aspect.inputDatajobs == [
        "urn:li:dataJob:(urn:li:dataFlow:(airflow,f1,PROD),upstream_job)"
    ]


def test_build_data_flow_with_container(monkeypatch):
    repo = ParsedRepository()
    repo.containers.append(
        ContainerDoc.model_validate(
            {
                "kind": "CONTAINER",
                "platform": "duckdb",
                "database": "warehouse",
                "env": "PROD",
                "name": "Warehouse",
                "subTypes": "Database",
            }
        )
    )
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DataFlowDoc.model_validate(
        {
            "kind": "DATA_FLOW",
            "orchestrator": "airflow",
            "flowId": "f1",
            "cluster": "PROD",
            "name": "F1",
            "container": {"platform": "duckdb", "database": "warehouse", "env": "PROD"},
        }
    )

    wus = list(build_data_flow(doc, index, report))
    assert not report.dangling_references
    container_aspect = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "ContainerClass"
    )
    assert container_aspect.container is not None


def test_build_data_job_reports_dangling_tag():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DataJobDoc.model_validate(
        {
            "kind": "DATA_JOB",
            "jobId": "j1",
            "dataFlow": {"orchestrator": "airflow", "flowId": "f1", "cluster": "PROD"},
            "name": "Job 1",
            "tags": ["unknown"],
        }
    )
    list(build_data_job(doc, index, report))
    assert len(report.dangling_references) == 1
