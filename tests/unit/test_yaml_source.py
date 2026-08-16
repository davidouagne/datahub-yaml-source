from pathlib import Path

import pytest
import requests
from datahub.configuration.git import GitInfo
from datahub.ingestion.api.common import PipelineContext
from datahub.ingestion.source.common.http_connection_config import HTTPConnectionConfig
from pydantic import ValidationError

from datahub_yaml_source.loader import ParsedRepository
from datahub_yaml_source.yaml_source import YamlSource, _resolve_aws_connection
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
    # DATASET is deliberately unsupported: deprecated upstream in favor of VOLUME.
    (tmp_path / "assets.yml").write_text(
        "kind: ASSERTION\n"
        "id: bad-assertion\n"
        "assertion:\n"
        "  type: DATASET\n"
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


# --- git_info -----------------------------------------------------------


def test_config_requires_path_when_git_info_is_not_set():
    with pytest.raises(ValidationError, match="'path' is required"):
        YamlSourceConfig()


def test_config_defaults_path_to_dot_when_git_info_is_set():
    config = YamlSourceConfig(git_info=GitInfo(repo="https://github.com/aphp/datahub-sample"))
    assert config.path == "."


def test_get_workunits_internal_clones_git_info_and_loads_checkout(tmp_path: Path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "assets.yml").write_text("kind: TAG\nname: from-git\n")

    def fake_clone(self, tmp_path, fallback_deploy_key=None):
        return checkout

    monkeypatch.setattr(GitInfo, "clone", fake_clone)

    config = YamlSourceConfig(git_info=GitInfo(repo="https://github.com/aphp/datahub-sample"))
    source = YamlSource(config, PipelineContext(run_id="test-run"))

    wus = list(source.get_workunits_internal())

    assert source.report.tags_scanned == 1
    assert source.report.files_scanned == 1
    assert source.report.git_checkout == str(checkout)
    assert any(wu.metadata.entityUrn == "urn:li:tag:from-git" for wu in wus)


def test_get_workunits_internal_resolves_relative_path_under_git_checkout(
    tmp_path: Path, monkeypatch
):
    checkout = tmp_path / "checkout"
    (checkout / "sub").mkdir(parents=True)
    (checkout / "sub" / "assets.yml").write_text("kind: TAG\nname: scoped\n")
    # A file outside the configured subtree must not be scanned.
    (checkout / "outside.yml").write_text("kind: TAG\nname: unscoped\n")

    def fake_clone(self, tmp_path, fallback_deploy_key=None):
        return checkout

    monkeypatch.setattr(GitInfo, "clone", fake_clone)

    config = YamlSourceConfig(
        git_info=GitInfo(repo="https://github.com/aphp/datahub-sample"), path="sub"
    )
    source = YamlSource(config, PipelineContext(run_id="test-run"))

    wus = list(source.get_workunits_internal())

    assert source.report.tags_scanned == 1
    assert any(wu.metadata.entityUrn == "urn:li:tag:scoped" for wu in wus)
    assert not any(wu.metadata.entityUrn == "urn:li:tag:unscoped" for wu in wus)


def test_get_workunits_internal_reports_failure_when_git_clone_raises(monkeypatch):
    def fake_clone(self, tmp_path, fallback_deploy_key=None):
        raise RuntimeError("SSH authentication failed")

    monkeypatch.setattr(GitInfo, "clone", fake_clone)

    config = YamlSourceConfig(git_info=GitInfo(repo="https://github.com/aphp/datahub-sample"))
    source = YamlSource(config, PipelineContext(run_id="test-run"))

    wus = list(source.get_workunits_internal())

    assert wus == []
    assert len(source.report.failures) == 1
    assert "clone" in str(source.report.failures[0]).lower()


def test_test_connection_reports_capable_when_git_clone_succeeds(tmp_path: Path, monkeypatch):
    def fake_clone(self, tmp_path, fallback_deploy_key=None):
        return tmp_path

    monkeypatch.setattr(GitInfo, "clone", fake_clone)

    report = YamlSource.test_connection(
        {"git_info": {"repo": "https://github.com/aphp/datahub-sample"}}
    )
    assert report.basic_connectivity.capable is True


def test_test_connection_reports_not_capable_when_git_clone_fails(monkeypatch):
    def fake_clone(self, tmp_path, fallback_deploy_key=None):
        raise RuntimeError("Repository not found")

    monkeypatch.setattr(GitInfo, "clone", fake_clone)

    report = YamlSource.test_connection(
        {"git_info": {"repo": "https://github.com/aphp/datahub-sample"}}
    )
    assert report.basic_connectivity.capable is False


# --- s3:// / http(s):// path entries --------------------------------------


def test_config_requires_aws_connection_for_s3_path():
    with pytest.raises(ValidationError, match="aws_connection"):
        YamlSourceConfig(path="s3://bucket/prefix")


def test_config_requires_aws_connection_when_any_path_entry_is_s3():
    with pytest.raises(ValidationError, match="aws_connection"):
        YamlSourceConfig(path=["/local/dir", "s3://bucket/prefix"])


def test_config_accepts_s3_path_with_aws_connection():
    config = YamlSourceConfig(path="s3://bucket/prefix", aws_connection={})
    assert config.path == "s3://bucket/prefix"


def test_config_accepts_http_path_without_aws_connection():
    config = YamlSourceConfig(path="https://example.com/catalog.yml")
    assert config.path == "https://example.com/catalog.yml"


def test_config_accepts_path_as_a_list():
    config = YamlSourceConfig(path=["/a", "/b"])
    assert config.path == ["/a", "/b"]


def test_config_rejects_s3_path_combined_with_git_info():
    with pytest.raises(ValidationError, match="git_info"):
        YamlSourceConfig(
            git_info=GitInfo(repo="https://github.com/aphp/datahub-sample"),
            path=["s3://bucket/prefix"],
            aws_connection={},
        )


def test_config_rejects_http_path_combined_with_git_info():
    with pytest.raises(ValidationError, match="git_info"):
        YamlSourceConfig(
            git_info=GitInfo(repo="https://github.com/aphp/datahub-sample"),
            path=["https://example.com/catalog.yml"],
        )


def test_resolve_aws_connection_returns_none_when_unset():
    assert _resolve_aws_connection(None) is None


def test_resolve_aws_connection_builds_config_from_dict():
    conn = _resolve_aws_connection({"aws_region": "eu-west-1"})
    assert conn.aws_region == "eu-west-1"


def test_get_workunits_internal_passes_remote_config_through_to_load_repository(monkeypatch):
    captured = {}

    def fake_load_repository(
        roots,
        on_error,
        on_file_scanned=None,
        on_unknown_fields=None,
        aws_connection=None,
        http_connection=None,
        max_input_file_bytes=None,
    ):
        captured["roots"] = roots
        captured["aws_connection"] = aws_connection
        captured["http_connection"] = http_connection
        captured["max_input_file_bytes"] = max_input_file_bytes
        return ParsedRepository()

    monkeypatch.setattr("datahub_yaml_source.yaml_source.load_repository", fake_load_repository)

    fake_aws_connection = object()
    monkeypatch.setattr(
        "datahub_yaml_source.yaml_source._resolve_aws_connection",
        lambda cfg: fake_aws_connection,
    )

    http_connection = HTTPConnectionConfig(token="secret")
    config = YamlSourceConfig(
        path=["s3://bucket/prefix", "https://example.com/catalog.yml"],
        aws_connection={"aws_region": "eu-west-1"},
        http_connection=http_connection,
        max_input_file_bytes=1000,
    )
    source = YamlSource(config, PipelineContext(run_id="test-run"))

    list(source.get_workunits_internal())

    assert captured["roots"] == ["s3://bucket/prefix", "https://example.com/catalog.yml"]
    assert captured["aws_connection"] is fake_aws_connection
    assert captured["http_connection"] is http_connection
    assert captured["max_input_file_bytes"] == 1000


def test_get_workunits_internal_reports_failure_when_boto3_missing_for_s3_path(monkeypatch):
    def fake_resolve(cfg):
        raise ImportError("Reading s3:// paths requires the 's3' extra")

    monkeypatch.setattr("datahub_yaml_source.yaml_source._resolve_aws_connection", fake_resolve)

    config = YamlSourceConfig(path="s3://bucket/prefix", aws_connection={})
    source = YamlSource(config, PipelineContext(run_id="test-run"))

    wus = list(source.get_workunits_internal())

    assert wus == []
    assert any("s3" in str(f).lower() for f in source.report.failures)


def test_test_connection_reports_not_capable_for_s3_path_without_aws_connection():
    report = YamlSource.test_connection({"path": "s3://bucket/prefix"})
    assert report.basic_connectivity.capable is False


def test_test_connection_reports_capable_for_s3_path(monkeypatch):
    class _FakeClient:
        def list_objects_v2(self, Bucket, Prefix, MaxKeys):
            return {}

    class _FakeAwsConnection:
        def get_s3_client(self):
            return _FakeClient()

    monkeypatch.setattr(
        "datahub_yaml_source.yaml_source._resolve_aws_connection",
        lambda cfg: _FakeAwsConnection(),
    )

    report = YamlSource.test_connection({"path": "s3://bucket/prefix", "aws_connection": {}})
    assert report.basic_connectivity.capable is True


def test_test_connection_reports_not_capable_when_s3_listing_fails(monkeypatch):
    class _FakeClient:
        def list_objects_v2(self, Bucket, Prefix, MaxKeys):
            raise RuntimeError("access denied")

    class _FakeAwsConnection:
        def get_s3_client(self):
            return _FakeClient()

    monkeypatch.setattr(
        "datahub_yaml_source.yaml_source._resolve_aws_connection",
        lambda cfg: _FakeAwsConnection(),
    )

    report = YamlSource.test_connection({"path": "s3://bucket/prefix", "aws_connection": {}})
    assert report.basic_connectivity.capable is False
    assert "access denied" in report.basic_connectivity.failure_reason


def test_test_connection_reports_not_capable_when_boto3_missing_for_s3_path(monkeypatch):
    def fake_resolve(cfg):
        raise ImportError("Reading s3:// paths requires the 's3' extra")

    monkeypatch.setattr("datahub_yaml_source.yaml_source._resolve_aws_connection", fake_resolve)

    report = YamlSource.test_connection({"path": "s3://bucket/prefix", "aws_connection": {}})
    assert report.basic_connectivity.capable is False
    assert "extra" in report.basic_connectivity.failure_reason


def test_test_connection_reports_capable_for_http_path(monkeypatch):
    def fake_head(url, timeout, allow_redirects, **kwargs):
        class _FakeResponse:
            def raise_for_status(self):
                pass

        return _FakeResponse()

    monkeypatch.setattr(requests, "head", fake_head)

    report = YamlSource.test_connection({"path": "https://example.com/catalog.yml"})
    assert report.basic_connectivity.capable is True


def test_test_connection_reports_not_capable_for_http_path_on_request_error(monkeypatch):
    def fake_head(url, timeout, allow_redirects, **kwargs):
        raise requests.ConnectionError("dns failure")

    monkeypatch.setattr(requests, "head", fake_head)

    report = YamlSource.test_connection({"path": "https://example.com/catalog.yml"})
    assert report.basic_connectivity.capable is False
    assert "dns failure" in report.basic_connectivity.failure_reason


def test_test_connection_reports_not_capable_for_http_glob_pattern():
    report = YamlSource.test_connection({"path": "https://example.com/*.yml"})
    assert report.basic_connectivity.capable is False
    assert "Glob patterns" in report.basic_connectivity.failure_reason
