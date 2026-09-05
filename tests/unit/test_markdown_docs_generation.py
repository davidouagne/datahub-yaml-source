import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from generate_markdown_docs import OUTPUT_PATH, build_markdown  # noqa: E402


def test_checked_in_reference_md_is_up_to_date_with_models():
    """If this fails, someone changed a Pydantic model in models.py without
    regenerating the docs. Run `python scripts/generate_markdown_docs.py`."""
    checked_in = OUTPUT_PATH.read_text(encoding="utf-8")
    freshly_generated = build_markdown()
    assert checked_in == freshly_generated, (
        "docs/sources/yaml/reference.md is out of date -- "
        "run `python scripts/generate_markdown_docs.py` to regenerate it."
    )


def test_generated_markdown_has_a_section_per_document_kind():
    markdown = build_markdown()
    for kind in [
        "DATA_PLATFORM",
        "TAG",
        "GLOSSARY_NODE",
        "GLOSSARY_TERM",
        "STRUCTURED_PROPERTY",
        "DOMAIN",
        "CONTAINER",
        "DATASET",
        "DATA_PRODUCT",
        "DATA_FLOW",
        "DATA_JOB",
        "DATA_PROCESS_INSTANCE",
        "ASSERTION",
    ]:
        assert f"## {kind}\n" in markdown


def test_generated_markdown_links_are_not_dangling():
    """Every `[Name](#anchor)` reference must correspond to a real `##`/`###`
    heading elsewhere in the document (case-insensitive, GFM anchor rules)."""
    import re

    markdown = build_markdown()
    headings = set()
    for line in markdown.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            heading_text = line.lstrip("#").strip()
            anchor = (
                heading_text.lower()
                .replace(" ", "-")
                .replace("_", "-")
                .replace(":", "")
                .replace("(", "")
                .replace(")", "")
                .replace(".", "")
            )
            headings.add(anchor)

    referenced_anchors = set(re.findall(r"\]\(#([a-z0-9\-]+)\)", markdown))
    missing = referenced_anchors - headings
    assert not missing, f"Dangling links to non-existent headings: {missing}"
