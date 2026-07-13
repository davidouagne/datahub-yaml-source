from typing import Iterable

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    AssertionInfoClass,
    AssertionStdParameterClass,
    AssertionStdParametersClass,
    FieldAssertionInfoClass,
    FieldMetricAssertionClass,
    FieldValuesAssertionClass,
    FieldValuesFailThresholdClass,
    FreshnessAssertionInfoClass,
    FreshnessAssertionScheduleClass,
    FreshnessCronScheduleClass,
    SchemaFieldSpecClass,
    SqlAssertionInfoClass,
)
from datahub.metadata.urns import AssertionUrn

from datahub_yaml_source.builders.common import mcp_workunit
from datahub_yaml_source.models import AssertionDoc


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


_BUILDERS = {
    "FRESHNESS": (_build_freshness_assertion, "freshnessAssertion"),
    "SQL": (_build_sql_assertion, "sqlAssertion"),
    "FIELD": (_build_field_assertion, "fieldAssertion"),
}


def build_assertion(doc: AssertionDoc) -> Iterable[MetadataWorkUnit]:
    builder = _BUILDERS.get(doc.assertion.type)
    if builder is None:
        raise ValueError(
            f"Unsupported assertion type '{doc.assertion.type}' for assertion '{doc.id}'. "
            f"Supported types: {sorted(_BUILDERS)}"
        )
    build_fn, kwarg_name = builder
    sub_assertion = build_fn(doc)

    aspect = AssertionInfoClass(
        type=doc.assertion.type,
        description=doc.description,
        **{kwarg_name: sub_assertion},
    )

    yield mcp_workunit(AssertionUrn(doc.id).urn(), aspect)
