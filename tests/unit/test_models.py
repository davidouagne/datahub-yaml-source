import pytest
from pydantic import ValidationError

from datahub_yaml_source.models import (
    ContainerDoc,
    DataJobDoc,
    DatasetDoc,
    DocumentParseError,
    RawAspectDoc,
    normalize_owners,
    normalize_sub_types,
    parse_document,
)


def test_parse_document_dispatches_by_kind():
    doc = parse_document({"kind": "TAG", "name": "pii", "description": "PII data"})
    assert doc.__class__.__name__ == "TagDoc"
    assert doc.name == "pii"


def test_parse_document_dispatches_application_kind():
    doc = parse_document({"kind": "APPLICATION", "id": "ORBIS", "name": "ORBIS"})
    assert doc.__class__.__name__ == "ApplicationDoc"
    assert doc.id == "ORBIS"


def test_parse_document_dispatches_raw_aspect_by_aspect_name():
    doc = parse_document(
        {
            "aspectName": "DATASET_PROFILE",
            "dataset": {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"},
            "rowCount": 100,
        }
    )
    assert isinstance(doc, RawAspectDoc)
    assert doc.aspectName == "DATASET_PROFILE"
    assert doc.model_extra["rowCount"] == 100


def test_parse_document_rejects_unknown_kind():
    with pytest.raises(DocumentParseError, match="Unknown kind"):
        parse_document({"kind": "NOT_A_REAL_KIND", "name": "x"})


def test_parse_document_rejects_document_without_kind_or_aspect_name():
    with pytest.raises(DocumentParseError, match="neither"):
        parse_document({"name": "mystery"})


def test_container_doc_parses_schema_alias_without_colliding_with_pydantic():
    doc = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "ehr",
            "schema": "public",
            "env": "PROD",
            "name": "public",
        }
    )
    assert doc.schema_name == "public"


def test_dataset_doc_schema_block_parses_fields_and_foreign_keys():
    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "ehr_public_actes",
            "platform": "postgres",
            "env": "PROD",
            "schema": {
                "fields": [
                    {"fieldPath": "acte_id", "type": "number", "partOfKey": True},
                ],
                "foreignKeys": [
                    {
                        "name": "fk_actes_patient",
                        "sourceFields": [
                            {
                                "platform": "postgres",
                                "name": "actes",
                                "env": "PROD",
                                "fieldPath": "patient_id",
                            }
                        ],
                        "foreignDataset": {
                            "platform": "postgres",
                            "name": "patient",
                            "env": "PROD",
                        },
                        "foreignFields": [
                            {
                                "platform": "postgres",
                                "name": "patient",
                                "env": "PROD",
                                "fieldPath": "patient_id",
                            }
                        ],
                    }
                ],
            },
        }
    )
    assert doc.schema_block is not None
    assert doc.schema_block.fields[0].partOfKey is True
    assert doc.schema_block.foreignKeys[0].foreignDataset.name == "patient"


def test_dataset_doc_missing_required_platform_raises():
    with pytest.raises(ValidationError):
        DatasetDoc.model_validate({"kind": "DATASET", "name": "x"})


def test_data_job_doc_requires_data_flow_ref():
    with pytest.raises(ValidationError):
        DataJobDoc.model_validate({"kind": "DATA_JOB", "jobId": "j1", "name": "Job 1"})


@pytest.mark.parametrize(
    "owners_input,expected_len",
    [
        (None, 0),
        ({"owner": "datahub", "type": "TECHNICAL_OWNER"}, 1),
        ([{"owner": "a"}, {"owner": "b", "type": "BUSINESS_OWNER"}], 2),
    ],
)
def test_normalize_owners_handles_single_dict_or_list(owners_input, expected_len):
    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "x",
            "platform": "postgres",
            "owners": owners_input,
        }
    )
    normalized = normalize_owners(doc.owners)
    assert len(normalized) == expected_len


@pytest.mark.parametrize(
    "sub_types_input,expected",
    [
        (None, []),
        ("Table", ["Table"]),
        (["Table", "External Table"], ["Table", "External Table"]),
    ],
)
def test_normalize_sub_types_handles_string_or_list(sub_types_input, expected):
    assert normalize_sub_types(sub_types_input) == expected


def test_dataset_doc_coerces_bare_string_glossary_terms_and_tags_to_list():
    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "x",
            "platform": "postgres",
            "tags": "fhir-r4",
            "glossaryTerms": "fhir:Condition",
        }
    )
    assert doc.tags == ["fhir-r4"]
    assert doc.glossaryTerms == ["fhir:Condition"]


def test_dataset_doc_coerces_bare_string_applications_to_list():
    doc = DatasetDoc.model_validate(
        {"kind": "DATASET", "name": "x", "platform": "postgres", "applications": "ORBIS"}
    )
    assert doc.applications == ["ORBIS"]


def test_dataset_doc_parses_view_properties():
    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "v1",
            "platform": "oracle",
            "subTypes": "View",
            "viewProperties": {"viewLogic": "SELECT 1 FROM dual"},
        }
    )
    assert doc.viewProperties.viewLogic == "SELECT 1 FROM dual"
    assert doc.viewProperties.viewLanguage == "SQL"
    assert doc.viewProperties.materialized is False


def test_fine_grained_lineage_doc_allows_missing_upstream_for_constant_operation():
    from datahub_yaml_source.models import FineGrainedLineageDoc

    doc = FineGrainedLineageDoc.model_validate(
        {
            "downstream": {"platform": "postgres", "name": "t", "env": "PROD", "fieldPath": "f"},
            "operation": "CONSTANT",
        }
    )
    assert doc.upstream is None


def test_data_process_instance_doc_coerces_single_run_event_dict_to_list():
    from datahub_yaml_source.models import DataProcessInstanceDoc

    doc = DataProcessInstanceDoc.model_validate(
        {
            "kind": "DATA_PROCESS_INSTANCE",
            "id": "x",
            "name": "x",
            "created": {"timestampMillis": 1},
            "parentTemplate": {
                "orchestrator": "airflow",
                "flowId": "f",
                "cluster": "PROD",
                "jobId": "j",
            },
            "runEvents": {"status": "STARTED", "timestampMillis": 1},
        }
    )
    assert len(doc.runEvents) == 1
