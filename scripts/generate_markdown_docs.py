"""Generate a human-readable Markdown field reference for the YAML
metadata-as-code document format, derived from the Pydantic models in
`datahub_yaml_source.models` -- the same source of truth as
`generate_json_schema.py`, so the two can never disagree.

Usage:
    python scripts/generate_markdown_docs.py
"""

from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Type, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from datahub_yaml_source.models import (
    AllowedValueDoc,
    ApplicationDoc,
    AssertionAssertionDoc,
    AssertionDoc,
    AssertionPropertiesDoc,
    ChartDoc,
    ChartRef,
    ContainerDoc,
    ContainerRef,
    CreatedDoc,
    DashboardDoc,
    DashboardRef,
    DataFlowDoc,
    DataFlowJobRef,
    DataFlowRef,
    DataJobDoc,
    DataPlatformDoc,
    DataProcessInstanceDoc,
    DataProductDoc,
    DatasetDoc,
    DatasetFieldRef,
    DatasetRef,
    DocumentDoc,
    DomainDoc,
    FineGrainedLineageDoc,
    ForeignKeyDoc,
    GlossaryNodeDoc,
    GlossaryTermDoc,
    IncidentDoc,
    IncidentSourceDoc,
    IncidentStatusDoc,
    CaveatDetailsDoc,
    CaveatsAndRecommendationsDoc,
    EthicalConsiderationsDoc,
    IntendedUseDoc,
    AiContextDoc,
    MetricDoc,
    MetricRef,
    MLFeatureDoc,
    MLFeatureRef,
    MLFeatureTableDoc,
    MLModelDataDoc,
    MLModelDoc,
    MLModelFactorDoc,
    MLModelFactorPromptsDoc,
    MLModelGroupDoc,
    MLModelGroupRef,
    MLModelMetricsDoc,
    MLModelSourceCodeDoc,
    MLPrimaryKeyDoc,
    MLPrimaryKeyRef,
    OwnerEntry,
    QueryDoc,
    QuerySubjectRef,
    RawAspectDoc,
    RunEventDoc,
    SchemaBlock,
    SchemaFieldDoc,
    SemanticModelDoc,
    SemanticModelRef,
    StructuredPropertyDoc,
    StructuredPropertySettingsDoc,
    TagDoc,
    UpstreamEntryDoc,
    UpstreamLineageDoc,
    ViewPropertiesDoc,
)

OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "sources" / "yaml" / "reference.md"

# One entry per `kind:` value, plus the `aspectName:` passthrough doc.
DOCUMENT_MODELS = [
    ("DATA_PLATFORM", DataPlatformDoc),
    ("TAG", TagDoc),
    ("GLOSSARY_NODE", GlossaryNodeDoc),
    ("GLOSSARY_TERM", GlossaryTermDoc),
    ("STRUCTURED_PROPERTY", StructuredPropertyDoc),
    ("DOMAIN", DomainDoc),
    ("APPLICATION", ApplicationDoc),
    ("CONTAINER", ContainerDoc),
    ("DATASET", DatasetDoc),
    ("CHART", ChartDoc),
    ("DASHBOARD", DashboardDoc),
    ("QUERY", QueryDoc),
    ("INCIDENT", IncidentDoc),
    ("DOCUMENT", DocumentDoc),
    ("MLFEATURE_TABLE", MLFeatureTableDoc),
    ("MLFEATURE", MLFeatureDoc),
    ("MLPRIMARY_KEY", MLPrimaryKeyDoc),
    ("MLMODEL_GROUP", MLModelGroupDoc),
    ("MLMODEL", MLModelDoc),
    ("SEMANTIC_MODEL", SemanticModelDoc),
    ("METRIC", MetricDoc),
    ("DATA_PRODUCT", DataProductDoc),
    ("DATA_FLOW", DataFlowDoc),
    ("DATA_JOB", DataJobDoc),
    ("DATA_PROCESS_INSTANCE", DataProcessInstanceDoc),
    ("ASSERTION", AssertionDoc),
    ("(aspectName: ...)", RawAspectDoc),
]

# Supporting types referenced by the document models above, documented once
# in their own section and linked to from every field table that uses them.
SUPPORTING_MODELS = [
    AllowedValueDoc,
    ContainerRef,
    ChartRef,
    DashboardRef,
    DatasetRef,
    QuerySubjectRef,
    IncidentStatusDoc,
    IncidentSourceDoc,
    MLFeatureRef,
    MLPrimaryKeyRef,
    MLModelGroupRef,
    IntendedUseDoc,
    CaveatDetailsDoc,
    EthicalConsiderationsDoc,
    CaveatsAndRecommendationsDoc,
    MLModelDataDoc,
    MLModelFactorDoc,
    MLModelFactorPromptsDoc,
    MLModelMetricsDoc,
    MLModelSourceCodeDoc,
    SemanticModelRef,
    MetricRef,
    AiContextDoc,
    DatasetFieldRef,
    SchemaBlock,
    SchemaFieldDoc,
    ForeignKeyDoc,
    UpstreamLineageDoc,
    UpstreamEntryDoc,
    FineGrainedLineageDoc,
    ViewPropertiesDoc,
    OwnerEntry,
    DataFlowRef,
    DataFlowJobRef,
    CreatedDoc,
    RunEventDoc,
    AssertionPropertiesDoc,
    AssertionAssertionDoc,
    StructuredPropertySettingsDoc,
]

ALL_MODELS = [m for _, m in DOCUMENT_MODELS] + SUPPORTING_MODELS
MODEL_ANCHORS = {m: m.__name__ for m in ALL_MODELS}


def _anchor(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-").replace(":", "").replace("(", "").replace(")", "").replace(".", "")


def _strip_annotated(annotation: Any) -> Any:
    if get_origin(annotation) is Annotated:
        return get_args(annotation)[0]
    return annotation


def _render_type(annotation: Any) -> str:
    annotation = _strip_annotated(annotation)
    origin = get_origin(annotation)

    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        rendered = [_render_type(a) for a in args]
        return " or ".join(dict.fromkeys(rendered))  # dedupe, preserve order

    if origin is Literal:
        values = get_args(annotation)
        return " | ".join(f'"{v}"' for v in values)

    if origin in (list, List):
        (item,) = get_args(annotation)
        return f"list of {_render_type(item)}"

    if origin in (dict, Dict):
        return "map"

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in MODEL_ANCHORS:
            name = MODEL_ANCHORS[annotation]
            return f"[{name}](#{_anchor(name)})"
        return annotation.__name__

    if annotation is Any:
        return "any"
    if annotation is str:
        return "string"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"

    return getattr(annotation, "__name__", str(annotation))


def _render_default(field: FieldInfo) -> str:
    if field.default is PydanticUndefined:
        return "-"
    if field.default is None:
        return "-"
    if field.default_factory is not None:
        return "-"
    return f"`{field.default}`"


# Field names contributed by the cross-cutting `Has*` mixins in models.py, in
# the canonical order they should render. Pydantic lists inherited fields
# before a class's own fields, which would otherwise bury `kind`/`name`/etc.
# under nine common fields on every single kind; render each kind's own
# fields first instead, with common ones broken out into their own rows below
# a divider so a kind's *distinctive* shape is what a reader sees first.
_COMMON_ASPECT_FIELD_ORDER = [
    "owners", "tags", "glossaryTerms", "domains", "applications",
    "links", "deprecation", "structuredProperties", "subTypes",
]


def _render_field_row(model: Type[BaseModel], py_name: str, field: FieldInfo) -> str:
    yaml_name = field.alias or py_name
    required = "**yes**" if field.is_required() else "no"
    type_str = _render_type(field.annotation)
    default = _render_default(field)
    description = (field.description or "").replace("\n", " ")
    return f"| `{yaml_name}` | {type_str} | {required} | {default} | {description} |"


def _render_field_table(model: Type[BaseModel]) -> str:
    header = ["| Field | Type | Required | Default | Description |", "| --- | --- | --- | --- | --- |"]
    all_fields = model.model_fields
    common_present = [name for name in _COMMON_ASPECT_FIELD_ORDER if name in all_fields]
    own_fields = [name for name in all_fields if name not in _COMMON_ASPECT_FIELD_ORDER]

    lines = list(header)
    for py_name in own_fields:
        lines.append(_render_field_row(model, py_name, all_fields[py_name]))

    if common_present:
        lines.append("")
        lines.append(
            "Plus these [common metadata fields](#common-metadata-fields), which every "
            "kind accepts a subset of depending on what DataHub's entity registry permits:"
        )
        lines.append("")
        lines.extend(header)
        for py_name in common_present:
            lines.append(_render_field_row(model, py_name, all_fields[py_name]))

    return "\n".join(lines)


def _model_doc(model: Type[BaseModel]) -> str:
    if model.__doc__:
        return " ".join(line.strip() for line in model.__doc__.strip().splitlines())
    return ""


def build_markdown() -> str:
    lines: List[str] = []
    lines.append("<!-- AUTO-GENERATED by scripts/generate_markdown_docs.py -- do not edit by hand. -->")
    lines.append("# YAML Metadata Format Reference")
    lines.append("")
    lines.append(
        "Complete field-by-field reference for every document `kind` and the raw "
        "aspect passthrough format, generated directly from the connector's "
        "Pydantic models (`src/datahub_yaml_source/models.py`) -- it cannot drift "
        "from what the connector actually accepts. For a narrative introduction, "
        "see [yaml.md](yaml.md)."
    )
    lines.append("")
    lines.append("## Document kinds")
    lines.append("")
    for kind, _ in DOCUMENT_MODELS:
        lines.append(f"- [`{kind}`](#{_anchor(kind)})")
    lines.append("")
    lines.append("## Common metadata fields")
    lines.append("")
    lines.append(
        "`owners`, `tags`, `glossaryTerms`, `domains`, `applications`, `links`, "
        "`deprecation`, `structuredProperties`, and `subTypes` behave identically "
        "wherever they're accepted -- which kind accepts which is determined by "
        "DataHub's entity registry, not by this connector, so it varies per kind. "
        "Each kind's own section below lists exactly the subset it accepts, after "
        "that kind's distinctive fields."
    )
    lines.append("")

    for kind, model in DOCUMENT_MODELS:
        lines.append(f"## {kind}")
        lines.append("")
        doc = _model_doc(model)
        if doc:
            lines.append(doc)
            lines.append("")
        lines.append(_render_field_table(model))
        lines.append("")

    lines.append("## Supporting types")
    lines.append("")
    lines.append("Nested structures referenced by the fields above.")
    lines.append("")
    for model in SUPPORTING_MODELS:
        lines.append(f"### {model.__name__}")
        lines.append("")
        doc = _model_doc(model)
        if doc:
            lines.append(doc)
            lines.append("")
        lines.append(_render_field_table(model))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    markdown = build_markdown()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
