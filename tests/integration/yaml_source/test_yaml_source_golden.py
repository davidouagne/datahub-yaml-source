import json
import os
from pathlib import Path
from typing import Any, Dict, List

from datahub.ingestion.run.pipeline import Pipeline
from datahub.testing import mce_helpers

RESOURCES_DIR = Path(__file__).parent / "resources"
GOLDEN_FILE = Path(__file__).parent / "yaml_source_mces_golden.json"


def _relpath(path: Path) -> str:
    # The DataHub file sink/source derive their filesystem implementation from
    # `urlparse(path).scheme`, which misreads a Windows drive letter (`C:\...`)
    # as a URL scheme. Relative paths sidestep that entirely.
    return os.path.relpath(str(path), start=os.getcwd())


def _run_yaml_source_to_file(output_path: Path) -> None:
    pipeline = Pipeline.create(
        {
            "run_id": "yaml-source-golden-test",
            "source": {
                "type": "yaml",
                "config": {"path": _relpath(RESOURCES_DIR)},
            },
            "sink": {
                "type": "file",
                "config": {"filename": _relpath(output_path)},
            },
        }
    )
    pipeline.run()
    pipeline.raise_from_status()


def _normalize(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop run-specific `systemMetadata` and sort for order-insensitive diffing."""
    normalized = []
    for event in events:
        event = dict(event)
        event.pop("systemMetadata", None)
        normalized.append(event)
    return sorted(normalized, key=lambda e: (e.get("entityUrn", ""), e.get("aspectName", "")))


def test_yaml_source_produces_expected_golden_file(pytestconfig, tmp_path):
    output_path = tmp_path / "yaml_source_mces.json"
    _run_yaml_source_to_file(output_path)

    # `mce_helpers.check_golden_file` normalizes the golden file by round-tripping
    # it through `datahub.ingestion.sink.file.write_metadata_file` into a
    # `tempfile.NamedTemporaryFile`. On native Windows, that temp path's drive
    # letter (e.g. "C:\\...") gets misparsed as a URL scheme by the file sink's
    # `get_path_schema`, which raises `KeyError` unrelated to this connector's
    # correctness (reproducible with any connector's golden file test on this
    # platform). Fall back to a simpler structural comparison there; use the
    # standards-compliant helper everywhere else (this is what CI runs).
    try:
        mce_helpers.check_golden_file(
            pytestconfig,
            output_path=output_path,
            golden_path=GOLDEN_FILE,
        )
    except KeyError as e:
        if "registered class for" not in str(e):
            raise
        output = _normalize(json.loads(output_path.read_text(encoding="utf-8")))
        golden = _normalize(json.loads(GOLDEN_FILE.read_text(encoding="utf-8")))
        assert output == golden


def test_yaml_source_reports_no_dangling_references_or_parse_failures():
    """The curated fixture is deliberately self-consistent: every tag, domain,
    glossary term, and container referenced by another document is declared
    somewhere in the tree. This guards against fixture bit-rot."""
    pipeline = Pipeline.create(
        {
            "source": {
                "type": "yaml",
                "config": {"path": _relpath(RESOURCES_DIR)},
            },
            "sink": {"type": "console"},
        }
    )
    pipeline.run()
    pipeline.raise_from_status()

    source_report = pipeline.source.get_report()
    assert source_report.documents_failed_to_parse == 0
    assert len(source_report.dangling_references) == 0
    assert len(source_report.unknown_fields) == 0
    assert source_report.datasets_scanned == 4
    assert source_report.containers_scanned == 4
    assert source_report.applications_scanned == 1
    assert source_report.charts_scanned == 1
    assert source_report.dashboards_scanned == 1
    assert source_report.queries_scanned == 1
    assert source_report.incidents_scanned == 1
    assert source_report.documents_scanned == 1
    assert source_report.ml_feature_tables_scanned == 1
    assert source_report.ml_features_scanned == 1
    assert source_report.ml_primary_keys_scanned == 1
    assert source_report.ml_model_groups_scanned == 1
    assert source_report.ml_models_scanned == 1
    assert source_report.semantic_models_scanned == 1
    assert source_report.metrics_scanned == 1
    assert source_report.repositories_scanned == 1
    assert source_report.apis_scanned == 1
    assert source_report.agent_skills_scanned == 1
    assert source_report.ai_agents_scanned == 1
    assert source_report.services_scanned == 1
    assert source_report.data_process_instances_scanned == 2
    assert source_report.assertions_scanned == 3
    assert source_report.raw_aspects_scanned == 5
