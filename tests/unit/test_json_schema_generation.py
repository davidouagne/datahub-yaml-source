import json
import sys
from pathlib import Path

import pydantic
import pytest
from jsonschema import Draft202012Validator
from packaging.version import Version

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from generate_json_schema import OUTPUT_PATH, build_schema  # noqa: E402

# The checked-in schema is generated with the locked pydantic. Its JSON
# Schema generator changed shape before 2.11 (`allOf` around `$ref`,
# `type` next to `const`), so on the `lowest` CI leg (pydantic at the
# 2.4.0 runtime floor) the drift check would only compare generator
# versions, not models. The `highest` legs still run it.
_SCHEMA_GENERATOR_STABLE = Version(pydantic.VERSION) >= Version("2.11")


@pytest.mark.skipif(
    not _SCHEMA_GENERATOR_STABLE,
    reason="pydantic < 2.11 generates a differently shaped JSON Schema",
)
def test_checked_in_schema_is_up_to_date_with_models():
    """If this fails, someone changed a Pydantic model in models.py without
    regenerating the schema. Run `python scripts/generate_json_schema.py`."""
    checked_in = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    freshly_generated = build_schema()
    assert checked_in == freshly_generated, (
        "docs/sources/yaml/schema/yaml-metadata.schema.json is out of date -- "
        "run `python scripts/generate_json_schema.py` to regenerate it."
    )


def test_generated_schema_is_valid_draft_2020_12():
    schema = build_schema()
    Draft202012Validator.check_schema(schema)


def test_generated_schema_has_one_branch_per_document_kind():
    schema = build_schema()
    assert len(schema["oneOf"]) == 32  # 31 `kind:` values + the raw aspect passthrough doc


def test_generated_schema_validates_every_fixture_document():
    import yaml

    schema = build_schema()
    validator = Draft202012Validator(schema)

    resources = REPO_ROOT / "tests" / "integration" / "yaml_source" / "resources"
    checked = 0
    for path in resources.rglob("*.yml"):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if doc is None:
                continue
            checked += 1
            errors = list(validator.iter_errors(doc))
            assert not errors, (
                f"{path}: {doc.get('kind') or doc.get('aspectName')}: {errors[0].message}"
            )
    assert checked > 0


def test_generated_schema_rejects_unknown_kind():
    schema = build_schema()
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors({"kind": "NOT_A_REAL_KIND", "name": "x"}))
    assert errors


def test_generated_schema_rejects_dataset_missing_required_platform():
    schema = build_schema()
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors({"kind": "DATASET", "name": "x"}))
    assert errors
