import re
from typing import Iterable, Optional

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    AssertionActionClass,
    AssertionActionsClass,
    AssertionInfoClass,
    AssertionNoteClass,
    AssertionStdParameterClass,
    AssertionStdParametersClass,
    AuditStampClass,
    CustomAssertionInfoClass,
    FieldAssertionInfoClass,
    FieldMetricAssertionClass,
    FieldValuesAssertionClass,
    FieldValuesFailThresholdClass,
    FreshnessAssertionInfoClass,
    FreshnessAssertionScheduleClass,
    FreshnessCronScheduleClass,
    OtherSchemaClass,
    RowCountChangeClass,
    RowCountTotalClass,
    SchemaAssertionInfoClass,
    SchemaFieldClass,
    SchemaFieldSpecClass,
    SchemaMetadataClass,
    SqlAssertionInfoClass,
    VolumeAssertionInfoClass,
)
from datahub.metadata.urns import AssertionUrn

from datahub_yaml_source.builders.common import (
    DEFAULT_ACTOR_URN,
    common_aspect_mcps,
    mcp_workunit,
    schema_field_data_type,
)
from datahub_yaml_source.models import AssertionActionsDoc, AssertionDoc
from datahub_yaml_source.urns import ReferenceIndex
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _build_freshness_assertion(doc: AssertionDoc) -> FreshnessAssertionInfoClass:
    a = doc.assertion
    schedule = FreshnessAssertionScheduleClass(
        type=a.scheduleType or "CRON",
        cron=FreshnessCronScheduleClass(cron=a.cron or "", timezone=a.timezone or "UTC"),
    )
    return FreshnessAssertionInfoClass(
        type=a.freshnessType or "DATASET_CHANGE", entity=a.entityUrn, schedule=schedule
    )


def _build_sql_assertion(doc: AssertionDoc) -> SqlAssertionInfoClass:
    a = doc.assertion
    return SqlAssertionInfoClass(
        type=a.sqlType or "METRIC",
        entity=a.entityUrn,
        statement=a.statement or "",
        operator=a.operator or "GREATER_THAN",
        parameters=AssertionStdParametersClass(
            value=AssertionStdParameterClass(value=str(a.value), type="NUMBER")
        ),
        changeType=a.changeType,
    )


def _build_field_assertion(doc: AssertionDoc) -> FieldAssertionInfoClass:
    a = doc.assertion
    field_spec = SchemaFieldSpecClass(
        path=a.fieldPath or "",
        type=a.dataType or "STRING",
        nativeType=a.nativeDataType or "",
    )

    field_values_assertion = None
    field_metric_assertion = None
    if a.fieldType == "FIELD_METRIC":
        field_metric_assertion = FieldMetricAssertionClass(
            field=field_spec,
            metric=a.metric or "UNIQUE_PERCENTAGE",
            operator=a.metricOperator or "EQUAL_TO",
            parameters=(
                AssertionStdParametersClass(
                    value=AssertionStdParameterClass(value=str(a.metricValue), type="NUMBER")
                )
                if a.metricValue is not None
                else None
            ),
        )
    else:
        field_values_assertion = FieldValuesAssertionClass(
            field=field_spec,
            operator=a.operator or "NOT_NULL",
            failThreshold=FieldValuesFailThresholdClass(type="COUNT", value=0),
            excludeNulls=a.excludeNulls,
        )

    return FieldAssertionInfoClass(
        type=a.fieldType or "FIELD_VALUES",
        entity=a.entityUrn,
        fieldValuesAssertion=field_values_assertion,
        fieldMetricAssertion=field_metric_assertion,
    )


_DATASET_URN_PLATFORM_RE = re.compile(r"^urn:li:dataset:\((?P<platform>urn:li:dataPlatform:[^,]+),")


def _platform_urn_from_dataset_urn(entity_urn: str) -> str:
    match = _DATASET_URN_PLATFORM_RE.match(entity_urn)
    return match.group("platform") if match else "urn:li:dataPlatform:unknown"


def _build_volume_assertion(doc: AssertionDoc) -> VolumeAssertionInfoClass:
    a = doc.assertion
    if a.value is None:
        raise ValueError(f"VOLUME assertion '{doc.id}' is missing a 'value' to compare against.")
    # `RowCountTotalClass.parameters` / `RowCountChangeClass.parameters` are
    # required in the Avro schema despite the generated stub typing them
    # Optional -- passing None parses fine but fails MCP validation at emit
    # time (same trap as `DeprecationClass.note`, see build_deprecation_aspect()).
    parameters = AssertionStdParametersClass(value=AssertionStdParameterClass(value=str(a.value), type="NUMBER"))
    if a.volumeType == "ROW_COUNT_CHANGE":
        return VolumeAssertionInfoClass(
            type="ROW_COUNT_CHANGE",
            entity=a.entityUrn,
            rowCountChange=RowCountChangeClass(
                type=a.changeType or "ABSOLUTE",
                operator=a.operator or "GREATER_THAN_OR_EQUAL_TO",
                parameters=parameters,
            ),
        )
    return VolumeAssertionInfoClass(
        type="ROW_COUNT_TOTAL",
        entity=a.entityUrn,
        rowCountTotal=RowCountTotalClass(
            operator=a.operator or "GREATER_THAN_OR_EQUAL_TO", parameters=parameters
        ),
    )


def _build_data_schema_assertion(doc: AssertionDoc) -> SchemaAssertionInfoClass:
    a = doc.assertion
    fields = [
        SchemaFieldClass(
            fieldPath=f.path,
            type=schema_field_data_type(f.type),
            nativeDataType=f.nativeType or f.type,
        )
        for f in (a.schemaFields or [])
    ]
    expected_schema = SchemaMetadataClass(
        schemaName=f"{doc.id}-expected-schema",
        platform=_platform_urn_from_dataset_urn(a.entityUrn),
        version=0,
        hash="",
        platformSchema=OtherSchemaClass(rawSchema=""),
        fields=fields,
    )
    return SchemaAssertionInfoClass(entity=a.entityUrn, schema=expected_schema, compatibility=a.compatibility)


def _build_custom_assertion(doc: AssertionDoc) -> CustomAssertionInfoClass:
    a = doc.assertion
    field_spec = (
        SchemaFieldSpecClass(path=a.fieldPath, type=a.dataType or "string", nativeType=a.nativeDataType or "")
        if a.fieldPath
        else None
    )
    return CustomAssertionInfoClass(
        type=a.customType or "CUSTOM", entity=a.entityUrn, field=field_spec, logic=a.logic or ""
    )


_BUILDERS = {
    "FRESHNESS": (_build_freshness_assertion, "freshnessAssertion"),
    "VOLUME": (_build_volume_assertion, "volumeAssertion"),
    "SQL": (_build_sql_assertion, "sqlAssertion"),
    "FIELD": (_build_field_assertion, "fieldAssertion"),
    "DATA_SCHEMA": (_build_data_schema_assertion, "schemaAssertion"),
    "CUSTOM": (_build_custom_assertion, "customAssertion"),
}


def _build_assertion_actions(actions: Optional[AssertionActionsDoc]) -> Optional[AssertionActionsClass]:
    if actions is None:
        return None
    return AssertionActionsClass(
        onSuccess=[AssertionActionClass(type=a.type) for a in (actions.onSuccess or [])] or None,
        onFailure=[AssertionActionClass(type=a.type) for a in (actions.onFailure or [])] or None,
    )


def build_assertion(
    doc: AssertionDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    builder = _BUILDERS.get(doc.assertion.type)
    if builder is None:
        raise ValueError(
            f"Unsupported assertion type '{doc.assertion.type}' for assertion '{doc.id}'. "
            f"Supported types: {sorted(_BUILDERS)}"
        )
    build_fn, kwarg_name = builder
    sub_assertion = build_fn(doc)

    entity_urn = AssertionUrn(doc.id).urn()

    aspect = AssertionInfoClass(
        type=doc.assertion.type,
        description=doc.description,
        **{kwarg_name: sub_assertion},
    )
    yield mcp_workunit(entity_urn, aspect)

    if doc.assertionNote:
        yield mcp_workunit(
            entity_urn,
            AssertionNoteClass(
                content=doc.assertionNote,
                lastModified=AuditStampClass(time=0, actor=DEFAULT_ACTOR_URN),
            ),
        )

    actions_aspect = _build_assertion_actions(doc.assertionActions)
    if actions_aspect:
        yield mcp_workunit(entity_urn, actions_aspect)

    yield from common_aspect_mcps(entity_urn, doc, index, report, f"ASSERTION '{doc.id}'")
