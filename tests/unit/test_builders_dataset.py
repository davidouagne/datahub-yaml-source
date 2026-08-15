from datahub_yaml_source.builders.dataset import build_dataset
from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import ApplicationDoc, ContainerDoc, DatasetDoc, DomainDoc, GlossaryTermDoc, TagDoc
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _repository_with_known_references():
    repo = ParsedRepository()
    repo.tags.append(TagDoc(kind="TAG", name="pii"))
    repo.tags.append(TagDoc(kind="TAG", name="fhir-r4"))
    repo.glossary_terms.append(GlossaryTermDoc(kind="GLOSSARY_TERM", id="donnees-patient.patient", name="Patient"))
    repo.domains.append(DomainDoc(kind="DOMAIN", id="3667192a0a19c51419efe99aa865c1ba", name="Identite patient"))
    repo.containers.append(
        ContainerDoc.model_validate(
            {
                "kind": "CONTAINER",
                "platform": "postgres",
                "database": "ehr",
                "schema": "public",
                "env": "PROD",
                "name": "public",
                "subTypes": "Schema",
            }
        )
    )
    return repo


def _dataset_doc():
    return DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "ehr_public_patient",
            "platform": "postgres",
            "env": "PROD",
            "description": "Patient data",
            "container": {"platform": "postgres", "database": "ehr", "schema": "public", "env": "PROD"},
            "schema": {
                "fields": [
                    {"fieldPath": "patient_id", "type": "number", "nativeDataType": "BIGSERIAL", "partOfKey": True},
                    {"fieldPath": "nom", "type": "string", "nativeDataType": "VARCHAR(255)", "partOfKey": False},
                ],
            },
            "subTypes": ["Table"],
            "tags": ["pii"],
            "glossaryTerms": ["donnees-patient.patient"],
            "owners": {"owner": "datahub", "type": "TECHNICAL_OWNER"},
            "domains": "3667192a0a19c51419efe99aa865c1ba",
        }
    )


def test_build_dataset_emits_expected_aspects():
    repo = _repository_with_known_references()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    wus = list(build_dataset(_dataset_doc(), index, report))
    assert not report.dangling_references

    aspects_by_name = {wu.metadata.aspect.__class__.__name__: wu.metadata.aspect for wu in wus}
    assert wus[0].metadata.entityUrn == "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"

    schema_metadata = aspects_by_name["SchemaMetadataClass"]
    assert [f.fieldPath for f in schema_metadata.fields] == ["patient_id", "nom"]
    assert schema_metadata.fields[0].isPartOfKey is True

    tags = aspects_by_name["GlobalTagsClass"]
    assert tags.tags[0].tag == "urn:li:tag:pii"

    terms = aspects_by_name["GlossaryTermsClass"]
    assert terms.terms[0].urn == "urn:li:glossaryTerm:donnees-patient.patient"

    domains = aspects_by_name["DomainsClass"]
    assert domains.domains == ["urn:li:domain:3667192a0a19c51419efe99aa865c1ba"]

    container = aspects_by_name["ContainerClass"]
    assert container.container is not None


def test_build_dataset_with_foreign_keys_builds_schema_field_urns():
    repo = _repository_with_known_references()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "ehr_public_actes",
            "platform": "postgres",
            "env": "PROD",
            "schema": {
                "fields": [{"fieldPath": "acte_id", "type": "number", "partOfKey": True}],
                "foreignKeys": [
                    {
                        "name": "fk_actes_patient",
                        "sourceFields": [
                            {"platform": "postgres", "name": "ehr_public_actes", "env": "PROD", "fieldPath": "patient_id"}
                        ],
                        "foreignDataset": {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD"},
                        "foreignFields": [
                            {"platform": "postgres", "name": "ehr_public_patient", "env": "PROD", "fieldPath": "patient_id"}
                        ],
                    }
                ],
            },
        }
    )

    wus = list(build_dataset(doc, index, report))
    schema_metadata = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "SchemaMetadataClass"
    )
    fk = schema_metadata.foreignKeys[0]
    assert fk.foreignDataset == "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD)"
    assert fk.sourceFields[0].endswith(",patient_id)")


def test_build_dataset_with_upstream_lineage_and_fine_grained():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "transform_layer_fhir_condition",
            "platform": "dbt",
            "env": "PROD",
            "upstreamLineage": {
                "upstreams": [{"dataset": {"platform": "duckdb", "name": "warehouse_staging_stg_ehr__diagnostics", "env": "PROD"}}],
                "fineGrainedLineages": [
                    {
                        "upstream": {"platform": "duckdb", "name": "warehouse_staging_stg_ehr__diagnostics", "env": "PROD", "fieldPath": "diagnostic_id"},
                        "downstream": {"platform": "dbt", "name": "transform_layer_fhir_condition", "env": "PROD", "fieldPath": "identifier_diag_value"},
                        "operation": "TRANSFORM",
                        "confidence": 1.0,
                    }
                ],
            },
        }
    )

    wus = list(build_dataset(doc, index, report))
    upstream_lineage = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "UpstreamLineageClass"
    )
    assert len(upstream_lineage.upstreams) == 1
    assert upstream_lineage.upstreams[0].dataset == "urn:li:dataset:(urn:li:dataPlatform:duckdb,warehouse_staging_stg_ehr__diagnostics,PROD)"
    assert len(upstream_lineage.fineGrainedLineages) == 1
    fgl = upstream_lineage.fineGrainedLineages[0]
    assert fgl.transformOperation == "TRANSFORM"
    assert fgl.upstreams[0].endswith(",diagnostic_id)")
    assert fgl.downstreams[0].endswith(",identifier_diag_value)")


def test_build_dataset_upstream_lineage_handles_constant_operation_without_upstream():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "omop_public_visit_occurrence",
            "platform": "postgres",
            "upstreamLineage": {
                "upstreams": [],
                "fineGrainedLineages": [
                    {
                        "downstream": {
                            "platform": "postgres",
                            "name": "omop_public_visit_occurrence",
                            "env": "PROD",
                            "fieldPath": "visit_type_concept_id",
                        },
                        "operation": "CONSTANT",
                        "confidence": 1.0,
                    }
                ],
            },
        }
    )

    wus = list(build_dataset(doc, index, report))
    upstream_lineage = next(
        wu.metadata.aspect for wu in wus if wu.metadata.aspect.__class__.__name__ == "UpstreamLineageClass"
    )
    fgl = upstream_lineage.fineGrainedLineages[0]
    assert fgl.upstreams == []
    assert fgl.transformOperation == "CONSTANT"


def test_build_dataset_reports_dangling_tag_domain_and_container_but_still_emits():
    repo = ParsedRepository()  # empty: nothing declared
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "x",
            "platform": "postgres",
            "tags": ["unknown-tag"],
            "domains": "unknown-domain",
            "container": {"platform": "postgres", "database": "unknown-db", "env": "PROD"},
        }
    )

    wus = list(build_dataset(doc, index, report))
    assert len(wus) > 0
    assert len(report.dangling_references) == 3


def test_build_dataset_emits_view_properties_and_applications_without_inferring_lineage():
    repo = ParsedRepository()
    repo.applications.append(ApplicationDoc(kind="APPLICATION", id="ORBIS", name="ORBIS"))
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "aph_pha_recup_prescr_v3_hc1v2",
            "platform": "oracle",
            "env": "PROD",
            "subTypes": "View",
            "applications": ["ORBIS"],
            "viewProperties": {
                "viewLogic": "SELECT patient_id FROM medication",
                "viewLanguage": "SQL",
                "materialized": False,
            },
        }
    )

    wus = list(build_dataset(doc, index, report))
    assert not report.dangling_references

    aspects_by_name = {wu.metadata.aspect.__class__.__name__: wu.metadata.aspect for wu in wus}

    view_properties = aspects_by_name["ViewPropertiesClass"]
    assert view_properties.viewLogic == "SELECT patient_id FROM medication"
    assert view_properties.viewLanguage == "SQL"
    assert view_properties.materialized is False

    applications = aspects_by_name["ApplicationsClass"]
    assert applications.applications == ["urn:li:application:ORBIS"]

    # No upstreamLineage was declared in the YAML, and the SQL in viewLogic must
    # never be auto-parsed by the SDK's sqlglot integration (parse_view_lineage=False)
    # -- the connector's lineage story is "fully declared in YAML", never inferred.
    assert "UpstreamLineageClass" not in aspects_by_name


def test_build_dataset_reports_dangling_application_but_still_emits():
    repo = ParsedRepository()  # empty: ORBIS not declared
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "x",
            "platform": "oracle",
            "applications": ["ORBIS"],
        }
    )

    wus = list(build_dataset(doc, index, report))
    assert len(wus) > 0
    assert len(report.dangling_references) == 1
    assert "ORBIS" in report.dangling_references[0]


def test_build_dataset_emits_column_level_metadata():
    repo = _repository_with_known_references()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "ehr_public_patient",
            "platform": "postgres",
            "env": "PROD",
            "schema": {
                "fields": [
                    {
                        "fieldPath": "nom",
                        "type": "string",
                        "tags": ["pii"],
                        "glossaryTerms": ["donnees-patient.patient"],
                        "deprecation": {"deprecated": True, "note": "Remplacée par nom_normalise"},
                    },
                    {"fieldPath": "patient_id", "type": "number"},
                ],
            },
        }
    )

    wus = list(build_dataset(doc, index, report))
    assert not report.dangling_references

    field_urn = "urn:li:schemaField:(urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD),nom)"
    field_wus = [wu for wu in wus if wu.metadata.entityUrn == field_urn]
    aspect_names = {wu.metadata.aspect.__class__.__name__ for wu in field_wus}
    assert aspect_names == {"GlobalTagsClass", "GlossaryTermsClass", "DeprecationClass"}

    tags_aspect = next(wu.metadata.aspect for wu in field_wus if wu.metadata.aspect.__class__.__name__ == "GlobalTagsClass")
    assert tags_aspect.tags[0].tag == "urn:li:tag:pii"

    # The second column has no common-metadata fields set -- no workunits for it at all.
    other_field_urn = "urn:li:schemaField:(urn:li:dataset:(urn:li:dataPlatform:postgres,ehr_public_patient,PROD),patient_id)"
    assert not [wu for wu in wus if wu.metadata.entityUrn == other_field_urn]


def test_build_dataset_reports_dangling_reference_naming_the_column():
    repo = ParsedRepository()  # empty: nothing declared
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = DatasetDoc.model_validate(
        {
            "kind": "DATASET",
            "name": "x",
            "platform": "postgres",
            "schema": {
                "fields": [{"fieldPath": "ssn", "type": "string", "tags": ["unknown-tag"]}],
            },
        }
    )

    list(build_dataset(doc, index, report))
    assert len(report.dangling_references) == 1
    assert "field 'ssn'" in report.dangling_references[0]
    assert "unknown-tag" in report.dangling_references[0]
