"""Out-of-range server behaviour (ADR-0007 §2, §4; issue #141).

Seam: constructing `YamlSource` with a `PipelineContext` whose graph is a
double exposing a real `RestServiceConfig` built from a `/config` payload.
The supported range is read from the installed package metadata.
"""

import logging
from pathlib import Path
from typing import Any

import pytest
from datahub.configuration.common import ConfigurationError
from datahub.ingestion.api.common import PipelineContext
from datahub.utilities.server_config_util import RestServiceConfig

from datahub_yaml_source.yaml_source import YamlSource
from datahub_yaml_source.yaml_source_config import YamlSourceConfig


class _FakeGraph:
    """Stands in for DataHubGraph: only the server config is read."""

    def __init__(self, version: str | None, server_env: str = "core") -> None:
        raw: dict[str, Any] = {"datahub": {"serverEnv": server_env}}
        if version is not None:
            raw["versions"] = {"acryldata/datahub": {"version": version}}
        self.server_config = RestServiceConfig(raw_config=raw)


def _source(tmp_path: Path, graph: _FakeGraph | None, **config_kwargs: Any) -> YamlSource:
    ctx = PipelineContext(run_id="test-run")
    ctx.graph = graph  # type: ignore[assignment]
    return YamlSource(YamlSourceConfig(path=str(tmp_path), **config_kwargs), ctx)


def _warning_texts(source: YamlSource) -> list[str]:
    return [str(w) for w in source.report.warnings]


def test_server_on_a_newer_minor_is_reported_as_out_of_range(tmp_path: Path):
    source = _source(tmp_path, _FakeGraph("v1.8.0"))

    warnings = _warning_texts(source)
    assert len(warnings) == 1
    assert "v1.8.0" in warnings[0]
    assert "1.7" in warnings[0]


def test_server_patch_below_the_client_floor_is_in_range(tmp_path: Path):
    # GMS 1.7 reports v1.7.0 / v1.7.0.1 while the client floor is 1.7.0.11:
    # the range is compared per minor.
    source = _source(tmp_path, _FakeGraph("v1.7.0.1"))

    assert _warning_texts(source) == []


def test_unreadable_server_version_is_reported_as_unrecognised(tmp_path: Path):
    for version in ("not-a-version", None):
        source = _source(tmp_path, _FakeGraph(version))

        warnings = _warning_texts(source)
        assert len(warnings) == 1, version
        assert "not recognised" in warnings[0]


def test_datahub_cloud_is_reported_as_unrecognised(tmp_path: Path):
    # Cloud follows its own v0.3.x line, unrelated to the open-source minors.
    source = _source(tmp_path, _FakeGraph("v0.3.14", server_env="cloud"))

    warnings = _warning_texts(source)
    assert len(warnings) == 1
    assert "not recognised" in warnings[0]
    assert "Cloud" in warnings[0]


def test_without_a_graph_the_version_is_only_logged(tmp_path: Path, caplog):
    # file / console sinks: no server to compare, and no noise in the report.
    with caplog.at_level(logging.INFO, logger="datahub_yaml_source"):
        source = _source(tmp_path, None)

    assert _warning_texts(source) == []
    assert any("server version" in r.getMessage() for r in caplog.records)


def test_strict_version_fails_init_whenever_a_warning_would_be_raised(tmp_path: Path):
    for graph in (
        _FakeGraph("v1.8.0"),
        _FakeGraph("not-a-version"),
        _FakeGraph("v0.3.14", server_env="cloud"),
    ):
        with pytest.raises(ConfigurationError):
            _source(tmp_path, graph, strict_version=True)


def test_strict_version_without_a_graph_fails_and_suggests_datahub_api(tmp_path: Path):
    with pytest.raises(ConfigurationError, match="datahub_api"):
        _source(tmp_path, None, strict_version=True)


def test_strict_version_accepts_a_server_in_range(tmp_path: Path):
    source = _source(tmp_path, _FakeGraph("v1.7.0"), strict_version=True)

    assert _warning_texts(source) == []
