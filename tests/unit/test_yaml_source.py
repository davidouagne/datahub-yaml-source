from pathlib import Path

import pytest
from datahub.ingestion.api.common import PipelineContext

from datahub_yaml_source.yaml_source import YamlSource
from datahub_yaml_source.yaml_source_config import YamlSourceConfig


def _source(tmp_path: Path, **config_kwargs) -> YamlSource:
    ctx = PipelineContext(run_id="test-run")
    config = YamlSourceConfig(path=str(tmp_path), **config_kwargs)
    return YamlSource(config, ctx)


def test_create_classmethod_builds_source_from_config_dict(tmp_path: Path):
    ctx = PipelineContext(run_id="test-run")
    source = YamlSource.create({"path": str(tmp_path)}, ctx)
    assert isinstance(source, YamlSource)


def test_get_workunits_internal_processes_valid_and_invalid_documents(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: TAG\nname: pii\n---\nkind: DATASET\nname: missing_platform\n"
    )
    source = _source(tmp_path)

    wus = list(source.get_workunits_internal())

    assert len(wus) > 0
    assert source.report.tags_scanned == 1
    assert source.report.documents_failed_to_parse == 1
    assert source.report.files_scanned == 1


def test_get_workunits_internal_counts_multiple_files_scanned(tmp_path: Path):
    (tmp_path / "a.yml").write_text("kind: TAG\nname: a\n")
    (tmp_path / "b.yaml").write_text("kind: TAG\nname: b\n")
    source = _source(tmp_path)

    list(source.get_workunits_internal())

    assert source.report.files_scanned == 2
    assert source.report.tags_scanned == 2


def test_get_workunits_internal_reports_failure_when_path_does_not_exist(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    source = _source(missing)

    wus = list(source.get_workunits_internal())

    assert wus == []
    assert len(source.report.failures) == 1
    assert "does not exist" in str(source.report.failures[0])


def test_get_workunits_internal_reports_failure_when_path_is_a_file(tmp_path: Path):
    file_path = tmp_path / "not_a_dir.yml"
    file_path.write_text("kind: TAG\nname: x\n")
    source = _source(file_path)

    wus = list(source.get_workunits_internal())

    assert wus == []
    assert len(source.report.failures) == 1
    assert "not a directory" in str(source.report.failures[0])


def test_get_workunits_internal_warns_when_directory_has_no_yaml_files(tmp_path: Path):
    (tmp_path / "readme.md").write_text("not a yaml file")
    source = _source(tmp_path)

    wus = list(source.get_workunits_internal())

    assert wus == []
    assert source.report.files_scanned == 0
    assert any("No YAML files found" in str(w) for w in source.report.warnings)


def test_get_workunits_internal_reports_warning_and_continues_when_builder_raises(
    tmp_path: Path,
):
    # A dataset whose upstreamLineage references a dataset ref without a platform
    # would fail model validation already; instead force a builder-time failure
    # via an assertion with an unsupported type, which raises inside the builder.
    (tmp_path / "assets.yml").write_text(
        "kind: ASSERTION\n"
        "id: bad-assertion\n"
        "assertion:\n"
        "  type: VOLUME\n"
        "  entityUrn: 'urn:li:dataset:(urn:li:dataPlatform:x,y,PROD)'\n"
        "---\n"
        "kind: TAG\n"
        "name: still-processed\n"
    )
    source = _source(tmp_path)

    wus = list(source.get_workunits_internal())

    tag_urns = {wu.metadata.entityUrn for wu in wus if wu.metadata.entityUrn == "urn:li:tag:still-processed"}
    assert tag_urns  # the tag after the failing assertion was still emitted
    assert len(source.report.warnings) == 1


def test_fail_on_unresolved_reference_raises_instead_of_warning(tmp_path: Path):
    (tmp_path / "bad.yml").write_text("not: [valid\n")
    source = _source(tmp_path, fail_on_unresolved_reference=True)

    with pytest.raises(ValueError, match="Failed to parse YAML"):
        list(source.get_workunits_internal())


def test_test_connection_reports_capable_for_existing_directory(tmp_path: Path):
    report = YamlSource.test_connection({"path": str(tmp_path)})
    assert report.basic_connectivity.capable is True


def test_test_connection_reports_not_capable_for_missing_path(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    report = YamlSource.test_connection({"path": str(missing)})
    assert report.basic_connectivity.capable is False
    assert "does not exist" in report.basic_connectivity.failure_reason


def test_test_connection_reports_not_capable_when_path_is_a_file(tmp_path: Path):
    file_path = tmp_path / "not_a_dir.yml"
    file_path.write_text("kind: TAG\nname: x\n")
    report = YamlSource.test_connection({"path": str(file_path)})
    assert report.basic_connectivity.capable is False
    assert "not a directory" in report.basic_connectivity.failure_reason


def test_test_connection_reports_not_capable_for_invalid_config():
    report = YamlSource.test_connection({})  # missing required 'path'
    assert report.basic_connectivity.capable is False
