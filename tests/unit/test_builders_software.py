"""Builder tests for the software/AI catalog family (Phase 5C): REPOSITORY, API,
AGENT_SKILL, AI_AGENT, SERVICE."""

from datahub_yaml_source.builders.software import (
    build_agent_skill,
    build_ai_agent,
    build_api,
    build_repository,
    build_service,
)
from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.models import (
    AgentSkillDoc,
    AIAgentDoc,
    ApiDoc,
    RepositoryDoc,
    ServiceDoc,
    TagDoc,
)
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _repo_with_known_tag() -> ParsedRepository:
    repo = ParsedRepository()
    repo.tags.append(TagDoc(kind="TAG", name="pii"))
    return repo


def test_build_repository_emits_properties_source_lineage_and_platform_instance():
    repo = _repo_with_known_tag()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = RepositoryDoc.model_validate(
        {
            "kind": "REPOSITORY",
            "id": "aphp-pathling",
            "name": "aphp/pathling",
            "defaultBranch": "main",
            "languages": ["Java"],
            "license": "Apache-2.0",
            "source": {
                "externalUrl": "https://gitlab.example.org/ds/pathling",
                "externalId": "1234",
            },
            "forkOf": "upstream-pathling",
            "platform": "gitlab",
            "instance": "aphp-prod",
            "tags": ["pii"],
        }
    )

    wus = list(build_repository(doc, index, report))
    assert not report.dangling_references
    assert wus[0].metadata.entityUrn == "urn:li:repository:aphp-pathling"

    props = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "RepositoryPropertiesClass"
    )
    assert props.name == "aphp/pathling"
    assert props.defaultBranch == "main"

    source = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "RepositorySourceClass"
    )
    assert source.externalId == "1234"

    lineage = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "RepositoryLineageClass"
    )
    assert lineage.forkOf == "urn:li:repository:upstream-pathling"

    dpi = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "DataPlatformInstanceClass"
    )
    assert dpi.platform == "urn:li:dataPlatform:gitlab"
    assert dpi.instance == "urn:li:dataPlatformInstance:(urn:li:dataPlatform:gitlab,aphp-prod)"

    assert any(wu.metadata.aspect.__class__.__name__ == "GlobalTagsClass" for wu in wus)


def test_build_api_resolves_source_repository_and_emits_rest_and_signature():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = ApiDoc.model_validate(
        {
            "kind": "API",
            "id": "fhir-patient-search-api",
            "name": "Recherche de patients FHIR",
            "sourceRepository": "aphp-pathling",
            "restApi": {"method": "GET", "path": "/Patient"},
            "signature": {"schemaDefinition": "OpenAPI 3.0"},
        }
    )

    wus = list(build_api(doc, index, report))
    assert wus[0].metadata.entityUrn == "urn:li:api:fhir-patient-search-api"

    props = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "ApiPropertiesClass"
    )
    assert props.sourceRepository == "urn:li:repository:aphp-pathling"

    rest = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "RestApiPropertiesClass"
    )
    assert rest.method == "GET"
    assert rest.path == "/Patient"

    signature = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "ApiSignatureClass"
    )
    assert signature.schemaDefinition == "OpenAPI 3.0"


def test_build_agent_skill_resolves_source_repository_urn():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = AgentSkillDoc.model_validate(
        {
            "kind": "AGENT_SKILL",
            "id": "fhir-query-skill",
            "name": "Interrogation FHIR",
            "requiredTools": ["fhir-patient-search-api"],
            "sourceRepository": {"repositoryUrn": "aphp-pathling", "path": "skills/fhir_query"},
        }
    )

    wus = list(build_agent_skill(doc, index, report))
    assert wus[0].metadata.entityUrn == "urn:li:agentSkill:fhir-query-skill"

    info = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "AgentSkillInfoClass"
    )
    assert info.requiredTools == ["urn:li:api:fhir-patient-search-api"]
    assert info.sourceRepository.repositoryUrn == "urn:li:repository:aphp-pathling"
    assert info.sourceRepository.path == "skills/fhir_query"


def test_build_ai_agent_emits_deterministic_audit_stamp_and_dependencies():
    repo = ParsedRepository()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = AIAgentDoc.model_validate(
        {
            "kind": "AI_AGENT",
            "id": "cohort-builder-agent",
            "name": "Agent de constitution de cohorte",
            "source": {"type": "NATIVE"},
            "dependencies": {
                "skills": ["fhir-query-skill"],
                "models": [{"platform": "mlflow", "name": "readmission_risk_v3", "env": "PROD"}],
                "tools": ["fhir-patient-search-api"],
            },
            "displayProperties": {"colorHex": "#2E86AB"},
        }
    )

    wus = list(build_ai_agent(doc, index, report))
    assert wus[0].metadata.entityUrn == "urn:li:aiAgent:cohort-builder-agent"

    info = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "AIAgentInfoClass"
    )
    assert info.created.time == 0
    assert info.lastModified.time == 0
    assert info.source.type == "NATIVE"

    deps = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "AIAgentDependenciesClass"
    )
    assert deps.skills == ["urn:li:agentSkill:fhir-query-skill"]
    assert deps.models == ["urn:li:mlModel:(urn:li:dataPlatform:mlflow,readmission_risk_v3,PROD)"]
    assert deps.tools == ["urn:li:api:fhir-patient-search-api"]

    display = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "DisplayPropertiesClass"
    )
    assert display.colorHex == "#2E86AB"


def test_build_service_only_permits_tags_owners_subtypes_and_wraps_raw_spec():
    repo = _repo_with_known_tag()
    index = ReferenceIndex(repo)
    report = YamlSourceReport()

    doc = ServiceDoc.model_validate(
        {
            "kind": "SERVICE",
            "id": "pathling-fhir-server",
            "displayName": "Serveur FHIR Pathling",
            "lifecycle": "PRODUCTION",
            "apis": ["fhir-patient-search-api"],
            "sourceRepository": "aphp-pathling",
            "mcpServer": {"url": "https://mcp.example.org/pathling", "transport": "HTTP"},
            "definition": {"format": "OPENAPI", "rawSpec": "openapi: 3.0.0", "version": "1.0"},
            "properties": {"cluster": "eds", "replicas": 3},
            "tags": ["pii"],
            "owners": {"owner": "datahub", "type": "TECHNICAL_OWNER"},
        }
    )
    # `domains:`/`glossaryTerms:` aren't valid fields on SERVICE -- verify the
    # registry-driven restriction actually holds at the model level.
    assert "domains" not in ServiceDoc.model_fields
    assert "glossaryTerms" not in ServiceDoc.model_fields

    wus = list(build_service(doc, index, report))
    assert wus[0].metadata.entityUrn == "urn:li:service:pathling-fhir-server"

    props = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "ServicePropertiesClass"
    )
    assert props.apis == ["urn:li:api:fhir-patient-search-api"]
    assert props.sourceRepository == "urn:li:repository:aphp-pathling"
    assert props.lifecycle == "PRODUCTION"
    # `replicas: 3` (int) must be coerced to `"3"` -- customProperties is Dict[str, str].
    assert props.customProperties == {"cluster": "eds", "replicas": "3"}

    mcp_server = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "McpServerPropertiesClass"
    )
    assert mcp_server.url == "https://mcp.example.org/pathling"

    definition = next(
        wu.metadata.aspect
        for wu in wus
        if wu.metadata.aspect.__class__.__name__ == "ServiceDefinitionClass"
    )
    assert definition.rawSpec.blob == "openapi: 3.0.0"

    assert any(wu.metadata.aspect.__class__.__name__ == "OwnershipClass" for wu in wus)
    assert any(wu.metadata.aspect.__class__.__name__ == "GlobalTagsClass" for wu in wus)
