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
    AssertionAssertionDoc,
    AssertionDoc,
    AssertionPropertiesDoc,
    ContainerDoc,
    ContainerRef,
    CreatedDoc,
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
    DomainDoc,
    FineGrainedLineageDoc,
    ForeignKeyDoc,
    GlossaryNodeDoc,
    GlossaryTermDoc,
    OwnerEntry,
    RawAspectDoc,
    RunEventDoc,
    SchemaBlock,
    SchemaFieldDoc,
    StructuredPropertyDoc,
    StructuredPropertySettingsDoc,
    TagDoc,
    UpstreamEntryDoc,
    UpstreamLineageDoc,
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
    ("CONTAINER", ContainerDoc),
    ("DATASET", DatasetDoc),
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
    DatasetRef,
    DatasetFieldRef,
    SchemaBlock,
    SchemaFieldDoc,
    ForeignKeyDoc,
    UpstreamLineageDoc,
    UpstreamEntryDoc,
    FineGrainedLineageDoc,
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


def _render_field_table(model: Type[BaseModel]) -> str:
    lines = ["| Field | Type | Required | Default | Description |", "| --- | --- | --- | --- | --- |"]
    for py_name, field in model.model_fields.items():
        yaml_name = field.alias or py_name
        required = "**yes**" if field.is_required() else "no"
        type_str = _render_type(field.annotation)
        default = _render_default(field)
        description = (field.description or "").replace("\n", " ")
        lines.append(f"| `{yaml_name}` | {type_str} | {required} | {default} | {description} |")
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
