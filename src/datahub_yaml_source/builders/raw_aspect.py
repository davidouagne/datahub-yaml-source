"""Builders for `aspectName:`-keyed raw aspect passthrough documents.

Each supported `aspectName` gets its own small builder function, registered in
`_BUILDERS` below. A single fully-generic `AspectClass(**raw_dict)` constructor
would silently produce broken output for any aspect with nested object fields
(e.g. `DatasetProfile.fieldProfiles`, which needs real `DatasetFieldProfileClass`
instances, not plain dicts) -- DataHub's generated aspect classes don't do that
coercion themselves. So instead of one generic mechanism, this module is a
small, extensible registry: add a new `_build_<aspect>` function and register
it to support another aspect.
"""

from typing import Any, Dict, Iterable, List, Optional

from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    AssertionResultClass,
    AssertionRunEventClass,
    DataProcessInstanceRunEventClass,
    DataProcessInstanceRunResultClass,
    DatasetFieldProfileClass,
    DatasetFieldUsageCountsClass,
    DatasetProfileClass,
    DatasetUsageStatisticsClass,
    DatasetUserUsageCountsClass,
    OperationClass,
    PartitionSpecClass,
    TimeWindowSizeClass,
    ValueFrequencyClass,
)

from datahub_yaml_source.builders.common import mcp_workunit
from datahub_yaml_source.models import DatasetRef, RawAspectDoc
from datahub_yaml_source.urns import dataset_urn, owner_urn


def _build_field_profile(raw: Dict[str, Any]) -> DatasetFieldProfileClass:
    distinct_value_frequencies = None
    if raw.get("distinctValueFrequencies"):
        distinct_value_frequencies = [
            ValueFrequencyClass(value=str(v["value"]), frequency=v["frequency"])
            for v in raw["distinctValueFrequencies"]
        ]
    return DatasetFieldProfileClass(
        fieldPath=raw["fieldPath"],
        uniqueCount=raw.get("uniqueCount"),
        uniqueProportion=raw.get("uniqueProportion"),
        nullCount=raw.get("nullCount"),
        nullProportion=raw.get("nullProportion"),
        min=raw.get("min"),
        max=raw.get("max"),
        sampleValues=raw.get("sampleValues"),
        distinctValueFrequencies=distinct_value_frequencies,
    )


def _build_event_granularity(raw: Optional[Dict[str, Any]]) -> Optional[TimeWindowSizeClass]:
    if not raw:
        return None
    return TimeWindowSizeClass(unit=raw["unit"], multiple=raw.get("multiple"))


def _build_partition_spec(raw: Optional[Dict[str, Any]]) -> Optional[PartitionSpecClass]:
    if not raw:
        return None
    return PartitionSpecClass(partition=raw["partition"], type=raw.get("type"))


def _build_dataset_profile(payload: Dict[str, Any]) -> DatasetProfileClass:
    field_profiles: Optional[List[DatasetFieldProfileClass]] = None
    if payload.get("fieldProfiles"):
        field_profiles = [_build_field_profile(f) for f in payload["fieldProfiles"]]

    return DatasetProfileClass(
        timestampMillis=payload["timestampMillis"],
        eventGranularity=_build_event_granularity(payload.get("eventGranularity")),
        partitionSpec=_build_partition_spec(payload.get("partitionSpec")),
        messageId=payload.get("messageId"),
        rowCount=payload.get("rowCount"),
        columnCount=payload.get("columnCount"),
        sizeInBytes=payload.get("sizeInBytes"),
        fieldProfiles=field_profiles,
    )


def _build_operation(payload: Dict[str, Any]) -> OperationClass:
    affected_datasets = None
    if payload.get("affectedDatasets"):
        affected_datasets = [
            dataset_urn(DatasetRef.model_validate(d)) for d in payload["affectedDatasets"]
        ]

    return OperationClass(
        timestampMillis=payload["timestampMillis"],
        operationType=payload["operationType"],
        lastUpdatedTimestamp=payload["lastUpdatedTimestamp"],
        eventGranularity=_build_event_granularity(payload.get("eventGranularity")),
        partitionSpec=_build_partition_spec(payload.get("partitionSpec")),
        messageId=payload.get("messageId"),
        actor=owner_urn(payload["actor"]) if payload.get("actor") else None,
        customOperationType=payload.get("customOperationType"),
        numAffectedRows=payload.get("numAffectedRows"),
        affectedDatasets=affected_datasets,
        sourceType=payload.get("sourceType"),
        customProperties=payload.get("customProperties"),
        queries=payload.get("queries"),
    )


def _build_dataset_usage_statistics(payload: Dict[str, Any]) -> DatasetUsageStatisticsClass:
    user_counts = None
    if payload.get("userCounts"):
        user_counts = [
            DatasetUserUsageCountsClass(
                user=u["user"], count=u["count"], userEmail=u.get("userEmail")
            )
            for u in payload["userCounts"]
        ]

    field_counts = None
    if payload.get("fieldCounts"):
        field_counts = [
            DatasetFieldUsageCountsClass(fieldPath=f["fieldPath"], count=f["count"])
            for f in payload["fieldCounts"]
        ]

    return DatasetUsageStatisticsClass(
        timestampMillis=payload["timestampMillis"],
        eventGranularity=_build_event_granularity(payload.get("eventGranularity")),
        partitionSpec=_build_partition_spec(payload.get("partitionSpec")),
        messageId=payload.get("messageId"),
        uniqueUserCount=payload.get("uniqueUserCount"),
        totalSqlQueries=payload.get("totalSqlQueries"),
        topSqlQueries=payload.get("topSqlQueries"),
        userCounts=user_counts,
        fieldCounts=field_counts,
    )


def _build_assertion_run_event(payload: Dict[str, Any], assertion_urn: str) -> AssertionRunEventClass:
    result = None
    if payload.get("result"):
        result = AssertionResultClass(
            type=payload["result"]["type"],
            nativeResults=payload["result"].get("nativeResults"),
        )

    return AssertionRunEventClass(
        timestampMillis=payload["timestampMillis"],
        runId=payload["runId"],
        asserteeUrn=payload["asserteeUrn"],
        assertionUrn=assertion_urn,
        # Not present in the source YAML today; an event carrying a `result`
        # is by definition complete.
        status=payload.get("status", "COMPLETE"),
        result=result,
        partitionSpec=_build_partition_spec(payload.get("partitionSpec")),
    )


def _build_data_process_instance_run_event(
    payload: Dict[str, Any],
) -> DataProcessInstanceRunEventClass:
    result = None
    if payload.get("result"):
        result = DataProcessInstanceRunResultClass(
            type=payload["result"]["type"],
            nativeResultType=payload["result"].get("nativeResultType"),
        )

    return DataProcessInstanceRunEventClass(
        timestampMillis=payload["timestampMillis"],
        status=payload["status"],
        attempt=payload.get("attempt"),
        durationMillis=payload.get("durationMillis"),
        result=result,
        partitionSpec=_build_partition_spec(payload.get("partitionSpec")),
    )


_DATASET_SCOPED_BUILDERS = {
    "DATASET_PROFILE": _build_dataset_profile,
    "OPERATION": _build_operation,
    "DATASET_USAGE_STATISTICS": _build_dataset_usage_statistics,
}

_ASSERTION_SCOPED_BUILDERS = {
    "ASSERTION_RUN_EVENT": _build_assertion_run_event,
}

_DATA_PROCESS_INSTANCE_SCOPED_BUILDERS = {
    "DATA_PROCESS_INSTANCE_RUN_EVENT": _build_data_process_instance_run_event,
}


def build_raw_aspect(doc: RawAspectDoc) -> Iterable[MetadataWorkUnit]:
    payload = doc.model_extra or {}

    if doc.aspectName in _DATASET_SCOPED_BUILDERS:
        if doc.dataset is None:
            raise ValueError(
                f"Raw aspect document for '{doc.aspectName}' is missing a 'dataset:' "
                "entity reference."
            )
        entity_urn = dataset_urn(doc.dataset)
        aspect = _DATASET_SCOPED_BUILDERS[doc.aspectName](payload)
    elif doc.aspectName in _ASSERTION_SCOPED_BUILDERS:
        if doc.assertionUrn is None:
            raise ValueError(
                f"Raw aspect document for '{doc.aspectName}' is missing an "
                "'assertionUrn:' entity reference."
            )
        entity_urn = doc.assertionUrn
        aspect = _ASSERTION_SCOPED_BUILDERS[doc.aspectName](payload, doc.assertionUrn)
    elif doc.aspectName in _DATA_PROCESS_INSTANCE_SCOPED_BUILDERS:
        if doc.dataProcessInstanceUrn is None:
            raise ValueError(
                f"Raw aspect document for '{doc.aspectName}' is missing a "
                "'dataProcessInstanceUrn:' entity reference."
            )
        entity_urn = doc.dataProcessInstanceUrn
        aspect = _DATA_PROCESS_INSTANCE_SCOPED_BUILDERS[doc.aspectName](payload)
    else:
        supported = sorted(
            {
                *_DATASET_SCOPED_BUILDERS,
                *_ASSERTION_SCOPED_BUILDERS,
                *_DATA_PROCESS_INSTANCE_SCOPED_BUILDERS,
            }
        )
        raise ValueError(f"Unsupported raw aspectName '{doc.aspectName}'. Supported: {supported}")

    yield mcp_workunit(entity_urn, aspect)
