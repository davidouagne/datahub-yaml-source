import pytest

from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import (
    ContainerDoc,
    DataFlowJobRef,
    DataFlowRef,
    DatasetRef,
    DomainDoc,
    TagDoc,
)
from datahub_yaml_source.urns import (
    ReferenceIndex,
    container_key,
    container_urn,
    data_flow_urn,
    data_job_urn,
    dataset_urn,
    document_urn,
    domain_urn,
    glossary_term_urn,
    owner_urn,
    tag_urn,
)


def test_dataset_urn_without_platform_instance():
    ref = DatasetRef(platform="postgres", name="ehr.public.patient", env="PROD")
    assert (
        dataset_urn(ref) == "urn:li:dataset:(urn:li:dataPlatform:postgres,ehr.public.patient,PROD)"
    )


def test_dataset_urn_with_platform_instance():
    ref = DatasetRef(platform="postgres", name="t", env="PROD", instance="prod-pg")
    urn = dataset_urn(ref)
    assert "prod-pg" in urn


def test_container_key_carries_schema_when_present():
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
    key = container_key(doc)
    assert key.db_schema == "public"


def test_container_key_has_no_schema_when_absent():
    doc = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "dbt",
            "database": "transform_layer",
            "env": "PROD",
            "name": "Transform layer",
        }
    )
    key = container_key(doc)
    assert not hasattr(key, "db_schema")


def test_container_key_requires_database():
    doc = ContainerDoc.model_validate(
        {"kind": "CONTAINER", "platform": "postgres", "env": "PROD", "name": "x"}
    )
    with pytest.raises(ValueError, match="missing 'database'"):
        container_key(doc)


def test_container_urn_matches_known_production_guid_database_level():
    """Regression pin: confirmed against a real container already registered
    in a production DataHub instance (`postgres` / `semantic_layer` database,
    no schema, no explicit `instance`)."""
    doc = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "semantic_layer",
            "env": "PROD",
            "name": "Semantic layer",
        }
    )
    assert container_urn(doc) == "urn:li:container:f1c5e2905eec7e68436fae294290422a"


def test_container_urn_matches_known_production_guid_schema_level():
    """Regression pin: confirmed against the real, already-registered `public`
    schema container under the `semantic_layer` database above."""
    doc = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "semantic_layer",
            "schema": "public",
            "env": "PROD",
            "name": "public",
        }
    )
    assert container_urn(doc) == "urn:li:container:fd5e706c8acf479b41d77b2adacdb4b1"


def test_container_urn_ignores_instance_entirely():
    """`instance` is confirmed to never affect the container GUID in this
    system (it's used for the separate `dataPlatformInstance` aspect, not the
    container's identity) -- so a dataset's `container:` reference that
    happens to declare `instance: postgres` must resolve to the *same* URN as
    the schema container's own declaration, which declares no instance at all.
    This is the exact bug report this test locks in: a dataset referencing
    `platform=postgres, instance=postgres, database=semantic_layer,
    schema=public` must link to the real, already-existing schema container.
    """
    without_instance = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "semantic_layer",
            "schema": "public",
            "env": "PROD",
            "name": "public",
        }
    )
    with_instance = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "instance": "postgres",
            "database": "semantic_layer",
            "schema": "public",
            "env": "PROD",
            "name": "public",
        }
    )
    assert container_urn(with_instance) == container_urn(without_instance)
    assert container_urn(with_instance) == "urn:li:container:fd5e706c8acf479b41d77b2adacdb4b1"


def test_container_urn_ignores_env_like_default_sdk_behavior():
    # DataHub's default ContainerKey.guid_dict() excludes `env` from the hash
    # entirely, so these two must collide (this is expected/desired: it's why
    # the known-good GUID above doesn't depend on env at all).
    prod = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "ehr",
            "env": "PROD",
            "name": "EHR",
        }
    )
    dev = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "ehr",
            "env": "DEV",
            "name": "EHR",
        }
    )
    assert container_urn(prod) == container_urn(dev)


def test_container_urn_is_deterministic_for_same_key():
    doc = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "ehr",
            "env": "PROD",
            "name": "EHR",
        }
    )
    assert container_urn(doc) == container_urn(doc)


def test_tag_domain_glossary_term_urns_are_stable_and_passthrough_full_urns():
    assert tag_urn("pii") == "urn:li:tag:pii"
    assert tag_urn("urn:li:tag:pii") == "urn:li:tag:pii"
    assert domain_urn("abc123") == "urn:li:domain:abc123"
    assert glossary_term_urn("fhir:Patient") == "urn:li:glossaryTerm:fhir:Patient"


def test_document_urn_is_stable_and_passes_through_full_urns():
    assert document_urn("runbook_patient") == "urn:li:document:runbook_patient"
    assert document_urn("urn:li:document:runbook_patient") == "urn:li:document:runbook_patient"


def test_owner_urn_builds_corpuser_unless_already_a_urn():
    assert owner_urn("datahub") == "urn:li:corpuser:datahub"
    assert (
        owner_urn("urn:li:corpGroup:eds-data-engineering")
        == "urn:li:corpGroup:eds-data-engineering"
    )


def test_data_flow_and_data_job_urns():
    flow_ref = DataFlowRef(orchestrator="airflow", flowId="ehr_to_raw", cluster="PROD")
    assert data_flow_urn(flow_ref) == "urn:li:dataFlow:(airflow,ehr_to_raw,PROD)"

    job_ref = DataFlowJobRef(
        orchestrator="airflow", flowId="ehr_to_raw", cluster="PROD", jobId="patient_to_raw"
    )
    job_urn = data_job_urn(job_ref)
    assert job_urn.startswith("urn:li:dataJob:")
    assert "patient_to_raw" in job_urn


def test_reference_index_flags_missing_tag_domain_and_container():
    repo = ParsedRepository()
    repo.tags.append(TagDoc(kind="TAG", name="pii"))
    repo.domains.append(DomainDoc(kind="DOMAIN", id="d1", name="Domain 1"))
    repo.containers.append(
        ContainerDoc.model_validate(
            {
                "kind": "CONTAINER",
                "platform": "postgres",
                "database": "ehr",
                "env": "PROD",
                "name": "EHR",
            }
        )
    )
    index = ReferenceIndex(repo)

    assert index.has_tag("pii") is True
    assert index.has_tag("does-not-exist") is False
    assert index.has_domain("d1") is True
    assert index.has_domain("missing") is False

    known_container = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "ehr",
            "env": "PROD",
            "name": "EHR",
        }
    )
    unknown_container = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "other",
            "env": "PROD",
            "name": "Other",
        }
    )
    assert index.has_container(known_container) is True
    assert index.has_container(unknown_container) is False


def test_reference_index_treats_containers_differing_only_by_instance_as_the_same():
    # instance doesn't affect the container URN (see test_container_urn_ignores_instance_entirely),
    # so it must not affect dangling-reference detection either.
    repo = ParsedRepository()
    repo.containers.append(
        ContainerDoc.model_validate(
            {
                "kind": "CONTAINER",
                "platform": "postgres",
                "database": "ehr",
                "env": "PROD",
                "name": "EHR",
            }
        )
    )
    index = ReferenceIndex(repo)

    reference_with_instance = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "instance": "postgres",
            "database": "ehr",
            "env": "PROD",
            "name": "EHR",
        }
    )
    assert index.has_container(reference_with_instance) is True
