import pytest

from datahub_yaml_source.builders.assertion import build_assertion
from datahub_yaml_source.builders.data_process_instance import build_data_process_instance
from datahub_yaml_source.builders.data_product import build_data_product
from datahub_yaml_source.builders.document import build_document
from datahub_yaml_source.builders.incident import build_incident
from datahub_yaml_source.builders.query import build_query
from datahub_yaml_source.builders.raw_aspect import build_raw_aspect
from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import (
    AssertionDoc,
    DataProcessInstanceDoc,
    DataProductDoc,
    DocumentDoc,
    DomainDoc,
    GlossaryTermDoc,
    IncidentDoc,
    QueryDoc,
    RawAspectDoc,
    StructuredPropertyDoc,
    TagDoc,
)
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def test_build_data_product_emits_properties_assets_and_structured_properties():
    repo = ParsedRepository()
    repo.structured_properties.append(
        StructuredPropertyDoc.model_validate(
            {
                "kind": "STRUCTURED_PROPERTY",
                "qualifiedName": "fr.aphp.healthdcat.publishingFrequency",
                "valueType": "string",
                "entityTypes": ["dataProduct"],
            }
        )
    )
    repo.domains.append(DomainDoc(kind="DOMAIN", id="9306fe49bb1f70f491a712ff19b8d972", name="Parcours patient"))
    repo.tags.append(TagDoc(kind="TAG", name="aphp:access"))
    repo.glossary_terms.append(
        GlossaryTermDoc(kind="GLOSSARY_TERM", id="aphp:medico-administrative", name="Donnees medico-administratives")
    )
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DataProductDoc.model_validate(
        {
            "kind": "DATA_PRODUCT",
            "id": "b78435bfad26dab4c11e6e41c2a72b53",
            "name": "Venues et sejours",
            "domains": "9306fe49bb1f70f491a712ff19b8d972",
            "tags": ["aphp:access"],
            "glossaryTerms": ["aphp:medico-administrative"],
            "owners": [{"owner": "a@aphp.fr", "type": "TECHNICAL_OWNER"}],
            "structuredProperties": {
                "fr.aphp.healthdcat.publishingFrequency": "DAILY",
            },
            "assets": [
                "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)",
            ],
        }
    )

    wus = list(build_data_product(doc, index, report))
    assert not report.dangling_references

    props = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "DataProductPropertiesClass"
    )
    assert props.name == "Venues et sejours"
    assert props.assets[0].destinationUrn == "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"

    structured = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "StructuredPropertiesClass"
    )
    assert structured.properties[0].values == ["DAILY"]


def test_build_data_product_reports_dangling_structured_property():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DataProductDoc.model_validate(
        {
            "kind": "DATA_PRODUCT",
            "id": "x",
            "name": "X",
            "structuredProperties": {"unknown.prop": "value"},
        }
    )
    list(build_data_product(doc, index, report))
    assert len(report.dangling_references) == 1


def test_build_data_process_instance_emits_run_events_and_io():
    doc = DataProcessInstanceDoc.model_validate(
        {
            "kind": "DATA_PROCESS_INSTANCE",
            "id": "airflow_ehr_patient_to_raw_layer__2026-05-25T08:00:00",
            "name": "Run 1",
            "type": "BATCH_SCHEDULED",
            "created": {"timestampMillis": 1779696000000, "actor": "svc-airflow"},
            "parentTemplate": {
                "orchestrator": "airflow",
                "flowId": "ehr_to_duckdb_raw_layer",
                "cluster": "PROD",
                "jobId": "ehr_patient_to_raw_layer",
            },
            "inputs": [{"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"}],
            "outputs": [{"platform": "duckdb", "name": "warehouse_raw-layer_patient", "env": "PROD"}],
            "runEvents": [{"status": "STARTED", "timestampMillis": 1779696000000, "attempt": 1}],
        }
    )

    wus = list(build_data_process_instance(doc))
    aspect_names = {wu.metadata.aspect.__class__.__name__ for wu in wus}
    assert aspect_names == {
        "DataProcessInstancePropertiesClass",
        "DataProcessInstanceRelationshipsClass",
        "DataProcessInstanceInputClass",
        "DataProcessInstanceOutputClass",
        "DataProcessInstanceRunEventClass",
    }
    relationships = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "DataProcessInstanceRelationshipsClass"
    )
    assert "ehr_patient_to_raw_layer" in relationships.parentTemplate


def test_build_assertion_freshness():
    doc = AssertionDoc.model_validate(
        {
            "kind": "ASSERTION",
            "id": "ehr-patient-freshness-check-1",
            "sourceType": "NATIVE",
            "assertion": {
                "type": "FRESHNESS",
                "entityUrn": "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)",
                "freshnessType": "DATASET_CHANGE",
                "scheduleType": "CRON",
                "cron": "0 8 * * *",
                "timezone": "UTC",
            },
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    wus = list(build_assertion(doc, index, report))
    aspect = wus[0].metadata.aspect
    assert aspect.type == "FRESHNESS"
    assert aspect.freshnessAssertion.schedule.cron.cron == "0 8 * * *"


def test_build_assertion_sql():
    doc = AssertionDoc.model_validate(
        {
            "kind": "ASSERTION",
            "id": "id2",
            "assertion": {
                "type": "SQL",
                "entityUrn": "urn:li:dataset:(urn:li:dataPlatform:postgres,x,PROD)",
                "sqlType": "METRIC",
                "statement": "SELECT COUNT(*) FROM t",
                "operator": "GREATER_THAN",
                "value": 0,
            },
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    wus = list(build_assertion(doc, index, report))
    aspect = wus[0].metadata.aspect
    assert aspect.sqlAssertion.statement == "SELECT COUNT(*) FROM t"
    assert aspect.sqlAssertion.parameters.value.value == "0"


def test_build_assertion_field_metric():
    doc = AssertionDoc.model_validate(
        {
            "kind": "ASSERTION",
            "id": "id3",
            "assertion": {
                "type": "FIELD",
                "entityUrn": "urn:li:dataset:(urn:li:dataPlatform:duckdb,x,PROD)",
                "fieldType": "FIELD_METRIC",
                "fieldPath": "patient_id",
                "dataType": "STRING",
                "nativeDataType": "VARCHAR",
                "metric": "UNIQUE_PERCENTAGE",
                "metricOperator": "EQUAL_TO",
                "metricValue": "1.0",
            },
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    wus = list(build_assertion(doc, index, report))
    aspect = wus[0].metadata.aspect
    assert aspect.fieldAssertion.fieldMetricAssertion.metric == "UNIQUE_PERCENTAGE"
    assert aspect.fieldAssertion.fieldValuesAssertion is None


def test_build_assertion_rejects_unsupported_type():
    # DATASET is deliberately unsupported: deprecated upstream in favor of VOLUME.
    doc = AssertionDoc.model_validate(
        {
            "kind": "ASSERTION",
            "id": "id4",
            "assertion": {"type": "DATASET", "entityUrn": "urn:li:dataset:(urn:li:dataPlatform:x,y,PROD)"},
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    with pytest.raises(ValueError, match="Unsupported assertion type"):
        list(build_assertion(doc, index, report))


def test_build_assertion_volume_row_count_total():
    doc = AssertionDoc.model_validate(
        {
            "kind": "ASSERTION",
            "id": "id5",
            "assertion": {
                "type": "VOLUME",
                "entityUrn": "urn:li:dataset:(urn:li:dataPlatform:postgres,x,PROD)",
                "volumeType": "ROW_COUNT_TOTAL",
                "operator": "GREATER_THAN_OR_EQUAL_TO",
                "value": 100,
            },
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    wus = list(build_assertion(doc, index, report))
    aspect = wus[0].metadata.aspect
    assert aspect.volumeAssertion.type == "ROW_COUNT_TOTAL"
    assert aspect.volumeAssertion.rowCountTotal.operator == "GREATER_THAN_OR_EQUAL_TO"


def test_build_assertion_data_schema():
    doc = AssertionDoc.model_validate(
        {
            "kind": "ASSERTION",
            "id": "id7",
            "assertion": {
                "type": "DATA_SCHEMA",
                "entityUrn": "urn:li:dataset:(urn:li:dataPlatform:postgres,x,PROD)",
                "compatibility": "EXACT_MATCH",
                "schemaFields": [{"path": "patient_id", "type": "number", "nativeType": "BIGINT"}],
            },
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    wus = list(build_assertion(doc, index, report))
    aspect = wus[0].metadata.aspect
    assert aspect.schemaAssertion.compatibility == "EXACT_MATCH"
    assert aspect.schemaAssertion.schema.fields[0].fieldPath == "patient_id"
    assert aspect.schemaAssertion.schema.platform == "urn:li:dataPlatform:postgres"


def test_build_assertion_custom():
    doc = AssertionDoc.model_validate(
        {
            "kind": "ASSERTION",
            "id": "id8",
            "assertion": {
                "type": "CUSTOM",
                "entityUrn": "urn:li:dataset:(urn:li:dataPlatform:postgres,x,PROD)",
                "customType": "GREAT_EXPECTATIONS",
                "logic": "expect_column_values_to_not_be_null(patient_id)",
            },
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    wus = list(build_assertion(doc, index, report))
    aspect = wus[0].metadata.aspect
    assert aspect.customAssertion.type == "GREAT_EXPECTATIONS"
    assert "not_be_null" in aspect.customAssertion.logic


def test_build_assertion_emits_note_and_actions():
    doc = AssertionDoc.model_validate(
        {
            "kind": "ASSERTION",
            "id": "id9",
            "assertion": {
                "type": "FRESHNESS",
                "entityUrn": "urn:li:dataset:(urn:li:dataPlatform:postgres,x,PROD)",
            },
            "assertionNote": "Last run failed due to a warehouse outage",
            "assertionActions": {"onFailure": [{"type": "RAISE_INCIDENT"}]},
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    wus = list(build_assertion(doc, index, report))
    note = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "AssertionNoteClass")
    assert note.content == "Last run failed due to a warehouse outage"
    actions = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "AssertionActionsClass"
    )
    assert actions.onFailure[0].type == "RAISE_INCIDENT"


def test_build_assertion_reports_dangling_tag():
    doc = AssertionDoc.model_validate(
        {
            "kind": "ASSERTION",
            "id": "id6",
            "tags": ["unknown"],
            "assertion": {
                "type": "FRESHNESS",
                "entityUrn": "urn:li:dataset:(urn:li:dataPlatform:postgres,x,PROD)",
            },
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()
    list(build_assertion(doc, index, report))
    assert len(report.dangling_references) == 1


def test_build_query_emits_properties_and_subjects():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = QueryDoc.model_validate(
        {
            "kind": "QUERY",
            "id": "q_patients_actifs",
            "name": "Patients actifs",
            "description": "Liste des patients actifs",
            "statement": "select * from ehr_public_patient where actif",
            "language": "SQL",
            "source": "MANUAL",
            "subjects": [
                {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"},
                {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD", "fieldPath": "nom"},
            ],
            "subTypes": "View query",
        }
    )

    wus = list(build_query(doc, index, report))
    assert not report.dangling_references
    assert wus[0].metadata.entityUrn == "urn:li:query:q_patients_actifs"

    props = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "QueryPropertiesClass"
    )
    assert props.statement.value == "select * from ehr_public_patient where actif"
    assert props.name == "Patients actifs"

    subjects = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "QuerySubjectsClass"
    )
    assert subjects.subjects[0].entity == "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"
    assert subjects.subjects[1].entity == (
        "urn:li:schemaField:(urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD),nom)"
    )

    subtypes = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "SubTypesClass"
    )
    assert subtypes.typeNames == ["View query"]


def test_build_query_without_subjects_emits_no_subjects_aspect():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = QueryDoc.model_validate(
        {"kind": "QUERY", "id": "q1", "statement": "select 1"}
    )

    wus = list(build_query(doc, index, report))
    aspect_names = {wu.metadata.aspect.__class__.__name__ for wu in wus}
    assert "QuerySubjectsClass" not in aspect_names


def test_build_incident_emits_info_and_notes():
    repo = ParsedRepository()
    repo.tags.append(TagDoc(kind="TAG", name="pii"))
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = IncidentDoc.model_validate(
        {
            "kind": "INCIDENT",
            "id": "inc-patient-freshness",
            "type": "FRESHNESS",
            "title": "Patient table late",
            "description": "The patient table missed its 08:00 refresh window",
            "priority": 1,
            "entities": ["urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"],
            "status": {"state": "ACTIVE", "stage": "TRIAGE", "message": "Investigating warehouse outage"},
            "assignees": ["datahub"],
            "source": {"type": "ASSERTION_FAILURE", "sourceUrn": "urn:li:assertion:ehr-patient-freshness-check"},
            "startedAt": 1830297600000,
            "notes": ["Warehouse outage confirmed at 08:05"],
            "tags": ["pii"],
        }
    )

    wus = list(build_incident(doc, index, report))
    assert not report.dangling_references
    assert wus[0].metadata.entityUrn == "urn:li:incident:inc-patient-freshness"

    info = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "IncidentInfoClass")
    assert info.type == "FRESHNESS"
    assert info.title == "Patient table late"
    assert info.status.stage == "TRIAGE"
    assert info.assignees[0].actor == "urn:li:corpuser:datahub"
    assert info.source.sourceUrn == "urn:li:assertion:ehr-patient-freshness-check"

    notes = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "IncidentNotesClass")
    assert notes.notes[0].message == "Warehouse outage confirmed at 08:05"

    tags = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "GlobalTagsClass")
    assert tags.tags[0].tag == "urn:li:tag:pii"


def test_build_incident_defaults_status_and_reports_dangling_tag():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = IncidentDoc.model_validate(
        {
            "kind": "INCIDENT",
            "id": "inc2",
            "type": "OPERATIONAL",
            "entities": ["urn:li:dataset:(urn:li:dataPlatform:postgres,x,PROD)"],
            "tags": ["unknown-tag"],
        }
    )

    wus = list(build_incident(doc, index, report))
    info = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "IncidentInfoClass")
    assert info.status.state == "ACTIVE"
    assert len(report.dangling_references) == 1


def test_build_document_native_emits_document_info_and_common_aspects():
    repo = ParsedRepository()
    repo.tags.append(TagDoc(kind="TAG", name="pii"))
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DocumentDoc.model_validate(
        {
            "kind": "DOCUMENT",
            "id": "runbook_patient",
            "title": "Runbook - reprise de la table patient",
            "text": "## Etapes\n1. Verifier le job",
            "subTypes": "Runbook",
            "relatedAssets": ["urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"],
            "tags": ["pii"],
            "owners": {"owner": "datahub", "type": "TECHNICAL_OWNER"},
            "links": [{"url": "https://wiki.example.org/runbooks/patient", "description": "Runbook source"}],
        }
    )

    wus = list(build_document(doc, index, report))
    assert not report.dangling_references
    assert wus[0].metadata.entityUrn == "urn:li:document:runbook_patient"

    aspect_names = {wu.metadata.aspect.__class__.__name__ for wu in wus}
    assert {"DocumentInfoClass", "SubTypesClass", "GlobalTagsClass", "OwnershipClass", "InstitutionalMemoryClass"} <= aspect_names

    info = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "DocumentInfoClass")
    assert info.title == "Runbook - reprise de la table patient"
    assert info.contents.text == "## Etapes\n1. Verifier le job"
    assert info.source.sourceType == "NATIVE"
    assert info.relatedAssets[0].asset == (
        "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"
    )
    # created/lastModified must be pinned to the epoch for golden-file determinism.
    assert info.created.time == 0
    assert info.lastModified.time == 0


def test_build_document_external_requires_platform():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DocumentDoc.model_validate(
        {
            "kind": "DOCUMENT",
            "id": "external_doc",
            "title": "External runbook",
            "externalUrl": "https://wiki.example.org/runbooks/patient",
        }
    )

    with pytest.raises(ValueError, match="missing 'platform'"):
        list(build_document(doc, index, report))


def test_build_document_external_emits_external_source():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DocumentDoc.model_validate(
        {
            "kind": "DOCUMENT",
            "id": "external_doc",
            "title": "External runbook",
            "platform": "confluence",
            "externalUrl": "https://wiki.example.org/runbooks/patient",
            "externalId": "12345",
        }
    )

    wus = list(build_document(doc, index, report))
    info = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "DocumentInfoClass")
    assert info.source.sourceType == "EXTERNAL"
    assert info.source.externalUrl == "https://wiki.example.org/runbooks/patient"
    assert info.source.externalId == "12345"


def test_build_document_resolves_parent_and_related_documents():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DocumentDoc.model_validate(
        {
            "kind": "DOCUMENT",
            "id": "runbook_patient_detail",
            "title": "Runbook patient - detail",
            "text": "...",
            "parentDocument": "runbook_patient",
            "relatedDocuments": ["runbook_encounter"],
        }
    )

    wus = list(build_document(doc, index, report))
    info = next(wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "DocumentInfoClass")
    assert info.parentDocument.document == "urn:li:document:runbook_patient"
    assert info.relatedDocuments[0].document == "urn:li:document:runbook_encounter"


def test_build_document_native_without_text_raises():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DocumentDoc.model_validate({"kind": "DOCUMENT", "id": "no_text", "title": "No text"})

    with pytest.raises(ValueError, match="requires 'text'"):
        list(build_document(doc, index, report))


def test_build_raw_aspect_dataset_profile():
    doc = RawAspectDoc.model_validate(
        {
            "aspectName": "DATASET_PROFILE",
            "dataset": {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"},
            "timestampMillis": 1777662127622,
            "rowCount": 1480100,
            "columnCount": 12,
            "sizeInBytes": 311681024,
            "fieldProfiles": [
                {
                    "fieldPath": "sexe",
                    "uniqueCount": 2,
                    "nullCount": 38,
                    "distinctValueFrequencies": [
                        {"value": "m", "frequency": 740720},
                        {"value": "f", "frequency": 739342},
                    ],
                }
            ],
        }
    )
    wus = list(build_raw_aspect(doc))
    assert wus[0].metadata.entityUrn == "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"
    aspect = wus[0].metadata.aspect
    assert aspect.rowCount == 1480100
    assert aspect.fieldProfiles[0].distinctValueFrequencies[0].value == "m"


def test_build_raw_aspect_rejects_unsupported_aspect_name():
    doc = RawAspectDoc.model_validate(
        {"aspectName": "SOME_UNKNOWN_ASPECT", "dataset": {"platform": "x", "name": "y", "env": "PROD"}}
    )
    with pytest.raises(ValueError, match="Unsupported raw aspectName"):
        list(build_raw_aspect(doc))


def test_build_raw_aspect_requires_entity_reference():
    doc = RawAspectDoc.model_validate({"aspectName": "DATASET_PROFILE", "timestampMillis": 1})
    with pytest.raises(ValueError, match="missing a 'dataset:' entity reference"):
        list(build_raw_aspect(doc))


def test_build_raw_aspect_operation_uses_dataset_reference():
    doc = RawAspectDoc.model_validate(
        {
            "aspectName": "OPERATION",
            "dataset": {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"},
            "timestampMillis": 1777593600000,
            "lastUpdatedTimestamp": 1777593000000,
            "operationType": "CUSTOM",
            "customOperationType": "QUALITY_CHECK",
            "sourceType": "DATA_PROCESS",
            "numAffectedRows": 982400,
            "actor": "quality-bot",
            "affectedDatasets": [{"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"}],
            "customProperties": {"checkType": "completeness"},
        }
    )
    wus = list(build_raw_aspect(doc))
    aspect = wus[0].metadata.aspect
    assert aspect.operationType == "CUSTOM"
    assert aspect.affectedDatasets == [
        "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"
    ]
    # `actor` is schema-typed as a URN by DataHub; a bare name here crashes
    # AutoMaterializeReferencedTagsTermsProcessor at ingestion time with
    # "urns must start with urn:li:" if not converted.
    assert aspect.actor == "urn:li:corpuser:quality-bot"


def test_build_raw_aspect_operation_without_actor_leaves_it_none():
    doc = RawAspectDoc.model_validate(
        {
            "aspectName": "OPERATION",
            "dataset": {"platform": "postgres", "name": "x", "env": "PROD"},
            "timestampMillis": 1,
            "lastUpdatedTimestamp": 1,
            "operationType": "INSERT",
        }
    )
    wus = list(build_raw_aspect(doc))
    assert wus[0].metadata.aspect.actor is None


def test_build_raw_aspect_assertion_run_event_uses_assertion_urn_reference():
    doc = RawAspectDoc.model_validate(
        {
            "aspectName": "ASSERTION_RUN_EVENT",
            "timestampMillis": 1779443737556,
            "assertionUrn": "urn:li:assertion:ehr-patient-freshness-check-1",
            "asserteeUrn": "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)",
            "runId": "urn:li:assertion:ehr-patient-freshness-check-1:1779443737556",
            "result": {"type": "SUCCESS", "nativeResults": {"threshold_hours": "24"}},
        }
    )
    wus = list(build_raw_aspect(doc))
    assert wus[0].metadata.entityUrn == "urn:li:assertion:ehr-patient-freshness-check-1"
    aspect = wus[0].metadata.aspect
    assert aspect.status == "COMPLETE"  # defaulted, not present in source
    assert aspect.result.type == "SUCCESS"


def test_build_raw_aspect_data_process_instance_run_event_uses_instance_urn_reference():
    doc = RawAspectDoc.model_validate(
        {
            "aspectName": "DATA_PROCESS_INSTANCE_RUN_EVENT",
            "dataProcessInstanceUrn": "urn:li:dataProcessInstance:airflow_x__2026-05-25T08:00:00",
            "timestampMillis": 1779696180000,
            "status": "COMPLETE",
            "attempt": 1,
            "durationMillis": 180000,
            "result": {"type": "SUCCESS", "nativeResultType": "airflow"},
        }
    )
    wus = list(build_raw_aspect(doc))
    assert wus[0].metadata.entityUrn == "urn:li:dataProcessInstance:airflow_x__2026-05-25T08:00:00"
    aspect = wus[0].metadata.aspect
    assert aspect.result.nativeResultType == "airflow"


def test_build_raw_aspect_dataset_usage_statistics():
    doc = RawAspectDoc.model_validate(
        {
            "aspectName": "DATASET_USAGE_STATISTICS",
            "dataset": {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"},
            "timestampMillis": 1778180527622,
            "uniqueUserCount": 5,
            "totalSqlQueries": 624,
            "userCounts": [{"user": "urn:li:corpuser:etl-pipeline", "count": 298}],
            "fieldCounts": [{"fieldPath": "patient_id", "count": 624}],
        }
    )
    wus = list(build_raw_aspect(doc))
    aspect = wus[0].metadata.aspect
    assert aspect.userCounts[0].user == "urn:li:corpuser:etl-pipeline"
    assert aspect.fieldCounts[0].fieldPath == "patient_id"
