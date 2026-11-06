"""Verdict logic of the local Version check (ADR-0007 §3; issue #143).

Seam: `containment_diffs(sent, read_back)` and `patch_diffs(ops, read_back)`
in scripts/version_check.py. Starting Docker and reading back from a live
GMS are exercised by actually running scripts/verify-datahub-version.sh.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from version_check import containment_diffs, patch_diffs  # noqa: E402


def test_identical_aspects_have_no_difference():
    sent = {"name": "patient", "tags": [{"tag": "urn:li:tag:pii"}]}

    assert containment_diffs(sent, {"name": "patient", "tags": [{"tag": "urn:li:tag:pii"}]}) == []


def test_values_the_server_adds_are_allowed():
    sent = {"name": "patient", "customProperties": {"a": "1"}}
    read_back = {
        "name": "patient",
        "customProperties": {"a": "1", "b": "2"},
        "created": {"time": 1},
    }

    assert containment_diffs(sent, read_back) == []


def test_a_trimmed_field_is_reported_with_its_path():
    sent = {"name": "patient", "owners": [{"owner": "urn:li:corpuser:a", "attribution": "x"}]}
    read_back = {"name": "patient", "owners": [{"owner": "urn:li:corpuser:a"}]}

    assert containment_diffs(sent, read_back) == ["/owners/0: no matching element"]


def test_a_changed_value_is_reported_with_both_sides():
    assert containment_diffs({"a": {"b": 1}}, {"a": {"b": 2}}) == ["/a/b: sent 1, read back 2"]


def test_list_elements_are_matched_in_any_order():
    sent = {"fields": [{"path": "a"}, {"path": "b"}]}
    read_back = {"fields": [{"path": "b", "type": "x"}, {"path": "a"}]}

    assert containment_diffs(sent, read_back) == []


def test_a_missing_aspect_is_reported():
    assert containment_diffs({"a": 1}, None) == ["aspect missing"]


def test_a_patch_add_is_checked_against_the_resulting_state():
    ops = [{"op": "add", "path": "/lastModified", "value": {"time": 5}}]

    assert patch_diffs(ops, {"name": "x", "lastModified": {"time": 5}}) == []
    assert patch_diffs(ops, {"name": "x"}) == ["/lastModified: missing"]


def test_a_patch_path_keyed_by_urn_is_found_in_the_stored_array():
    # Patch builders key array elements by URN; the stored aspect is a list.
    ops = [
        {"op": "add", "path": "/tags/urn:li:tag:pii", "value": {"tag": "urn:li:tag:pii"}},
    ]

    assert patch_diffs(ops, {"tags": [{"tag": "urn:li:tag:pii"}]}) == []
    assert patch_diffs(ops, {"tags": [{"tag": "urn:li:tag:phi"}]}) == [
        "/tags/urn:li:tag:pii: missing"
    ]


def test_a_patch_path_with_json_pointer_escapes_is_decoded():
    ops = [{"op": "add", "path": "/customProperties/a~1b~0c", "value": "x"}]

    assert patch_diffs(ops, {"customProperties": {"a/b~c": "x"}}) == []
