from datahub_yaml_source.builders.application import build_application
from datahub_yaml_source.builders.container import build_container, topological_sort_containers
from datahub_yaml_source.builders.domain import build_domain
from datahub_yaml_source.builders.glossary import build_glossary_node, build_glossary_term
from datahub_yaml_source.builders.platform import build_data_platform
from datahub_yaml_source.builders.structured_property import build_structured_property
from datahub_yaml_source.builders.tag import build_tag
from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import (
    ApplicationDoc,
    ContainerDoc,
    DataPlatformDoc,
    DomainDoc,
    GlossaryNodeDoc,
    GlossaryTermDoc,
    StructuredPropertyDoc,
    TagDoc,
)
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _container(name, database, schema=None, parent=None):
    data = {
        "kind": "CONTAINER",
        "platform": "postgres",
        "database": database,
        "env": "PROD",
        "name": name,
        "subTypes": "Schema" if schema else "Database",
    }
    if schema:
        data["schema"] = schema
    if parent:
        data["parentContainer"] = parent
    return ContainerDoc.model_validate(data)


def test_build_data_platform_emits_data_platform_info():
    doc = DataPlatformDoc(kind="DATA_PLATFORM", name="pathling", displayName="Pathling", type="OTHERS")
    wus = list(build_data_platform(doc))
    assert len(wus) == 1
    assert wus[0].metadata.entityUrn == "urn:li:dataPlatform:pathling"
    assert wus[0].metadata.aspect.name == "pathling"


def test_build_tag_emits_tag_entity():
    doc = TagDoc(kind="TAG", name="pii", description="Personally identifiable information")
    wus = list(build_tag(doc))
    urns = {wu.metadata.entityUrn for wu in wus}
    assert "urn:li:tag:pii" in urns


def test_build_domain_emits_domain_properties():
    doc = DomainDoc(kind="DOMAIN", id="abc123", name="Biologie", description="Analyses")
    wus = list(build_domain(doc))
    assert wus[0].metadata.entityUrn == "urn:li:domain:abc123"
    assert wus[0].metadata.aspect.name == "Biologie"


def test_build_application_emits_application_properties():
    doc = ApplicationDoc(kind="APPLICATION", id="ORBIS", name="ORBIS", description="EHR")
    wus = list(build_application(doc))
    assert wus[0].metadata.entityUrn == "urn:li:application:ORBIS"
    assert wus[0].metadata.aspect.name == "ORBIS"


def test_build_glossary_node_and_term_link_parent(monkeypatch):
    repo = ParsedRepository()
    repo.glossary_nodes.append(GlossaryNodeDoc(kind="GLOSSARY_NODE", id="fhir:Resource", name="FHIR Resource"))
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    node_doc = GlossaryNodeDoc(kind="GLOSSARY_NODE", id="fhir:Resource", name="FHIR Resource")
    list(build_glossary_node(node_doc, index, report))

    term_doc = GlossaryTermDoc(
        kind="GLOSSARY_TERM", id="fhir:Patient", name="FHIR Patient", parentNode="fhir:Resource"
    )
    wus = list(build_glossary_term(term_doc, index, report))
    urns = {wu.metadata.entityUrn for wu in wus}
    assert "urn:li:glossaryTerm:fhir:Patient" in urns
    assert report.documents_failed_to_parse == 0
    assert len(report.dangling_references) == 0


def test_build_glossary_term_reports_dangling_parent_node():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    term_doc = GlossaryTermDoc(
        kind="GLOSSARY_TERM", id="fhir:Patient", name="FHIR Patient", parentNode="does:not:exist"
    )
    list(build_glossary_term(term_doc, index, report))

    assert len(report.dangling_references) == 1
    assert "does:not:exist" in report.dangling_references[0]


def test_build_structured_property_maps_type_qualifier_shorthand_to_map():
    doc = StructuredPropertyDoc.model_validate(
        {
            "kind": "STRUCTURED_PROPERTY",
            "qualifiedName": "fr.aphp.panorama.dataProduct",
            "valueType": "urn",
            "cardinality": "SINGLE",
            "typeQualifier": ["urn:li:entityType:datahub.dataProduct"],
            "entityTypes": ["dataProduct"],
        }
    )
    wus = list(build_structured_property(doc))
    aspect = wus[0].metadata.aspect
    assert aspect.typeQualifier == {"allowedTypes": ["urn:li:entityType:datahub.dataProduct"]}
    assert aspect.entityTypes == ["urn:li:entityType:datahub.dataProduct"]
    assert aspect.valueType == "urn:li:dataType:datahub.urn"


def test_build_structured_property_emits_settings_when_present():
    doc = StructuredPropertyDoc.model_validate(
        {
            "kind": "STRUCTURED_PROPERTY",
            "qualifiedName": "fr.aphp.panorama.availability",
            "valueType": "string",
            "entityTypes": ["dataProduct"],
            "settings": {"showInAssetSummary": True, "isHidden": False},
        }
    )
    wus = list(build_structured_property(doc))
    assert len(wus) == 2
    assert wus[1].metadata.aspect.showInAssetSummary is True


def test_topological_sort_orders_parent_before_child():
    database = _container("EHR", "ehr")
    schema = _container(
        "public",
        "ehr",
        schema="public",
        parent={"platform": "postgres", "database": "ehr", "env": "PROD"},
    )
    # Deliberately out of order in the input list.
    ordered = topological_sort_containers([schema, database])
    assert ordered == [database, schema]


def test_topological_sort_handles_container_with_unresolved_parent_without_hanging():
    orphan = _container(
        "orphan_schema",
        "ehr",
        schema="orphan",
        parent={"platform": "postgres", "database": "does_not_exist", "env": "PROD"},
    )
    ordered = topological_sort_containers([orphan])
    assert ordered == [orphan]


def test_build_container_reports_dangling_parent_and_still_emits():
    orphan = _container(
        "orphan_schema",
        "ehr",
        schema="orphan",
        parent={"platform": "postgres", "database": "does_not_exist", "env": "PROD"},
    )
    repo = ParsedRepository()
    repo.containers.append(orphan)
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    wus = list(build_container(orphan, index, report))

    assert len(wus) > 0
    assert len(report.dangling_references) == 1


def test_build_container_with_multiple_owners_emits_full_ownership_aspect():
    doc = ContainerDoc.model_validate(
        {
            "kind": "CONTAINER",
            "platform": "postgres",
            "database": "ehr",
            "env": "PROD",
            "name": "EHR",
            "subTypes": "Database",
            "owners": [
                {"owner": "alice", "type": "TECHNICAL_OWNER"},
                {"owner": "bob", "type": "BUSINESS_OWNER"},
            ],
        }
    )
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    wus = list(build_container(doc, index, report))
    ownership_wus = [wu for wu in wus if wu.metadata.aspect.__class__.__name__ == "OwnershipClass"]
    assert len(ownership_wus) == 1
    assert len(ownership_wus[0].metadata.aspect.owners) == 2
