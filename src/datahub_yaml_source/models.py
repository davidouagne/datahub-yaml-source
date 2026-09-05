"""Pydantic document models for the YAML metadata-as-code format.

Every document in a source file is either:
  - an *entity document*, discriminated by its `kind` field, or
  - a *raw aspect document*, discriminated by the presence of an `aspectName`
    field (no `kind`).

These models only describe the on-disk shape of the YAML. Translation into
DataHub aspects/URNs happens in `datahub_yaml_source.builders.*`.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _coerce_to_list(value: Any) -> Any:
    """Some hand-authored YAML gives a single item where a list is expected
    (e.g. `glossaryTerms: fhir:Condition` instead of `- fhir:Condition`)."""
    if value is None or isinstance(value, list):
        return value
    return [value]


StringList = Annotated[list[str], BeforeValidator(_coerce_to_list)]


class OwnerEntry(BaseModel):
    owner: str
    type: str = "TECHNICAL_OWNER"


OwnersField = OwnerEntry | list[OwnerEntry]


def normalize_owners(owners: OwnersField | None) -> list[OwnerEntry]:
    if owners is None:
        return []
    if isinstance(owners, OwnerEntry):
        return [owners]
    return owners


SubTypesField = str | list[str]


def normalize_sub_types(sub_types: SubTypesField | None) -> list[str]:
    if sub_types is None:
        return []
    if isinstance(sub_types, str):
        return [sub_types]
    return sub_types


class DatasetRef(BaseModel):
    """Reference to a dataset by its natural (platform, name, env) key."""

    platform: str
    name: str
    env: str = "PROD"
    instance: str | None = None


class DatasetFieldRef(DatasetRef):
    fieldPath: str


class ContainerRef(BaseModel):
    """Reference to a container by its natural (platform, database, schema) key.

    Only `platform` + `database` + `schema` determine the container's URN;
    `instance` and `env` are accepted but never affect it (they're only used
    for the separate `dataPlatformInstance` aspect). See the "Container URN
    computation" section in yaml.md.
    """

    model_config = ConfigDict(populate_by_name=True)

    platform: str = Field(description="Platform of the container, e.g. 'postgres', 'duckdb', 's3'.")
    instance: str | None = Field(
        default=None, description="Platform instance name. Does not affect the container's URN."
    )
    database: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")
    env: str = Field(default="PROD", description="Does not affect the container's URN.")


class ForeignKeyDoc(BaseModel):
    """A foreign key constraint from this dataset's schema to another dataset."""

    name: str
    sourceFields: list[DatasetFieldRef] = Field(
        default_factory=list, description="Column(s) on this dataset."
    )
    foreignDataset: DatasetRef = Field(description="The dataset the foreign key points to.")
    foreignFields: list[DatasetFieldRef] = Field(
        default_factory=list, description="Column(s) on the foreign dataset."
    )


# SchemaFieldDoc / SchemaBlock are defined further below, after the Has*
# mixins -- SchemaFieldDoc needs to inherit some of them (Phase 3: column-
# level metadata).


class ViewPropertiesDoc(BaseModel):
    """The definition (usually SQL) behind a view. Pair with `subTypes: View`."""

    viewLogic: str = Field(description="The view's definition, e.g. its SELECT statement.")
    viewLanguage: str = Field(default="SQL", description="e.g. 'SQL'.")
    materialized: bool = Field(default=False, description="True for a materialized view.")
    formattedViewLogic: str | None = Field(
        default=None, description="Optional pretty-printed/formatted version of viewLogic."
    )


class FineGrainedLineageDoc(BaseModel):
    """A single column-level lineage edge."""

    upstream: DatasetFieldRef | None = Field(
        default=None,
        description="Source column. Absent for e.g. operation: CONSTANT, where the downstream "
        "value is a literal with no source column.",
    )
    downstream: DatasetFieldRef
    operation: str | None = Field(
        default=None, description="Free-text transform description, e.g. IDENTITY, CONSTANT."
    )
    confidence: float | None = 1.0


class UpstreamEntryDoc(BaseModel):
    dataset: DatasetRef


class UpstreamLineageDoc(BaseModel):
    """Table-level and (optionally) column-level lineage for a dataset."""

    upstreams: list[UpstreamEntryDoc] = Field(
        default_factory=list, description="Upstream (source) datasets."
    )
    fineGrainedLineages: list[FineGrainedLineageDoc] | None = Field(
        default=None, description="Column-level lineage edges."
    )


class LinkDoc(BaseModel):
    """A link surfaced in DataHub's "Links" panel (the `institutionalMemory` aspect)."""

    url: str
    description: str | None = None


class DeprecationDoc(BaseModel):
    """Marks an entity deprecated. Emits the `deprecation` aspect."""

    deprecated: bool = Field(
        default=True, description="Set to false to explicitly un-deprecate an entity."
    )
    note: str | None = None
    decommissionTime: int | None = Field(
        default=None, description="Planned removal time, epoch millis."
    )
    actor: str | None = Field(
        default=None, description="Owner name; converted to a corpuser URN if not already one."
    )


# --- Cross-cutting aspect mixins --------------------------------------------
#
# Every entity `kind:` inherits exactly the mixins below that DataHub's entity
# registry (metadata-models/src/main/resources/entity-registry.yml, verified
# cell-by-cell against v1.7.0rc1-111-gb9890a0912) actually permits for that
# entity type. This makes per-kind validity static: a field that isn't valid
# on a kind simply isn't a field on that Pydantic model, rather than being a
# separate allowlist that has to be kept in sync with the class declarations.
# See docs/specs/entity-aspect-coverage-gaps.md and _PLANNING.md.
#
# Verified matrix (Y = mixin included, blank/'-' = not permitted on that kind):
#
#                  owners tags terms domain apps links deprecation structProps subTypes
#   DATASET          Y     Y    Y     Y      Y     Y      Y            Y          Y
#   CHART            Y     Y    Y     Y      Y     Y      Y            Y          Y
#   DASHBOARD        Y     Y    Y     Y      Y     Y      Y            Y          Y
#   QUERY            -     -    -     -      -     -      -            -          Y
#   INCIDENT         -     Y    -     -      -     -      -            -          -
#   DOCUMENT         Y     Y    Y     Y      -     Y      -            Y          Y
#   MLMODEL          Y     Y    Y     Y      Y     Y      Y            Y          Y
#   MLMODEL_GROUP    Y     Y    Y     Y      Y     Y      Y            Y          Y
#   MLFEATURE_TABLE  Y     Y    Y     Y      Y     Y      Y            Y          Y
#   MLFEATURE        Y     Y    Y     Y      Y     Y      Y            Y          Y
#   MLPRIMARY_KEY    Y     Y    Y     Y      Y     Y      Y            Y          Y
#   SEMANTIC_MODEL   Y     Y    Y     Y      Y     Y      Y            Y          Y
#   METRIC           Y     Y    Y     Y      Y     Y      Y            Y          Y
#   REPOSITORY       Y     Y    Y     Y      -     Y      -            Y          Y
#   API              Y     Y    Y     Y      -     Y      -            Y          Y
#   AGENT_SKILL      Y     Y    Y     Y      -     Y      -            Y          -
#   AI_AGENT         Y     Y    Y     Y      -     Y      -            Y          -
#   SERVICE          Y     Y    -     -      -     -      -            -          Y
#   CONTAINER        Y     Y    Y     Y      Y     Y      Y            Y          Y
#   DATA_FLOW        Y     Y    Y     Y      Y     Y      Y            Y          Y
#   DATA_JOB         Y     Y    Y     Y      Y     Y      Y            Y          (via `type`, see DataJobDoc)  # noqa: E501
#   DATA_PRODUCT     Y     Y    Y     Y      Y     Y      Y            Y          Y
#   DOMAIN           Y     -    -     -      -     Y      Y            Y          -
#   APPLICATION      Y     Y    -     Y      -     Y      -            Y          Y
#   GLOSSARY_TERM    Y     Y    -     Y      Y     Y      Y            Y          Y
#   GLOSSARY_NODE    Y     Y    -     Y      -     Y      -            Y          Y
#   TAG              Y     -    -     -      -     -      Y            -          -
#   ASSERTION        Y     Y    -     -      -     -      -            -          -


class _AllowExtraFields(BaseModel):
    """Base for every kind-discriminated entity document.

    `extra="allow"` so a typo'd or unsupported field doesn't hard-fail parsing
    -- kept consistent with the connector's warn-and-skip philosophy. The
    loader inspects `model_extra` after validation and reports it as a
    warning (escalated to an error under `fail_on_unresolved_reference`), so
    authors are never *silently* ignored, which was the connector's original
    behavior.
    """

    model_config = ConfigDict(extra="allow")


class HasOwners(BaseModel):
    owners: OwnersField | None = None


class HasTags(BaseModel):
    tags: StringList | None = None


class HasTerms(BaseModel):
    glossaryTerms: StringList | None = None


class HasDomain(BaseModel):
    domains: str | None = None


class HasApplications(BaseModel):
    applications: StringList | None = Field(
        default=None, description="ids of the APPLICATION documents this entity belongs to."
    )


class HasLinks(BaseModel):
    links: list[LinkDoc] | None = Field(
        default=None,
        description="Links shown in DataHub's 'Links' panel (the institutionalMemory aspect).",
    )


class HasDeprecation(BaseModel):
    deprecation: DeprecationDoc | None = None


class HasStructuredProps(BaseModel):
    structuredProperties: dict[str, Any] | None = Field(
        default=None,
        description="Map of structuredProperty qualifiedName -> value (or list of values).",
    )


class HasSubTypes(BaseModel):
    subTypes: SubTypesField | None = None


class SchemaFieldDoc(HasTags, HasTerms, HasStructuredProps, HasDeprecation, BaseModel):
    """A single column/field in a dataset's schema.

    Cross-cutting mixins per `schemaField`'s entry in entity-registry.yml:
    tags/glossaryTerms/structuredProperties/deprecation are permitted (as
    are ownership/domains/subTypes/documentation/businessAttributes, not
    exposed here -- no current use case, see _PLANNING.md Phase 3 scope).
    """

    fieldPath: str
    type: str = Field(
        description="A DataHub schema type: number, string, boolean, date, time, bytes, record."
    )
    description: str | None = None
    nativeDataType: str | None = Field(
        default=None, description="The source system's own type name, e.g. VARCHAR(255)."
    )
    partOfKey: bool = False
    nullable: bool | None = None


class SchemaBlock(BaseModel):
    """A dataset's full schema: its fields and any foreign keys."""

    fields: list[SchemaFieldDoc] = Field(default_factory=list)
    foreignKeys: list[ForeignKeyDoc] | None = None


class DisplayPropertiesDoc(BaseModel):
    """Colour surfaced in the DataHub UI. Emits the `displayProperties` aspect.
    (`icon` is not supported yet -- DataHub's `IconPropertiesClass` needs an
    icon library/name/style triple with no natural single-field shorthand.)"""

    colorHex: str | None = None


class DataPlatformDoc(_AllowExtraFields):
    """Registers a custom data platform (e.g. one not built into DataHub's
    core platform list). Not needed for well-known platforms like `postgres`
    or `duckdb` -- only for platforms DataHub doesn't already know about."""

    kind: Literal["DATA_PLATFORM"]
    name: str = Field(
        description="Platform identifier, e.g. 'pathling'. Becomes urn:li:dataPlatform:<name>."
    )
    displayName: str | None = None
    type: str = Field(
        default="OTHERS",
        description="One of DataHub's PlatformType enum values, e.g. RELATIONAL_DB, OTHERS.",
    )
    logoUrl: str | None = None
    datasetNameDelimiter: str = "."


class TagDoc(HasOwners, HasDeprecation, _AllowExtraFields):
    """A tag definition. Referenced elsewhere via `tags: [<name>]`."""

    kind: Literal["TAG"]
    name: str
    description: str | None = None
    colorHex: str | None = None


class GlossaryNodeDoc(
    HasOwners, HasTags, HasDomain, HasLinks, HasStructuredProps, HasSubTypes, _AllowExtraFields
):
    """A glossary category/folder that groups related glossary terms."""

    kind: Literal["GLOSSARY_NODE"]
    id: str = Field(
        description=(
            "Stable identifier, becomes urn:li:glossaryNode:<id>. Referenced via 'parentNode'."
        )
    )
    name: str
    definition: str | None = None
    parentNode: str | None = Field(
        default=None, description="id of a parent GLOSSARY_NODE, for nested categories."
    )
    displayProperties: DisplayPropertiesDoc | None = None


class GlossaryRelatedTermsDoc(BaseModel):
    """Relationships to other glossary terms. Emits the `glossaryRelatedTerms`
    aspect. Each list holds ids of other GLOSSARY_TERM documents."""

    isRelatedTerms: StringList | None = Field(
        default=None,
        description="'is a' relationships, e.g. this term is a kind of the related term.",
    )
    hasRelatedTerms: StringList | None = Field(
        default=None,
        description="'has a' relationships, e.g. this term has the related term as a part.",
    )
    values: StringList | None = Field(
        default=None, description="Related terms representing possible values of this term."
    )
    relatedTerms: StringList | None = Field(
        default=None, description="General 'is related to' relationships."
    )


class GlossaryTermDoc(
    HasOwners,
    HasTags,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A glossary term. Referenced elsewhere via `glossaryTerms: [<id>]`."""

    kind: Literal["GLOSSARY_TERM"]
    id: str = Field(description="Stable identifier, becomes urn:li:glossaryTerm:<id>.")
    name: str
    definition: str | None = None
    parentNode: str | None = Field(
        default=None, description="id of the GLOSSARY_NODE this term belongs to."
    )
    glossaryRelatedTerms: GlossaryRelatedTermsDoc | None = None
    termSource: str | None = Field(default=None, description="e.g. 'EXTERNAL' or 'INTERNAL'.")
    sourceRef: str | None = Field(
        default=None,
        description="Name of the external source this term came from, if termSource is EXTERNAL.",
    )
    sourceUrl: str | None = None
    displayProperties: DisplayPropertiesDoc | None = None


class AllowedValueDoc(BaseModel):
    value: Any
    description: str | None = None


class StructuredPropertySettingsDoc(BaseModel):
    showInAssetSummary: bool | None = None
    showInSearchFilters: bool | None = None
    showInColumnsTable: bool | None = None
    showAsAssetBadge: bool | None = None
    isHidden: bool | None = None


class StructuredPropertyDoc(_AllowExtraFields):
    """A custom structured property definition (a typed, filterable field
    attachable to datasets/data products/etc, beyond built-in DataHub fields).
    """

    kind: Literal["STRUCTURED_PROPERTY"]
    qualifiedName: str = Field(
        description="Globally unique dotted name, e.g. 'org.example.legalBasis'."
    )
    displayName: str | None = None
    description: str | None = None
    cardinality: str = Field(
        default="SINGLE", description="SINGLE or MULTIPLE values allowed per entity."
    )
    valueType: str = Field(
        description="One of DataHub's data types: string, number, date, rich_text, urn, ..."
    )
    allowedValues: list[AllowedValueDoc] | None = Field(
        default=None, description="Restrict to an enum of allowed values; omit to allow any value."
    )
    entityTypes: list[str] = Field(
        default_factory=list,
        description=(
            "Which entity types this property can be attached to, e.g. [dataset, dataProduct]."
        ),
    )
    typeQualifier: list[str] | None = Field(
        default=None,
        description="For valueType 'urn': list of allowed target entity-type URNs "
        "(e.g. 'urn:li:entityType:datahub.dataProduct'). Maps to the 'allowedTypes' qualifier.",
    )
    settings: StructuredPropertySettingsDoc | None = Field(
        default=None, description="Where this property is surfaced in the DataHub UI."
    )


class DomainDoc(HasOwners, HasLinks, HasDeprecation, HasStructuredProps, _AllowExtraFields):
    """A business domain, used to group related datasets/data products.
    Referenced elsewhere via `domains: <id>`."""

    kind: Literal["DOMAIN"]
    id: str = Field(description="Stable identifier, becomes urn:li:domain:<id>.")
    name: str
    description: str | None = None
    parentDomain: str | None = Field(
        default=None, description="id of a parent DOMAIN, for nested domain trees."
    )
    displayProperties: DisplayPropertiesDoc | None = None


class ApplicationLineageEdgeDoc(BaseModel):
    """One edge in an APPLICATION's `applicationLineage`. Exactly one of `api`
    or `dataset` must be set -- `applicationLineage`'s underlying edges accept
    either an `api` or a `dataset` entity, never both."""

    api: str | None = Field(default=None, description="id of an API document.")
    dataset: DatasetRef | None = None


class ApplicationLineageDoc(BaseModel):
    """Which APIs/datasets an APPLICATION consumes and produces."""

    consumes: list[ApplicationLineageEdgeDoc] | None = Field(
        default=None, description="Upstream APIs/datasets this application reads from."
    )
    produces: list[ApplicationLineageEdgeDoc] | None = Field(
        default=None, description="Downstream APIs/datasets this application writes to."
    )


class ApplicationDoc(
    HasOwners, HasTags, HasDomain, HasLinks, HasStructuredProps, HasSubTypes, _AllowExtraFields
):
    """A source application/system (e.g. an EHR, an ERP). Referenced elsewhere
    via `applications: [<id>]`."""

    kind: Literal["APPLICATION"]
    id: str = Field(description="Stable identifier, becomes urn:li:application:<id>.")
    name: str
    description: str | None = None
    applicationLineage: ApplicationLineageDoc | None = Field(
        default=None, description="APIs/datasets this application consumes and produces."
    )


class ContainerDoc(
    ContainerRef,
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A container (database, schema, bucket, ...). Emitted with parents
    before children automatically, regardless of declaration order across
    files. See `ContainerRef` for how the URN is computed."""

    kind: Literal["CONTAINER"]
    name: str
    description: str | None = None
    externalUrl: str | None = None
    parentContainer: ContainerRef | None = Field(
        default=None,
        description="Reference to the parent container, if any (e.g. a schema's parent database).",
    )
    properties: dict[str, Any] | None = None


class DatasetDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A dataset (table, view, topic, file, ...)."""

    model_config = ConfigDict(populate_by_name=True)

    kind: Literal["DATASET"]
    name: str
    platform: str
    env: str = "PROD"
    instance: str | None = None
    displayName: str | None = None
    description: str | None = None
    container: ContainerRef | None = Field(
        default=None, description="The dataset's parent container."
    )
    schema_block: SchemaBlock | None = Field(default=None, alias="schema")
    properties: dict[str, Any] | None = None
    externalUrl: str | None = None
    upstreamLineage: UpstreamLineageDoc | None = None
    viewProperties: ViewPropertiesDoc | None = Field(
        default=None,
        description="For views: the view's SQL definition. Set subTypes: View alongside it. "
        "No lineage is inferred from viewLogic -- declare upstreamLineage explicitly if needed.",
    )


class ChartRef(BaseModel):
    """Reference to a CHART by its natural (platform, name) key."""

    platform: str
    name: str


class DashboardRef(BaseModel):
    """Reference to a DASHBOARD by its natural (platform, name) key."""

    platform: str
    name: str


class ChartDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A chart/visualization from a BI tool (Superset, Looker, Tableau, ...).
    Referenced from a DASHBOARD's `charts:` field by (platform, name)."""

    kind: Literal["CHART"]
    name: str = Field(
        description="Chart identifier within its platform. Becomes part of the chart URN."
    )
    platform: str = Field(description="The BI tool, e.g. 'superset', 'looker', 'tableau'.")
    instance: str | None = None
    displayName: str | None = None
    description: str | None = None
    chartUrl: str | None = Field(
        default=None, description="Link to the chart in its native BI tool."
    )
    chartType: str | None = Field(
        default=None, description="One of DataHub's ChartType values, e.g. BAR, LINE, PIE, TABLE."
    )
    externalUrl: str | None = None
    container: ContainerRef | None = Field(
        default=None, description="The chart's parent container, if any."
    )
    inputDatasets: list[DatasetRef] | None = Field(
        default=None, description="Datasets this chart is built from."
    )
    properties: dict[str, Any] | None = None


class DashboardDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A dashboard: a collection of charts (and/or nested dashboards) from a
    BI tool (Superset, Looker, Tableau, ...)."""

    kind: Literal["DASHBOARD"]
    name: str = Field(
        description="Dashboard identifier within its platform. Becomes part of the dashboard URN."
    )
    platform: str = Field(description="The BI tool, e.g. 'superset', 'looker', 'tableau'.")
    instance: str | None = None
    displayName: str | None = None
    description: str | None = None
    dashboardUrl: str | None = Field(
        default=None, description="Link to the dashboard in its native BI tool."
    )
    externalUrl: str | None = None
    container: ContainerRef | None = Field(
        default=None, description="The dashboard's parent container, if any."
    )
    charts: list[ChartRef] | None = Field(
        default=None, description="Charts shown on this dashboard."
    )
    dashboards: list[DashboardRef] | None = Field(
        default=None, description="Other dashboards nested under this one."
    )
    inputDatasets: list[DatasetRef] | None = Field(
        default=None, description="Datasets this dashboard is built from."
    )
    properties: dict[str, Any] | None = None


class QuerySubjectRef(DatasetRef):
    """A dataset (or, with `fieldPath`, one of its columns) that a QUERY reads."""

    fieldPath: str | None = None


class QueryDoc(HasSubTypes, _AllowExtraFields):
    """A saved/observed query (e.g. the SQL behind a dashboard or a dbt model).
    `query` only permits `subTypes` among the cross-cutting aspects."""

    kind: Literal["QUERY"]
    id: str = Field(description="Stable identifier, becomes urn:li:query:<id>.")
    name: str | None = None
    description: str | None = None
    statement: str = Field(description="The query text, e.g. a SQL SELECT statement.")
    language: str = Field(default="SQL", description="SQL or UNKNOWN.")
    source: str = Field(
        default="MANUAL", description="MANUAL (hand-authored here) or SYSTEM (observed)."
    )
    subjects: list[QuerySubjectRef] | None = Field(
        default=None, description="Datasets/columns this query reads."
    )


class IncidentStatusDoc(BaseModel):
    state: str = Field(default="ACTIVE", description="ACTIVE or RESOLVED.")
    stage: str | None = Field(
        default=None,
        description="TRIAGE, INVESTIGATION, WORK_IN_PROGRESS, FIXED, or NO_ACTION_REQUIRED.",
    )
    message: str | None = None


class IncidentSourceDoc(BaseModel):
    type: str = Field(description="MANUAL or ASSERTION_FAILURE.")
    sourceUrn: str | None = Field(
        default=None,
        description=(
            "Full URN of the triggering entity, e.g. an ASSERTION's urn, "
            "if type is ASSERTION_FAILURE."
        ),
    )


class IncidentDoc(HasTags, _AllowExtraFields):
    """A data quality/operational incident. `incident` only permits `tags`
    among the cross-cutting aspects."""

    kind: Literal["INCIDENT"]
    id: str = Field(description="Stable identifier, becomes urn:li:incident:<id>.")
    type: str = Field(
        description="OPERATIONAL, FRESHNESS, VOLUME, SQL, FIELD, DATA_SCHEMA, or CUSTOM."
    )
    customType: str | None = Field(
        default=None, description="Free-text type name, required if type is CUSTOM."
    )
    title: str | None = None
    description: str | None = None
    priority: int | None = None
    entities: list[str] = Field(
        description="Full URNs of the entities (usually datasets) affected."
    )
    status: IncidentStatusDoc | None = None
    assignees: StringList | None = Field(
        default=None, description="Owner names; converted to corpuser URNs if not already URNs."
    )
    source: IncidentSourceDoc | None = None
    startedAt: int | None = Field(default=None, description="Epoch millis.")
    notes: StringList | None = Field(
        default=None, description="Free-text notes about this incident."
    )


class DocumentDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasLinks,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A knowledge-base document (a runbook, a FAQ, an AI-context note, ...).
    `document` permits owners/tags/glossaryTerms/domains/links/
    structuredProperties/subTypes, but not applications or deprecation."""

    kind: Literal["DOCUMENT"]
    id: str = Field(description="Stable identifier, becomes urn:li:document:<id>.")
    title: str
    text: str | None = Field(
        default=None,
        description=(
            "Markdown body, stored natively in DataHub. Required unless externalUrl is set."
        ),
    )
    status: str = Field(default="PUBLISHED", description="PUBLISHED or UNPUBLISHED.")
    showInGlobalContext: bool = Field(
        default=True,
        description=(
            "If false, only reachable via relatedAssets/relatedDocuments "
            "-- useful for AI-only context documents."
        ),
    )
    platform: str | None = Field(
        default=None,
        description=(
            "The external system's platform, e.g. 'confluence'. Required if externalUrl is set."
        ),
    )
    externalUrl: str | None = Field(
        default=None, description="Link to the document in an external system."
    )
    externalId: str | None = None
    parentDocument: str | None = Field(
        default=None, description="id of a parent DOCUMENT, for hierarchical organization."
    )
    relatedAssets: list[str] | None = Field(
        default=None, description="Full URNs of related data assets (datasets, dashboards, ...)."
    )
    relatedDocuments: StringList | None = Field(
        default=None, description="ids of related DOCUMENT documents."
    )
    properties: dict[str, Any] | None = None


class MLFeatureRef(BaseModel):
    """Reference to an MLFEATURE by its natural (featureNamespace, name) key."""

    featureNamespace: str
    name: str


class MLPrimaryKeyRef(BaseModel):
    """Reference to an MLPRIMARY_KEY by its natural (featureNamespace, name) key."""

    featureNamespace: str
    name: str


class MLModelGroupRef(BaseModel):
    """Reference to an MLMODEL_GROUP by its natural (platform, name, env) key."""

    platform: str
    name: str
    env: str = "PROD"
    instance: str | None = None


class MLFeatureTableDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A feature store's feature table (e.g. a Feast feature view)."""

    kind: Literal["MLFEATURE_TABLE"]
    name: str = Field(
        description="Feature table identifier. Becomes part of the mlFeatureTable URN."
    )
    platform: str = Field(description="The feature store platform, e.g. 'feast'.")
    description: str | None = None
    properties: dict[str, Any] | None = None
    mlFeatures: list[MLFeatureRef] | None = Field(
        default=None, description="Features in this table."
    )
    mlPrimaryKeys: list[MLPrimaryKeyRef] | None = Field(
        default=None, description="Primary key(s) of this table."
    )


class MLFeatureDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A single feature in a feature store."""

    kind: Literal["MLFEATURE"]
    featureNamespace: str = Field(
        description="The feature's namespace, usually its feature table's name."
    )
    name: str
    description: str | None = None
    dataType: str | None = Field(
        default=None,
        description="One of DataHub's MLFeatureDataType values, e.g. CONTINUOUS, NOMINAL, TEXT.",
    )
    properties: dict[str, Any] | None = None
    sources: list[QuerySubjectRef] | None = Field(
        default=None, description="Dataset(s)/column(s) this feature is derived from."
    )


class MLPrimaryKeyDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A feature table's primary key."""

    kind: Literal["MLPRIMARY_KEY"]
    featureNamespace: str
    name: str
    description: str | None = None
    dataType: str | None = None
    properties: dict[str, Any] | None = None
    sources: list[QuerySubjectRef] = Field(
        description="Dataset(s)/column(s) this primary key is derived from."
    )


class MLModelGroupDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A group of related ML model versions (e.g. all versions of one MLflow registered model)."""

    kind: Literal["MLMODEL_GROUP"]
    name: str = Field(description="Model group identifier. Becomes part of the mlModelGroup URN.")
    platform: str
    instance: str | None = None
    env: str = "PROD"
    displayName: str | None = None
    description: str | None = None
    externalUrl: str | None = None
    properties: dict[str, Any] | None = None
    container: ContainerRef | None = Field(
        default=None, description="The model group's parent container, if any."
    )


class IntendedUseDoc(BaseModel):
    """[MLMODEL model card] Intended and out-of-scope uses. Emits the `intendedUse` aspect."""

    primaryUses: list[str] | None = None
    primaryUsers: list[str] | None = None
    outOfScopeUses: list[str] | None = None


class CaveatDetailsDoc(BaseModel):
    needsFurtherTesting: bool | None = None
    caveatDescription: str | None = None
    groupsNotRepresented: list[str] | None = None


class EthicalConsiderationsDoc(BaseModel):
    """[MLMODEL model card] Emits the `mlModelEthicalConsiderations` aspect."""

    data: list[str] | None = None
    humanLife: list[str] | None = None
    mitigations: list[str] | None = None
    risksAndHarms: list[str] | None = None
    useCases: list[str] | None = None


class CaveatsAndRecommendationsDoc(BaseModel):
    """[MLMODEL model card] Emits the `mlModelCaveatsAndRecommendations` aspect."""

    caveats: CaveatDetailsDoc | None = None
    recommendations: str | None = None
    idealDatasetCharacteristics: list[str] | None = None


class MLModelDataDoc(BaseModel):
    """[MLMODEL model card] One dataset used for training or evaluation -- an entry of
    the `mlModelTrainingData`/`mlModelEvaluationData` aspects."""

    dataset: DatasetRef
    motivation: str | None = None
    preProcessing: list[str] | None = None


class MLModelFactorDoc(BaseModel):
    groups: list[str] | None = None
    instrumentation: list[str] | None = None
    environment: list[str] | None = None


class MLModelFactorPromptsDoc(BaseModel):
    """[MLMODEL model card] Emits the `mlModelFactorPrompts` aspect."""

    relevantFactors: list[MLModelFactorDoc] | None = None
    evaluationFactors: list[MLModelFactorDoc] | None = None


class MLModelMetricsDoc(BaseModel):
    """[MLMODEL model card] Emits the `mlModelMetrics` aspect."""

    performanceMeasures: list[str] | None = None
    decisionThreshold: list[str] | None = None


class MLModelSourceCodeDoc(BaseModel):
    type: str = Field(
        description=(
            "TRAINING_PIPELINE_SOURCE_CODE, EVALUATION_PIPELINE_SOURCE_CODE, "
            "or ML_MODEL_SOURCE_CODE."
        )
    )
    sourceCodeUrl: str


class MLModelDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """An ML model version. Its full "model card" is supported: intended use, ethical
    considerations, caveats/recommendations, training/evaluation data, factor prompts,
    metrics, and source code -- all valid only on `mlModel` per the entity registry, so
    they live directly on this model rather than as a shared mixin (D1 is for aspects
    shared *across* kinds). `cost` is deliberately not exposed -- a financial
    discriminated-union structure outside the usual "model card" concept, with no
    current use case."""

    kind: Literal["MLMODEL"]
    name: str = Field(description="Model version identifier. Becomes part of the mlModel URN.")
    platform: str
    instance: str | None = None
    env: str = "PROD"
    displayName: str | None = None
    description: str | None = None
    type: str | None = Field(
        default=None, description="Free-text model type, e.g. 'classification'."
    )
    externalUrl: str | None = None
    properties: dict[str, Any] | None = None
    hyperParameters: dict[str, Any] | None = None
    modelGroup: MLModelGroupRef | None = Field(
        default=None, description="The MLMODEL_GROUP this version belongs to."
    )
    mlFeatures: list[MLFeatureRef] | None = Field(
        default=None, description="Features this model consumes."
    )
    container: ContainerRef | None = Field(
        default=None, description="The model's parent container, if any."
    )
    intendedUse: IntendedUseDoc | None = None
    ethicalConsiderations: EthicalConsiderationsDoc | None = None
    caveatsAndRecommendations: CaveatsAndRecommendationsDoc | None = None
    trainingData: list[MLModelDataDoc] | None = None
    evaluationData: list[MLModelDataDoc] | None = None
    factorPrompts: MLModelFactorPromptsDoc | None = None
    metrics: MLModelMetricsDoc | None = None
    sourceCode: list[MLModelSourceCodeDoc] | None = None


class AiContextDoc(BaseModel):
    """Freeform AI-consumption hints (synonyms, instructions, examples). Emits the
    `aiContext` aspect. Valid on SEMANTIC_MODEL and METRIC."""

    synonyms: list[str] | None = None
    instructions: str | None = None
    examples: list[str] | None = None
    customInstructions: str | None = None


class SemanticModelRef(BaseModel):
    """Reference to a SEMANTIC_MODEL by its natural (platform, path, id) key."""

    platform: str
    path: str
    id: str


class MetricRef(BaseModel):
    """Reference to a METRIC by its natural (platform, path, id) key."""

    platform: str
    path: str
    id: str


class SemanticModelDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A semantic-layer model (e.g. a dbt semantic model / Looker explore) -- the entity a
    METRIC is defined against. `relationships` (aliased cross-dataset joins) and
    `semanticContent` (vector embeddings) are deliberately out of scope: the former needs
    an aliased-dataset sub-feature this connector doesn't model, the latter is
    system-computed. See _PLANNING.md, Phase 5B."""

    kind: Literal["SEMANTIC_MODEL"]
    platform: str = Field(description="e.g. 'dbt', 'looker'.")
    path: str = Field(description="Logical path/folder. Part of the semanticModel URN.")
    id: str = Field(description="Identifier. Part of the semanticModel URN.")
    instance: str | None = None
    displayName: str | None = None
    description: str | None = None
    externalUrl: str | None = None
    nativeDefinition: str | None = Field(
        default=None, description="The model's native source definition, e.g. its dbt YAML/SQL."
    )
    datasets: list[DatasetRef] | None = Field(
        default=None, description="Datasets this semantic model is built from."
    )
    aiContext: AiContextDoc | None = None


class MetricDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A business metric definition (e.g. a dbt metric), always scoped to a
    SEMANTIC_MODEL."""

    kind: Literal["METRIC"]
    platform: str
    path: str = Field(description="Logical path/folder. Part of the metric URN.")
    id: str = Field(description="Identifier. Part of the metric URN.")
    instance: str | None = None
    semanticModel: SemanticModelRef = Field(
        description="The SEMANTIC_MODEL this metric is defined against."
    )
    displayName: str | None = None
    description: str | None = None
    externalUrl: str | None = None
    expression: str | None = Field(
        default=None, description="The metric's SQL expression, e.g. 'count(x) / count(*)'."
    )
    derivedFrom: list[MetricRef] | None = Field(
        default=None, description="Other metrics this one is computed from."
    )
    relatedMetrics: list[MetricRef] | None = Field(
        default=None, description="Loosely related metrics."
    )
    datasetUpstreams: list[DatasetRef] | None = Field(
        default=None, description="Datasets this metric reads from directly."
    )
    aiContext: AiContextDoc | None = None


class MLModelRef(BaseModel):
    """Reference to an MLMODEL by its natural (platform, name, env) key."""

    platform: str
    name: str
    env: str = "PROD"
    instance: str | None = None


class McpServerDoc(BaseModel):
    """If a SERVICE is itself an MCP server -- emits the mcpServerProperties aspect."""

    url: str
    transport: str | None = Field(default=None, description="HTTP, SSE, or WEBSOCKET.")
    timeout: float | None = None
    customHeaders: dict[str, str] | None = None


class ServiceDefinitionDoc(BaseModel):
    """A service's machine-readable interface definition (e.g. an OpenAPI document),
    emits the serviceDefinition aspect."""

    format: str = Field(
        description="OPENAPI, GRAPHQL_SDL, GRPC_PROTO, ASYNCAPI, JSON_SCHEMA, or OTHER."
    )
    rawSpec: str = Field(description="The raw definition text, e.g. an OpenAPI YAML document.")
    version: str | None = None
    externalUrl: str | None = None


class RestApiDoc(BaseModel):
    method: str = Field(description="GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, or TRACE.")
    path: str


class ApiSignatureDoc(BaseModel):
    """Only `schemaDefinition` (free text) is exposed -- structured input/output field
    lists are out of scope. See _PLANNING.md, Phase 5C."""

    schemaDefinition: str | None = None


class RepositorySourceDoc(BaseModel):
    externalUrl: str | None = None
    externalId: str | None = None


class SkillSourceRepositoryDoc(BaseModel):
    repositoryUrn: str | None = Field(
        default=None, description="id of a REPOSITORY document; converted to a repository URN."
    )
    url: str | None = None
    path: str | None = None


class AIAgentSourceDoc(BaseModel):
    type: str = Field(description="SYSTEM, NATIVE, or EXTERNAL.")
    clonedFrom: str | None = Field(
        default=None, description="id of another AI_AGENT this one was cloned from."
    )


class AIAgentDependenciesDoc(BaseModel):
    skills: StringList | None = Field(default=None, description="ids of AGENT_SKILL documents.")
    tools: StringList | None = Field(
        default=None, description="ids of API documents this agent invokes as tools."
    )
    models: list[MLModelRef] | None = Field(
        default=None, description="MLMODEL entities this agent relies on."
    )


class DisplayPropertiesDoc(BaseModel):
    colorHex: str | None = None


class RepositoryDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasLinks,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A source code repository (e.g. a GitLab/GitHub project). `repository`
    permits owners/tags/glossaryTerms/domains/links/structuredProperties/subTypes,
    but not applications or deprecation."""

    kind: Literal["REPOSITORY"]
    id: str = Field(description="Stable identifier, becomes urn:li:repository:<id>.")
    name: str
    description: str | None = None
    platform: str | None = Field(
        default=None,
        description="e.g. 'gitlab', 'github' -- emits the dataPlatformInstance aspect.",
    )
    instance: str | None = None
    defaultBranch: str | None = None
    languages: StringList | None = None
    license: str | None = None
    homepageUrl: str | None = None
    archived: bool | None = None
    source: RepositorySourceDoc | None = None
    forkOf: str | None = Field(
        default=None, description="id of another REPOSITORY this one was forked from."
    )


class ApiDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasLinks,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A callable API (e.g. a REST endpoint). `api` permits owners/tags/
    glossaryTerms/domains/links/structuredProperties/subTypes, but not
    applications or deprecation."""

    kind: Literal["API"]
    id: str = Field(description="Stable identifier, becomes urn:li:api:<id>.")
    name: str
    description: str | None = None
    externalUrl: str | None = None
    sourceRepository: str | None = Field(default=None, description="id of a REPOSITORY document.")
    restApi: RestApiDoc | None = None
    signature: ApiSignatureDoc | None = None
    platform: str | None = Field(
        default=None, description="e.g. 'kong' -- emits the dataPlatformInstance aspect."
    )
    instance: str | None = None


class AgentSkillDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasLinks,
    HasStructuredProps,
    _AllowExtraFields,
):
    """A reusable capability an AI_AGENT can invoke. `agentSkill` permits
    owners/tags/glossaryTerms/domains/links/structuredProperties, but not
    applications, deprecation, or subTypes."""

    kind: Literal["AGENT_SKILL"]
    id: str = Field(description="Stable identifier, becomes urn:li:agentSkill:<id>.")
    name: str
    description: str | None = None
    instructions: str | None = None
    requiredTools: StringList | None = Field(
        default=None, description="ids of API documents this skill requires."
    )
    sourceRepository: SkillSourceRepositoryDoc | None = None
    platform: str | None = Field(default=None, description="Emits the dataPlatformInstance aspect.")
    instance: str | None = None


class AIAgentDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasLinks,
    HasStructuredProps,
    _AllowExtraFields,
):
    """An AI agent. `aiAgent` permits owners/tags/glossaryTerms/domains/links/
    structuredProperties, but not applications, deprecation, or subTypes."""

    kind: Literal["AI_AGENT"]
    id: str = Field(description="Stable identifier, becomes urn:li:aiAgent:<id>.")
    name: str
    tagline: str | None = None
    description: str | None = None
    instructions: str | None = None
    source: AIAgentSourceDoc | None = None
    dependencies: AIAgentDependenciesDoc | None = None
    displayProperties: DisplayPropertiesDoc | None = None
    platform: str | None = Field(default=None, description="Emits the dataPlatformInstance aspect.")
    instance: str | None = None


class ServiceDoc(HasOwners, HasTags, HasSubTypes, _AllowExtraFields):
    """A running service (possibly an MCP server). `service` only permits
    owners/tags/subTypes among the cross-cutting aspects."""

    kind: Literal["SERVICE"]
    id: str = Field(description="Stable identifier, becomes urn:li:service:<id>.")
    displayName: str
    description: str | None = None
    lifecycle: str | None = Field(
        default=None, description="EXPERIMENTAL, PRODUCTION, or DEPRECATED."
    )
    apis: StringList | None = Field(
        default=None, description="ids of API documents this service exposes."
    )
    sourceRepository: str | None = Field(default=None, description="id of a REPOSITORY document.")
    mcpServer: McpServerDoc | None = None
    definition: ServiceDefinitionDoc | None = None
    properties: dict[str, Any] | None = None
    platform: str | None = Field(default=None, description="Emits the dataPlatformInstance aspect.")
    instance: str | None = None


class DataProductDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A data product: a curated bundle of datasets/jobs presented as a
    single discoverable asset, with its own domain/tags/owners."""

    kind: Literal["DATA_PRODUCT"]
    id: str = Field(description="Stable identifier, becomes urn:li:dataProduct:<id>.")
    name: str
    description: str | None = None
    assets: list[str] | None = Field(
        default=None,
        description=(
            "Full URNs of the entities (datasets, dataJobs, ...) that make up this product."
        ),
    )


class DataFlowDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    HasSubTypes,
    _AllowExtraFields,
):
    """A pipeline (e.g. an Airflow DAG, a dbt project run)."""

    kind: Literal["DATA_FLOW"]
    orchestrator: str = Field(
        description="e.g. 'airflow', 'dbt'. Becomes part of the dataFlow URN."
    )
    flowId: str
    cluster: str = Field(
        default="PROD", description="Deployment/cluster identifier, part of the dataFlow URN."
    )
    name: str
    description: str | None = None
    project: str | None = None
    externalUrl: str | None = None
    container: ContainerRef | None = Field(
        default=None, description="The pipeline's parent container, if any."
    )


class DataFlowRef(BaseModel):
    """Reference to a DATA_FLOW by its natural (orchestrator, flowId, cluster) key."""

    orchestrator: str
    flowId: str
    cluster: str = "PROD"


class DataFlowJobRef(DataFlowRef):
    """Reference to a DATA_JOB by its natural (orchestrator, flowId, cluster, jobId) key."""

    jobId: str


class DataJobDoc(
    HasOwners,
    HasTags,
    HasTerms,
    HasDomain,
    HasApplications,
    HasLinks,
    HasDeprecation,
    HasStructuredProps,
    _AllowExtraFields,
):
    """A task within a pipeline (DATA_FLOW).

    No `HasSubTypes` mixin: `type` below already fills that role (it was
    wired to the same `subTypes` aspect before this mixin existed), so adding
    a second `subTypes:` field would just give authors two names for one
    thing.
    """

    kind: Literal["DATA_JOB"]
    jobId: str
    dataFlow: DataFlowRef = Field(
        description="Reference to the parent DATA_FLOW this task belongs to."
    )
    name: str
    description: str | None = None
    type: str | None = Field(
        default=None, description="The job's subtype, e.g. 'RawCopy', 'Transform'."
    )
    externalUrl: str | None = None
    properties: dict[str, Any] | None = None
    container: ContainerRef | None = Field(
        default=None, description="The job's parent container, if any."
    )
    inputDatasets: list[DatasetRef] | None = None
    outputDatasets: list[DatasetRef] | None = None
    inputDataJobs: list[DataFlowJobRef] | None = Field(
        default=None,
        description=(
            "Other DATA_JOBs this one depends on -- "
            "job-to-job DAG edges with no dataset in between."
        ),
    )
    fineGrainedLineages: list[FineGrainedLineageDoc] | None = Field(
        default=None, description="Column-level lineage edges from inputDatasets to outputDatasets."
    )


class CreatedDoc(BaseModel):
    timestampMillis: int
    actor: str | None = Field(
        default=None, description="Owner name; converted to a corpuser URN if not already one."
    )


class RunEventDoc(BaseModel):
    status: str = Field(description="e.g. STARTED, COMPLETE, FAILURE.")
    timestampMillis: int
    attempt: int | None = None


class DataProcessInstanceDoc(_AllowExtraFields):
    """A single run of a DATA_JOB, with its own run-event history. For
    ongoing/incremental run events after the initial run, prefer an
    `aspectName: DATA_PROCESS_INSTANCE_RUN_EVENT` raw-aspect document instead
    of appending to `runEvents` here."""

    kind: Literal["DATA_PROCESS_INSTANCE"]
    id: str = Field(description="Stable identifier, becomes urn:li:dataProcessInstance:<id>.")
    name: str
    type: str = "BATCH_SCHEDULED"
    externalUrl: str | None = None
    created: CreatedDoc
    parentTemplate: DataFlowJobRef = Field(
        description="Reference to the DATA_JOB this is a run of."
    )
    inputs: list[DatasetRef] | None = None
    outputs: list[DatasetRef] | None = None
    runEvents: Annotated[list[RunEventDoc], BeforeValidator(_coerce_to_list)] | None = None


class AssertionPropertiesDoc(BaseModel):
    name: str
    dbt_test: str | None = None


class SchemaFieldSpecDoc(BaseModel):
    """[DATA_SCHEMA assertions] One expected column."""

    path: str
    type: str = "string"
    nativeType: str | None = None


class AssertionAssertionDoc(BaseModel):
    """Union of the FRESHNESS / VOLUME / SQL / FIELD / DATA_SCHEMA / CUSTOM
    assertion shapes, kept flat.

    Only the fields relevant to `type` will be populated by the author; the
    assertion builder picks which ones to read based on `type`. `DATASET` is
    deliberately not a supported value -- it is deprecated upstream
    (`AssertionType.pdl`) in favor of `VOLUME`.
    """

    type: str = Field(
        description=(
            "FRESHNESS, VOLUME, SQL, FIELD, DATA_SCHEMA, or CUSTOM "
            "-- selects which fields below apply."
        )
    )
    entityUrn: str = Field(description="Full URN of the dataset this assertion checks.")

    # FRESHNESS
    freshnessType: str | None = Field(default=None, description="[FRESHNESS] e.g. DATASET_CHANGE.")
    scheduleType: str | None = Field(default=None, description="[FRESHNESS] e.g. CRON.")
    cron: str | None = Field(
        default=None, description="[FRESHNESS] cron expression, if scheduleType is CRON."
    )
    timezone: str | None = Field(
        default=None, description="[FRESHNESS] IANA timezone for the cron schedule."
    )

    # VOLUME
    volumeType: str | None = Field(
        default=None,
        description=(
            "[VOLUME] ROW_COUNT_TOTAL or ROW_COUNT_CHANGE -- "
            "reuses 'operator'/'value'/'changeType' below."
        ),
    )

    # SQL / VOLUME
    sqlType: str | None = Field(default=None, description="[SQL] e.g. METRIC.")
    statement: str | None = Field(default=None, description="[SQL] the SQL query to evaluate.")
    operator: str | None = Field(
        default=None, description="[SQL/FIELD/VOLUME] e.g. GREATER_THAN, EQUAL_TO, NOT_NULL."
    )
    value: Any | None = Field(
        default=None, description="[SQL/VOLUME] the comparison value for 'operator'."
    )
    changeType: str | None = Field(
        default=None, description="[SQL/VOLUME] e.g. ABSOLUTE, PERCENTAGE."
    )

    # FIELD
    fieldType: str | None = Field(default=None, description="[FIELD] FIELD_METRIC or FIELD_VALUES.")
    fieldPath: str | None = Field(
        default=None, description="[FIELD] the column this assertion checks."
    )
    dataType: str | None = Field(
        default=None, description="[FIELD] the column's DataHub schema type."
    )
    nativeDataType: str | None = Field(
        default=None, description="[FIELD] the column's native source type."
    )
    metric: str | None = Field(
        default=None, description="[FIELD, FIELD_METRIC] e.g. UNIQUE_PERCENTAGE."
    )
    metricOperator: str | None = Field(
        default=None, description="[FIELD, FIELD_METRIC] comparison operator for 'metric'."
    )
    metricValue: Any | None = Field(
        default=None, description="[FIELD, FIELD_METRIC] the comparison value."
    )
    excludeNulls: bool | None = Field(
        default=None, description="[FIELD, FIELD_VALUES] ignore nulls when checking 'operator'."
    )

    # DATA_SCHEMA
    schemaFields: list[SchemaFieldSpecDoc] | None = Field(
        default=None, description="[DATA_SCHEMA] the expected columns."
    )
    compatibility: str | None = Field(
        default=None, description="[DATA_SCHEMA] e.g. EXACT_MATCH, SUPERSET."
    )

    # CUSTOM
    customType: str | None = Field(
        default=None, description="[CUSTOM] free-text assertion type name."
    )
    logic: str | None = Field(
        default=None, description="[CUSTOM] free-text description of the custom check's logic."
    )


class AssertionActionDoc(BaseModel):
    type: str = Field(description="e.g. RAISE_INCIDENT, RESOLVE_INCIDENT.")


class AssertionActionsDoc(BaseModel):
    """Declarative on-failure/on-success actions. Emits the `assertionActions` aspect."""

    onSuccess: list[AssertionActionDoc] | None = None
    onFailure: list[AssertionActionDoc] | None = None


class AssertionDoc(HasOwners, HasTags, _AllowExtraFields):
    """A data quality assertion (freshness, volume, SQL-based, field-level, schema, or custom check)."""  # noqa: E501

    kind: Literal["ASSERTION"]
    id: str = Field(description="Stable identifier, becomes urn:li:assertion:<id>.")
    description: str | None = None
    sourceType: str = "NATIVE"
    properties: AssertionPropertiesDoc | None = None
    assertion: AssertionAssertionDoc
    assertionNote: str | None = Field(
        default=None, description="Free-text note about this assertion's most recent run."
    )
    assertionActions: AssertionActionsDoc | None = None


class RawAspectDoc(BaseModel):
    """Passthrough document for directly emitting an existing DataHub aspect.

    Discriminated by the presence of `aspectName` rather than `kind`. All
    fields other than `aspectName` and the entity reference are treated as
    the raw payload for that aspect class. Different aspects attach to
    different entity types, so the entity reference is one of several
    mutually-exclusive fields depending on `aspectName`:
      - `dataset`: for dataset-scoped aspects (DATASET_PROFILE, OPERATION, ...)
      - `assertionUrn`: for ASSERTION_RUN_EVENT (already a full URN string)
      - `dataProcessInstanceUrn`: for DATA_PROCESS_INSTANCE_RUN_EVENT (full URN string)
      - `entityUrn`: generic fallback -- a full URN string for any other entity type
    """

    model_config = ConfigDict(extra="allow")

    aspectName: str
    dataset: DatasetRef | None = None
    assertionUrn: str | None = None
    dataProcessInstanceUrn: str | None = None
    entityUrn: str | None = None


ENTITY_DOC_TYPES_BY_KIND = {
    "DATA_PLATFORM": DataPlatformDoc,
    "TAG": TagDoc,
    "GLOSSARY_NODE": GlossaryNodeDoc,
    "GLOSSARY_TERM": GlossaryTermDoc,
    "STRUCTURED_PROPERTY": StructuredPropertyDoc,
    "DOMAIN": DomainDoc,
    "APPLICATION": ApplicationDoc,
    "CONTAINER": ContainerDoc,
    "DATASET": DatasetDoc,
    "CHART": ChartDoc,
    "DASHBOARD": DashboardDoc,
    "QUERY": QueryDoc,
    "INCIDENT": IncidentDoc,
    "DOCUMENT": DocumentDoc,
    "MLFEATURE_TABLE": MLFeatureTableDoc,
    "MLFEATURE": MLFeatureDoc,
    "MLPRIMARY_KEY": MLPrimaryKeyDoc,
    "MLMODEL_GROUP": MLModelGroupDoc,
    "MLMODEL": MLModelDoc,
    "SEMANTIC_MODEL": SemanticModelDoc,
    "METRIC": MetricDoc,
    "REPOSITORY": RepositoryDoc,
    "API": ApiDoc,
    "AGENT_SKILL": AgentSkillDoc,
    "AI_AGENT": AIAgentDoc,
    "SERVICE": ServiceDoc,
    "DATA_PRODUCT": DataProductDoc,
    "DATA_FLOW": DataFlowDoc,
    "DATA_JOB": DataJobDoc,
    "DATA_PROCESS_INSTANCE": DataProcessInstanceDoc,
    "ASSERTION": AssertionDoc,
}

EntityDoc = (
    DataPlatformDoc
    | TagDoc
    | GlossaryNodeDoc
    | GlossaryTermDoc
    | StructuredPropertyDoc
    | DomainDoc
    | ApplicationDoc
    | ContainerDoc
    | DatasetDoc
    | ChartDoc
    | DashboardDoc
    | QueryDoc
    | IncidentDoc
    | DocumentDoc
    | MLFeatureTableDoc
    | MLFeatureDoc
    | MLPrimaryKeyDoc
    | MLModelGroupDoc
    | MLModelDoc
    | SemanticModelDoc
    | MetricDoc
    | RepositoryDoc
    | ApiDoc
    | AgentSkillDoc
    | AIAgentDoc
    | ServiceDoc
    | DataProductDoc
    | DataFlowDoc
    | DataJobDoc
    | DataProcessInstanceDoc
    | AssertionDoc
)

ParsedDoc = EntityDoc | RawAspectDoc


class DocumentParseError(ValueError):
    """Raised when a YAML document doesn't match any known kind/aspectName shape."""


def parse_document(raw: dict[str, Any]) -> ParsedDoc:
    """Dispatch a raw YAML document dict to the correct Pydantic model."""
    if not isinstance(raw, dict):
        raise DocumentParseError(f"Expected a YAML mapping document, got {type(raw)}")

    kind = raw.get("kind")
    if kind is not None:
        model_cls = ENTITY_DOC_TYPES_BY_KIND.get(kind)
        if model_cls is None:
            raise DocumentParseError(
                f"Unknown kind '{kind}'. Supported kinds: {sorted(ENTITY_DOC_TYPES_BY_KIND)}"
            )
        return model_cls.model_validate(raw)

    if "aspectName" in raw:
        return RawAspectDoc.model_validate(raw)

    raise DocumentParseError(
        "Document has neither a 'kind' nor an 'aspectName' field; cannot determine its type."
    )
