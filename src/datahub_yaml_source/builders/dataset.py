from collections.abc import Iterable

from datahub.emitter.mce_builder import make_schema_field_urn
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    DatasetLineageTypeClass,
    ForeignKeyConstraintClass,
    OtherSchemaClass,
    SchemaFieldClass,
    SchemaMetadataClass,
    UpstreamClass,
    UpstreamLineageClass,
    ViewPropertiesClass,
)
from datahub.sdk.dataset import Dataset

from datahub_yaml_source.builders.common import (
    build_fine_grained_lineage_list,
    common_aspect_mcps,
    common_sdk_kwargs,
    schema_field_data_type,
    stringify_custom_properties,
)
from datahub_yaml_source.models import (
    DatasetDoc,
    ForeignKeyDoc,
    SchemaBlock,
    SchemaFieldDoc,
    UpstreamLineageDoc,
    ViewPropertiesDoc,
)
from datahub_yaml_source.urns import ReferenceIndex, container_key, data_platform_urn, dataset_urn
from datahub_yaml_source.yaml_source_report import YamlSourceReport


def _build_schema_field(field_doc: SchemaFieldDoc) -> SchemaFieldClass:
    return SchemaFieldClass(
        fieldPath=field_doc.fieldPath,
        type=schema_field_data_type(field_doc.type),
        nativeDataType=field_doc.nativeDataType or field_doc.type,
        description=field_doc.description,
        nullable=bool(field_doc.nullable) if field_doc.nullable is not None else False,
        isPartOfKey=field_doc.partOfKey,
    )


def _build_foreign_key(fk: ForeignKeyDoc) -> ForeignKeyConstraintClass:
    return ForeignKeyConstraintClass(
        name=fk.name,
        sourceFields=[make_schema_field_urn(dataset_urn(f), f.fieldPath) for f in fk.sourceFields],
        foreignFields=[
            make_schema_field_urn(dataset_urn(f), f.fieldPath) for f in fk.foreignFields
        ],
        foreignDataset=dataset_urn(fk.foreignDataset),
    )


def build_schema_metadata(
    name: str, platform: str, schema_block: SchemaBlock
) -> SchemaMetadataClass:
    return SchemaMetadataClass(
        schemaName=name,
        platform=data_platform_urn(platform),
        version=0,
        hash="",
        platformSchema=OtherSchemaClass(rawSchema=""),
        fields=[_build_schema_field(f) for f in schema_block.fields],
        foreignKeys=(
            [_build_foreign_key(fk) for fk in schema_block.foreignKeys]
            if schema_block.foreignKeys
            else None
        ),
    )


def build_upstream_lineage(doc: UpstreamLineageDoc) -> UpstreamLineageClass:
    upstreams = [
        UpstreamClass(dataset=dataset_urn(entry.dataset), type=DatasetLineageTypeClass.TRANSFORMED)
        for entry in doc.upstreams
    ]

    fine_grained = build_fine_grained_lineage_list(doc.fineGrainedLineages)

    return UpstreamLineageClass(upstreams=upstreams, fineGrainedLineages=fine_grained)


def build_view_properties(doc: ViewPropertiesDoc) -> ViewPropertiesClass:
    return ViewPropertiesClass(
        materialized=doc.materialized,
        viewLogic=doc.viewLogic,
        viewLanguage=doc.viewLanguage,
        formattedViewLogic=doc.formattedViewLogic,
    )


def build_dataset(
    doc: DatasetDoc, index: ReferenceIndex, report: YamlSourceReport
) -> Iterable[MetadataWorkUnit]:
    context = f"DATASET '{doc.name}'"
    common = common_sdk_kwargs(doc, index, report, context)

    parent_container = None
    if doc.container is not None:
        if not index.has_container(doc.container):
            report.report_dangling_reference(
                f"{context} references an undeclared container "
                f"(platform={doc.container.platform}, database={doc.container.database}, "
                f"schema={doc.container.schema_name})"
            )
        parent_container = container_key(doc.container)

    schema_metadata = None
    if doc.schema_block is not None:
        schema_metadata = build_schema_metadata(doc.name, doc.platform, doc.schema_block)

    upstreams = build_upstream_lineage(doc.upstreamLineage) if doc.upstreamLineage else None

    dataset = Dataset(
        platform=doc.platform,
        name=doc.name,
        platform_instance=doc.instance,
        env=doc.env,
        description=doc.description,
        display_name=doc.displayName,
        external_url=doc.externalUrl,
        custom_properties=stringify_custom_properties(doc.properties),
        parent_container=parent_container,
        schema=schema_metadata,
        upstreams=upstreams,
        view_definition=(build_view_properties(doc.viewProperties) if doc.viewProperties else None),
        parse_view_lineage=False,
        **common,
    )
    yield from dataset.as_workunits()

    # Column-level metadata (Phase 3): tags/glossaryTerms/deprecation/
    # structuredProperties on an individual schema.fields[] entry, emitted on
    # the schemaField entity URN -- never editableSchemaMetadata, which is
    # UI-owned. Emitted after the dataset's own workunits above so the field
    # already exists (via schemaMetadata) when these annotations land.
    if doc.schema_block is not None:
        entity_urn = dataset_urn(doc)
        for field in doc.schema_block.fields:
            field_urn = make_schema_field_urn(entity_urn, field.fieldPath)
            field_context = f"{context} field '{field.fieldPath}'"
            yield from common_aspect_mcps(field_urn, field, index, report, field_context)
