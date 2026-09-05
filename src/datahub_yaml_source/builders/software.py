"""Builders for the software/AI catalog family: REPOSITORY, API, AGENT_SKILL,
AI_AGENT, SERVICE (Phase 5C).

None of these five have an SDK V2 wrapper (verified: no matching module under
`datahub/sdk/`), so all five are emitted as raw MCPs via `common_aspect_mcps()`
-- the same pattern as QUERY/INCIDENT (Phase 4). Their URNs are a bare id with
no platform component, unlike every dataset-shaped kind in this connector.
"""

from collections.abc import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    AgentSkillInfoClass,
    AIAgentDependenciesClass,
    AIAgentInfoClass,
    AIAgentSourceClass,
    ApiPropertiesClass,
    ApiSignatureClass,
    DisplayPropertiesClass,
    LargeStringClass,
    McpServerPropertiesClass,
    RepositoryLineageClass,
    RepositoryPropertiesClass,
    RepositorySourceClass,
    RestApiPropertiesClass,
    ServiceDefinitionClass,
    ServicePropertiesClass,
    SkillSourceRepositoryClass,
)

from datahub_yaml_source.builders.common import (
    ZERO_AUDIT_STAMP,
    build_data_platform_instance_aspect,
    common_aspect_mcps,
    mcp_workunit,
    stringify_custom_properties,
)
from datahub_yaml_source.models import AgentSkillDoc, AIAgentDoc, ApiDoc, RepositoryDoc, ServiceDoc
from datahub_yaml_source.urns import (
    ReferenceIndex,
    agent_skill_urn,
    ai_agent_urn,
    api_urn,
    ml_model_urn,
    repository_urn,
    service_urn,
)
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def build_repository(
    doc: RepositoryDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"REPOSITORY '{doc.id}'"
    entity_urn = repository_urn(doc.id)

    yield mcp_workunit(
        entity_urn,
        RepositoryPropertiesClass(
            name=doc.name,
            description=doc.description,
            defaultBranch=doc.defaultBranch,
            languages=doc.languages,
            license=doc.license,
            homepageUrl=doc.homepageUrl,
            archived=doc.archived,
        ),
    )
    if doc.source:
        yield mcp_workunit(
            entity_urn,
            RepositorySourceClass(
                externalUrl=doc.source.externalUrl, externalId=doc.source.externalId
            ),
        )
    if doc.forkOf:
        yield mcp_workunit(entity_urn, RepositoryLineageClass(forkOf=repository_urn(doc.forkOf)))

    dpi = build_data_platform_instance_aspect(doc.platform, doc.instance)
    if dpi:
        yield mcp_workunit(entity_urn, dpi)

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)


def build_api(
    doc: ApiDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"API '{doc.id}'"
    entity_urn = api_urn(doc.id)

    yield mcp_workunit(
        entity_urn,
        ApiPropertiesClass(
            name=doc.name,
            description=doc.description,
            externalUrl=doc.externalUrl,
            sourceRepository=repository_urn(doc.sourceRepository) if doc.sourceRepository else None,
        ),
    )
    if doc.restApi:
        yield mcp_workunit(
            entity_urn,
            RestApiPropertiesClass(method=doc.restApi.method, path=doc.restApi.path),
        )
    if doc.signature:
        yield mcp_workunit(
            entity_urn, ApiSignatureClass(schemaDefinition=doc.signature.schemaDefinition)
        )

    dpi = build_data_platform_instance_aspect(doc.platform, doc.instance)
    if dpi:
        yield mcp_workunit(entity_urn, dpi)

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)


def build_agent_skill(
    doc: AgentSkillDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"AGENT_SKILL '{doc.id}'"
    entity_urn = agent_skill_urn(doc.id)

    source_repository = None
    if doc.sourceRepository:
        source_repository = SkillSourceRepositoryClass(
            repositoryUrn=(
                repository_urn(doc.sourceRepository.repositoryUrn)
                if doc.sourceRepository.repositoryUrn
                else None
            ),
            url=doc.sourceRepository.url,
            path=doc.sourceRepository.path,
        )

    yield mcp_workunit(
        entity_urn,
        AgentSkillInfoClass(
            name=doc.name,
            description=doc.description,
            instructions=doc.instructions,
            sourceRepository=source_repository,
            # `requiredTools` is `array[Urn]` with `entityTypes: [api]` in AgentSkillInfo.pdl
            # -- ids of API documents, not free-text tool names.
            requiredTools=[api_urn(t) for t in doc.requiredTools] if doc.requiredTools else None,
        ),
    )

    dpi = build_data_platform_instance_aspect(doc.platform, doc.instance)
    if dpi:
        yield mcp_workunit(entity_urn, dpi)

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)


def build_ai_agent(
    doc: AIAgentDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"AI_AGENT '{doc.id}'"
    entity_urn = ai_agent_urn(doc.id)

    source = None
    if doc.source:
        source = AIAgentSourceClass(
            type=doc.source.type,
            clonedFrom=ai_agent_urn(doc.source.clonedFrom) if doc.source.clonedFrom else None,
        )

    # `created`/`lastModified` are required on AIAgentInfoClass (unlike every other
    # Phase 5C aspect) -- pin to the epoch for a deterministic golden file, same as
    # `build_query()` does for `queryProperties`.
    yield mcp_workunit(
        entity_urn,
        AIAgentInfoClass(
            name=doc.name,
            created=ZERO_AUDIT_STAMP,
            lastModified=ZERO_AUDIT_STAMP,
            tagline=doc.tagline,
            description=doc.description,
            instructions=doc.instructions,
            source=source,
        ),
    )

    if doc.dependencies:
        deps = doc.dependencies
        yield mcp_workunit(
            entity_urn,
            AIAgentDependenciesClass(
                skills=[agent_skill_urn(s) for s in deps.skills] if deps.skills else None,
                # `tools` is `array[Urn]` with `entityTypes: [api]` in AIAgentDependencies.pdl
                # -- ids of API documents, not free-text tool names.
                tools=[api_urn(t) for t in deps.tools] if deps.tools else None,
                models=[ml_model_urn(m) for m in deps.models] if deps.models else None,
            ),
        )

    if doc.displayProperties:
        yield mcp_workunit(
            entity_urn, DisplayPropertiesClass(colorHex=doc.displayProperties.colorHex)
        )

    dpi = build_data_platform_instance_aspect(doc.platform, doc.instance)
    if dpi:
        yield mcp_workunit(entity_urn, dpi)

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)


def build_service(
    doc: ServiceDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"SERVICE '{doc.id}'"
    entity_urn = service_urn(doc.id)

    yield mcp_workunit(
        entity_urn,
        ServicePropertiesClass(
            displayName=doc.displayName,
            customProperties=stringify_custom_properties(doc.properties),
            description=doc.description,
            lifecycle=doc.lifecycle,
            apis=[api_urn(a) for a in doc.apis] if doc.apis else None,
            sourceRepository=repository_urn(doc.sourceRepository) if doc.sourceRepository else None,
        ),
    )
    if doc.mcpServer:
        yield mcp_workunit(
            entity_urn,
            McpServerPropertiesClass(
                url=doc.mcpServer.url,
                transport=doc.mcpServer.transport,
                timeout=doc.mcpServer.timeout,
                customHeaders=doc.mcpServer.customHeaders,
            ),
        )
    if doc.definition:
        yield mcp_workunit(
            entity_urn,
            ServiceDefinitionClass(
                format=doc.definition.format,
                rawSpec=LargeStringClass(blob=doc.definition.rawSpec),
                version=doc.definition.version,
                externalUrl=doc.definition.externalUrl,
            ),
        )

    dpi = build_data_platform_instance_aspect(doc.platform, doc.instance)
    if dpi:
        yield mcp_workunit(entity_urn, dpi)

    yield from common_aspect_mcps(entity_urn, doc, index, report, context)
