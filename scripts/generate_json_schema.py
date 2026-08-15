"""Generate the JSON Schema for the YAML metadata-as-code document format.

The schema is derived directly from the Pydantic models in
`datahub_yaml_source.models`, so it can never drift from what the connector
actually accepts: any field added/removed/redescribed there is automatically
reflected here on the next run.

Usage:
    python scripts/generate_json_schema.py

Editors (VS Code's redhat.vscode-yaml, IntelliJ, ...) pick this up via a
modeline at the top of a YAML file:
    # yaml-language-server: $schema=./schema/yaml-metadata.schema.json
"""

import json
from pathlib import Path

from pydantic.json_schema import models_json_schema

from datahub_yaml_source.models import (
    ApplicationDoc,
    AssertionDoc,
    ChartDoc,
    ContainerDoc,
    DashboardDoc,
    DataFlowDoc,
    DataJobDoc,
    DataPlatformDoc,
    DataProcessInstanceDoc,
    DataProductDoc,
    DatasetDoc,
    DocumentDoc,
    DomainDoc,
    GlossaryNodeDoc,
    GlossaryTermDoc,
    IncidentDoc,
    QueryDoc,
    RawAspectDoc,
    StructuredPropertyDoc,
    TagDoc,
)

OUTPUT_PATH = (
    Path(__file__).parent.parent / "docs" / "sources" / "yaml" / "schema" / "yaml-metadata.schema.json"
)

# One entry per `kind:` value, plus the `aspectName:`-keyed passthrough doc.
# Order here only affects the order of the generated `oneOf` list.
DOCUMENT_MODELS = [
    DataPlatformDoc,
    TagDoc,
    GlossaryNodeDoc,
    GlossaryTermDoc,
    StructuredPropertyDoc,
    DomainDoc,
    ApplicationDoc,
    ContainerDoc,
    DatasetDoc,
    ChartDoc,
    DashboardDoc,
    QueryDoc,
    IncidentDoc,
    DocumentDoc,
    DataProductDoc,
    DataFlowDoc,
    DataJobDoc,
    DataProcessInstanceDoc,
    AssertionDoc,
    RawAspectDoc,
]


def build_schema() -> dict:
    refs, combined_schema = models_json_schema(
        [(model, "validation") for model in DOCUMENT_MODELS],
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "YAML metadata-as-code document",
        "description": (
            "A single document (one `---`-separated section of a *.yml/*.yaml "
            "file) in the datahub-yaml-source format. Discriminated by `kind` "
            "for entity documents, or by `aspectName` for raw aspect passthrough "
            "documents. See docs/sources/yaml/yaml.md for the full reference."
        ),
        "oneOf": [refs[(model, "validation")] for model in DOCUMENT_MODELS],
        "$defs": combined_schema["$defs"],
    }


def main() -> None:
    schema = build_schema()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
