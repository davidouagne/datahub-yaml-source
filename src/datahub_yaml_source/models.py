"""Pydantic document models for the YAML metadata-as-code format.

Every document in a source file is either:
  - an *entity document*, discriminated by its `kind` field, or
  - a *raw aspect document*, discriminated by the presence of an `aspectName`
    field (no `kind`).

These models only describe the on-disk shape of the YAML. Translation into
DataHub aspects/URNs happens in `datahub_yaml_source.builders.*`.
"""

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _coerce_to_list(value: Any) -> Any:
    """Some hand-authored YAML gives a single item where a list is expected
    (e.g. `glossaryTerms: fhir:Condition` instead of `- fhir:Condition`)."""
    if value is None or isinstance(value, list):
        return value
    return [value]


StringList = Annotated[List[str], BeforeValidator(_coerce_to_list)]


class OwnerEntry(BaseModel):
    owner: str
    type: str = "TECHNICAL_OWNER"


OwnersField = Union[OwnerEntry, List[OwnerEntry]]


def normalize_owners(owners: Optional[OwnersField]) -> List[OwnerEntry]:
    if owners is None:
        return []
    if isinstance(owners, OwnerEntry):
        return [owners]
    return owners


SubTypesField = Union[str, List[str]]


def normalize_sub_types(sub_types: Optional[SubTypesField]) -> List[str]:
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
    instance: Optional[str] = None


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
    instance: Optional[str] = Field(
        default=None, description="Platform instance name. Does not affect the container's URN."
    )
    database: Optional[str] = None
    schema_name: Optional[str] = Field(default=None, alias="schema")
    env: str = Field(default="PROD", description="Does not affect the container's URN.")


class ForeignKeyDoc(BaseModel):
    """A foreign key constraint from this dataset's schema to another dataset."""

    name: str
    sourceFields: List[DatasetFieldRef] = Field(default_factory=list, description="Column(s) on this dataset.")
    foreignDataset: DatasetRef = Field(description="The dataset the foreign key points to.")
    foreignFields: List[DatasetFieldRef] = Field(
        default_factory=list, description="Column(s) on the foreign dataset."
    )


class SchemaFieldDoc(BaseModel):
    """A single column/field in a dataset's schema."""

    fieldPath: str
    type: str = Field(description="A DataHub schema type: number, string, boolean, date, time, bytes, record.")
    description: Optional[str] = None
    nativeDataType: Optional[str] = Field(default=None, description="The source system's own type name, e.g. VARCHAR(255).")
    partOfKey: bool = False
    nullable: Optional[bool] = None


class SchemaBlock(BaseModel):
    """A dataset's full schema: its fields and any foreign keys."""

    fields: List[SchemaFieldDoc] = Field(default_factory=list)
    foreignKeys: Optional[List[ForeignKeyDoc]] = None


class ViewPropertiesDoc(BaseModel):
    """The definition (usually SQL) behind a view. Pair with `subTypes: View`."""

    viewLogic: str = Field(description="The view's definition, e.g. its SELECT statement.")
    viewLanguage: str = Field(default="SQL", description="e.g. 'SQL'.")
    materialized: bool = Field(default=False, description="True for a materialized view.")
    formattedViewLogic: Optional[str] = Field(
        default=None, description="Optional pretty-printed/formatted version of viewLogic."
    )


class FineGrainedLineageDoc(BaseModel):
    """A single column-level lineage edge."""

    upstream: Optional[DatasetFieldRef] = Field(
        default=None,
        description="Source column. Absent for e.g. operation: CONSTANT, where the downstream "
        "value is a literal with no source column.",
    )
    downstream: DatasetFieldRef
    operation: Optional[str] = Field(default=None, description="Free-text transform description, e.g. IDENTITY, CONSTANT.")
    confidence: Optional[float] = 1.0


class UpstreamEntryDoc(BaseModel):
    dataset: DatasetRef


class UpstreamLineageDoc(BaseModel):
    """Table-level and (optionally) column-level lineage for a dataset."""

    upstreams: List[UpstreamEntryDoc] = Field(default_factory=list, description="Upstream (source) datasets.")
    fineGrainedLineages: Optional[List[FineGrainedLineageDoc]] = Field(
        default=None, description="Column-level lineage edges."
    )


class DataPlatformDoc(BaseModel):
    """Registers a custom data platform (e.g. one not built into DataHub's
    core platform list). Not needed for well-known platforms like `postgres`
    or `duckdb` -- only for platforms DataHub doesn't already know about."""

    kind: Literal["DATA_PLATFORM"]
    name: str = Field(description="Platform identifier, e.g. 'pathling'. Becomes urn:li:dataPlatform:<name>.")
    displayName: Optional[str] = None
    type: str = Field(default="OTHERS", description="One of DataHub's PlatformType enum values, e.g. RELATIONAL_DB, OTHERS.")
    logoUrl: Optional[str] = None
    datasetNameDelimiter: str = "."


class TagDoc(BaseModel):
    """A tag definition. Referenced elsewhere via `tags: [<name>]`."""

    kind: Literal["TAG"]
    name: str
    description: Optional[str] = None


class GlossaryNodeDoc(BaseModel):
    """A glossary category/folder that groups related glossary terms."""

    kind: Literal["GLOSSARY_NODE"]
    id: str = Field(description="Stable identifier, becomes urn:li:glossaryNode:<id>. Referenced via 'parentNode'.")
    name: str
    definition: Optional[str] = None
    parentNode: Optional[str] = Field(default=None, description="id of a parent GLOSSARY_NODE, for nested categories.")


class GlossaryTermDoc(BaseModel):
    """A glossary term. Referenced elsewhere via `glossaryTerms: [<id>]`."""

    kind: Literal["GLOSSARY_TERM"]
    id: str = Field(description="Stable identifier, becomes urn:li:glossaryTerm:<id>.")
    name: str
    definition: Optional[str] = None
    parentNode: Optional[str] = Field(default=None, description="id of the GLOSSARY_NODE this term belongs to.")


class AllowedValueDoc(BaseModel):
    value: Any
    description: Optional[str] = None


class StructuredPropertySettingsDoc(BaseModel):
    showInAssetSummary: Optional[bool] = None
    showInSearchFilters: Optional[bool] = None
    showInColumnsTable: Optional[bool] = None
    showAsAssetBadge: Optional[bool] = None
    isHidden: Optional[bool] = None


class StructuredPropertyDoc(BaseModel):
    """A custom structured property definition (a typed, filterable field
    attachable to datasets/data products/etc, beyond built-in DataHub fields).
    """

    kind: Literal["STRUCTURED_PROPERTY"]
    qualifiedName: str = Field(description="Globally unique dotted name, e.g. 'org.example.legalBasis'.")
    displayName: Optional[str] = None
    description: Optional[str] = None
    cardinality: str = Field(default="SINGLE", description="SINGLE or MULTIPLE values allowed per entity.")
    valueType: str = Field(description="One of DataHub's data types: string, number, date, rich_text, urn, ...")
    allowedValues: Optional[List[AllowedValueDoc]] = Field(
        default=None, description="Restrict to an enum of allowed values; omit to allow any value."
    )
    entityTypes: List[str] = Field(
        default_factory=list,
        description="Which entity types this property can be attached to, e.g. [dataset, dataProduct].",
    )
    typeQualifier: Optional[List[str]] = Field(
        default=None,
        description="For valueType 'urn': list of allowed target entity-type URNs "
        "(e.g. 'urn:li:entityType:datahub.dataProduct'). Maps to the 'allowedTypes' qualifier.",
    )
    settings: Optional[StructuredPropertySettingsDoc] = Field(
        default=None, description="Where this property is surfaced in the DataHub UI."
    )


class DomainDoc(BaseModel):
    """A business domain, used to group related datasets/data products.
    Referenced elsewhere via `domains: <id>`."""

    kind: Literal["DOMAIN"]
    id: str = Field(description="Stable identifier, becomes urn:li:domain:<id>.")
    name: str
    description: Optional[str] = None


class ApplicationDoc(BaseModel):
    """A source application/system (e.g. an EHR, an ERP). Referenced elsewhere
    via `applications: [<id>]`."""

    kind: Literal["APPLICATION"]
    id: str = Field(description="Stable identifier, becomes urn:li:application:<id>.")
    name: str
    description: Optional[str] = None


class ContainerDoc(ContainerRef):
    """A container (database, schema, bucket, ...). Emitted with parents
    before children automatically, regardless of declaration order across
    files. See `ContainerRef` for how the URN is computed."""

    kind: Literal["CONTAINER"]
    name: str
    description: Optional[str] = None
    externalUrl: Optional[str] = None
    parentContainer: Optional[ContainerRef] = Field(
        default=None, description="Reference to the parent container, if any (e.g. a schema's parent database)."
    )
    subTypes: Optional[SubTypesField] = Field(default=None, description="e.g. 'Database', 'Schema', 'S3_BUCKET'.")
    owners: Optional[OwnersField] = None
    tags: Optional[StringList] = None
    properties: Optional[Dict[str, Any]] = None


class DatasetDoc(BaseModel):
    """A dataset (table, view, topic, file, ...)."""

    model_config = ConfigDict(populate_by_name=True)

    kind: Literal["DATASET"]
    name: str
    platform: str
    env: str = "PROD"
    instance: Optional[str] = None
    displayName: Optional[str] = None
    description: Optional[str] = None
    container: Optional[ContainerRef] = Field(default=None, description="The dataset's parent container.")
    schema_block: Optional[SchemaBlock] = Field(default=None, alias="schema")
    properties: Optional[Dict[str, Any]] = None
    subTypes: Optional[SubTypesField] = Field(default=None, description="e.g. 'Table', 'View', 'Topic'.")
    tags: Optional[StringList] = None
    glossaryTerms: Optional[StringList] = None
    owners: Optional[OwnersField] = None
    domains: Optional[str] = None
    externalUrl: Optional[str] = None
    upstreamLineage: Optional[UpstreamLineageDoc] = None
    viewProperties: Optional[ViewPropertiesDoc] = Field(
        default=None,
        description="For views: the view's SQL definition. Set subTypes: View alongside it. "
        "No lineage is inferred from viewLogic -- declare upstreamLineage explicitly if needed.",
    )
    applications: Optional[StringList] = Field(
        default=None, description="ids of the APPLICATION documents this dataset belongs to."
    )


class DataProductDoc(BaseModel):
    """A data product: a curated bundle of datasets/jobs presented as a
    single discoverable asset, with its own domain/tags/owners."""

    kind: Literal["DATA_PRODUCT"]
    id: str = Field(description="Stable identifier, becomes urn:li:dataProduct:<id>.")
    name: str
    description: Optional[str] = None
    domains: Optional[str] = None
    glossaryTerms: Optional[StringList] = None
    tags: Optional[StringList] = None
    owners: Optional[OwnersField] = None
    structuredProperties: Optional[Dict[str, Any]] = Field(
        default=None, description="Map of structuredProperty qualifiedName -> value (or list of values)."
    )
    assets: Optional[List[str]] = Field(
        default=None, description="Full URNs of the entities (datasets, dataJobs, ...) that make up this product."
    )


class DataFlowDoc(BaseModel):
    """A pipeline (e.g. an Airflow DAG, a dbt project run)."""

    kind: Literal["DATA_FLOW"]
    orchestrator: str = Field(description="e.g. 'airflow', 'dbt'. Becomes part of the dataFlow URN.")
    flowId: str
    cluster: str = Field(default="PROD", description="Deployment/cluster identifier, part of the dataFlow URN.")
    name: str
    description: Optional[str] = None
    project: Optional[str] = None
    externalUrl: Optional[str] = None
    domains: Optional[str] = None
    owners: Optional[OwnersField] = None
    tags: Optional[StringList] = None


class DataFlowRef(BaseModel):
    """Reference to a DATA_FLOW by its natural (orchestrator, flowId, cluster) key."""

    orchestrator: str
    flowId: str
    cluster: str = "PROD"


class DataJobDoc(BaseModel):
    """A task within a pipeline (DATA_FLOW)."""

    kind: Literal["DATA_JOB"]
    jobId: str
    dataFlow: DataFlowRef = Field(description="Reference to the parent DATA_FLOW this task belongs to.")
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    inputDatasets: Optional[List[DatasetRef]] = None
    outputDatasets: Optional[List[DatasetRef]] = None
    fineGrainedLineages: Optional[List[FineGrainedLineageDoc]] = Field(
        default=None, description="Column-level lineage edges from inputDatasets to outputDatasets."
    )
    owners: Optional[OwnersField] = None
    tags: Optional[StringList] = None


class DataFlowJobRef(DataFlowRef):
    """Reference to a DATA_JOB by its natural (orchestrator, flowId, cluster, jobId) key."""

    jobId: str


class CreatedDoc(BaseModel):
    timestampMillis: int
    actor: Optional[str] = Field(default=None, description="Owner name; converted to a corpuser URN if not already one.")


class RunEventDoc(BaseModel):
    status: str = Field(description="e.g. STARTED, COMPLETE, FAILURE.")
    timestampMillis: int
    attempt: Optional[int] = None


class DataProcessInstanceDoc(BaseModel):
    """A single run of a DATA_JOB, with its own run-event history. For
    ongoing/incremental run events after the initial run, prefer an
    `aspectName: DATA_PROCESS_INSTANCE_RUN_EVENT` raw-aspect document instead
    of appending to `runEvents` here."""

    kind: Literal["DATA_PROCESS_INSTANCE"]
    id: str = Field(description="Stable identifier, becomes urn:li:dataProcessInstance:<id>.")
    name: str
    type: str = "BATCH_SCHEDULED"
    externalUrl: Optional[str] = None
    created: CreatedDoc
    parentTemplate: DataFlowJobRef = Field(description="Reference to the DATA_JOB this is a run of.")
    inputs: Optional[List[DatasetRef]] = None
    outputs: Optional[List[DatasetRef]] = None
    runEvents: Optional[Annotated[List[RunEventDoc], BeforeValidator(_coerce_to_list)]] = None


class AssertionPropertiesDoc(BaseModel):
    name: str
    dbt_test: Optional[str] = None


class AssertionAssertionDoc(BaseModel):
    """Union of the FRESHNESS / SQL / FIELD assertion shapes, kept flat.

    Only the fields relevant to `type` will be populated by the author; the
    assertion builder picks which ones to read based on `type`.
    """

    type: str = Field(description="FRESHNESS, SQL, or FIELD -- selects which fields below apply.")
    entityUrn: str = Field(description="Full URN of the dataset this assertion checks.")

    # FRESHNESS
    freshnessType: Optional[str] = Field(default=None, description="[FRESHNESS] e.g. DATASET_CHANGE.")
    scheduleType: Optional[str] = Field(default=None, description="[FRESHNESS] e.g. CRON.")
    cron: Optional[str] = Field(default=None, description="[FRESHNESS] cron expression, if scheduleType is CRON.")
    timezone: Optional[str] = Field(default=None, description="[FRESHNESS] IANA timezone for the cron schedule.")

    # SQL
    sqlType: Optional[str] = Field(default=None, description="[SQL] e.g. METRIC.")
    statement: Optional[str] = Field(default=None, description="[SQL] the SQL query to evaluate.")
    operator: Optional[str] = Field(default=None, description="[SQL/FIELD] e.g. GREATER_THAN, EQUAL_TO, NOT_NULL.")
    value: Optional[Any] = Field(default=None, description="[SQL] the comparison value for 'operator'.")
    changeType: Optional[str] = Field(default=None, description="[SQL] e.g. ABSOLUTE, PERCENTAGE.")

    # FIELD
    fieldType: Optional[str] = Field(default=None, description="[FIELD] FIELD_METRIC or FIELD_VALUES.")
    fieldPath: Optional[str] = Field(default=None, description="[FIELD] the column this assertion checks.")
    dataType: Optional[str] = Field(default=None, description="[FIELD] the column's DataHub schema type.")
    nativeDataType: Optional[str] = Field(default=None, description="[FIELD] the column's native source type.")
    metric: Optional[str] = Field(default=None, description="[FIELD, FIELD_METRIC] e.g. UNIQUE_PERCENTAGE.")
    metricOperator: Optional[str] = Field(default=None, description="[FIELD, FIELD_METRIC] comparison operator for 'metric'.")
    metricValue: Optional[Any] = Field(default=None, description="[FIELD, FIELD_METRIC] the comparison value.")
    excludeNulls: Optional[bool] = Field(default=None, description="[FIELD, FIELD_VALUES] ignore nulls when checking 'operator'.")


class AssertionDoc(BaseModel):
    """A data quality assertion (freshness, SQL-based, or field-level check)."""

    kind: Literal["ASSERTION"]
    id: str = Field(description="Stable identifier, becomes urn:li:assertion:<id>.")
    description: Optional[str] = None
    sourceType: str = "NATIVE"
    properties: Optional[AssertionPropertiesDoc] = None
    assertion: AssertionAssertionDoc


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
    """

    model_config = ConfigDict(extra="allow")

    aspectName: str
    dataset: Optional[DatasetRef] = None
    assertionUrn: Optional[str] = None
    dataProcessInstanceUrn: Optional[str] = None


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
    "DATA_PRODUCT": DataProductDoc,
    "DATA_FLOW": DataFlowDoc,
    "DATA_JOB": DataJobDoc,
    "DATA_PROCESS_INSTANCE": DataProcessInstanceDoc,
    "ASSERTION": AssertionDoc,
}

EntityDoc = Union[
    DataPlatformDoc,
    TagDoc,
    GlossaryNodeDoc,
    GlossaryTermDoc,
    StructuredPropertyDoc,
    DomainDoc,
    ApplicationDoc,
    ContainerDoc,
    DatasetDoc,
    DataProductDoc,
    DataFlowDoc,
    DataJobDoc,
    DataProcessInstanceDoc,
    AssertionDoc,
]

ParsedDoc = Union[EntityDoc, RawAspectDoc]


class DocumentParseError(ValueError):
    """Raised when a YAML document doesn't match any known kind/aspectName shape."""


def parse_document(raw: Dict[str, Any]) -> ParsedDoc:
    """Dispatch a raw YAML document dict to the correct Pydantic model."""
    if not isinstance(raw, dict):
        raise DocumentParseError(f"Expected a YAML mapping document, got {type(raw)}")

    kind = raw.get("kind")
    if kind is not None:
        model_cls = ENTITY_DOC_TYPES_BY_KIND.get(kind)
        if model_cls is None:
            raise DocumentParseError(
                f"Unknown kind '{kind}'. Supported kinds: "
                f"{sorted(ENTITY_DOC_TYPES_BY_KIND)}"
            )
        return model_cls.model_validate(raw)

    if "aspectName" in raw:
        return RawAspectDoc.model_validate(raw)

    raise DocumentParseError(
        "Document has neither a 'kind' nor an 'aspectName' field; cannot determine its type."
    )
