"""Minimum server version filter (ADR-0007 §5; issue #142).

Seam: the workunit processor, fed a test table, plus one run through
`YamlSource.get_workunits()` with the real (empty) table.
"""

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.api.source import SourceReport
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import StatusClass, SubTypesClass

from datahub_yaml_source.minimum_server_version import filter_by_minimum_server_version


def _wu(urn: str, aspect: object) -> MetadataWorkUnit:
    return MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect).as_workunit()  # type: ignore[arg-type]


def _urns_and_aspects(wus: list[MetadataWorkUnit]) -> list[tuple[str, str]]:
    return [(wu.get_urn(), wu.metadata.aspectName) for wu in wus]  # type: ignore[union-attr]


DOC_A = "urn:li:document:a"
DOC_B = "urn:li:document:b"
TAG = "urn:li:tag:pii"


def test_entity_needing_a_newer_server_is_skipped_with_one_aggregated_warning():
    report = SourceReport()
    stream = [
        _wu(DOC_A, StatusClass(removed=False)),
        _wu(TAG, StatusClass(removed=False)),
        _wu(DOC_B, StatusClass(removed=False)),
    ]

    emitted = list(
        filter_by_minimum_server_version(
            stream, (1, 7), report, by_entity={"document": (1, 8)}, by_aspect={}
        )
    )

    assert _urns_and_aspects(emitted) == [(TAG, "status")]
    warnings = [str(w) for w in report.warnings]
    assert len(warnings) == 1
    assert "document" in warnings[0]
    assert "1.8" in warnings[0]
    assert "2" in warnings[0]


def test_aspect_needing_a_newer_server_is_skipped_but_the_entity_keeps_its_other_aspects():
    report = SourceReport()
    stream = [
        _wu(TAG, StatusClass(removed=False)),
        _wu(TAG, SubTypesClass(typeNames=["x"])),
    ]

    emitted = list(
        filter_by_minimum_server_version(
            stream, (1, 7), report, by_entity={}, by_aspect={"subTypes": (1, 9)}
        )
    )

    assert _urns_and_aspects(emitted) == [(TAG, "status")]
    assert len(report.warnings) == 1
    assert "subTypes" in str(next(iter(report.warnings)))


def test_unknowable_server_version_emits_everything():
    report = SourceReport()
    stream = [_wu(DOC_A, StatusClass(removed=False))]

    emitted = list(
        filter_by_minimum_server_version(
            stream, None, report, by_entity={"document": (1, 8)}, by_aspect={}
        )
    )

    assert _urns_and_aspects(emitted) == [(DOC_A, "status")]
    assert len(report.warnings) == 0


def test_server_at_the_minimum_emits_everything():
    report = SourceReport()
    stream = [_wu(DOC_A, StatusClass(removed=False))]

    emitted = list(
        filter_by_minimum_server_version(
            stream, (1, 8), report, by_entity={"document": (1, 8)}, by_aspect={}
        )
    )

    assert _urns_and_aspects(emitted) == [(DOC_A, "status")]
    assert len(report.warnings) == 0


def _yaml_source(tmp_path, version):
    from datahub.ingestion.api.common import PipelineContext
    from datahub.utilities.server_config_util import RestServiceConfig

    from datahub_yaml_source.yaml_source import YamlSource
    from datahub_yaml_source.yaml_source_config import YamlSourceConfig

    class _FakeGraph:
        server_config = RestServiceConfig(
            raw_config={
                "versions": {"acryldata/datahub": {"version": version}},
                "datahub": {"serverEnv": "core"},
            }
        )

    (tmp_path / "tags.yml").write_text("kind: TAG\nname: pii\n---\nkind: TAG\nname: phi\n")
    ctx = PipelineContext(run_id="test-run")
    ctx.graph = _FakeGraph()  # type: ignore[assignment]
    return YamlSource(YamlSourceConfig(path=str(tmp_path)), ctx)


def test_source_applies_the_real_table_to_its_workunits(tmp_path, monkeypatch):
    from datahub_yaml_source import minimum_server_version

    ungated = {wu.get_urn() for wu in _yaml_source(tmp_path, "v1.7.0").get_workunits()}
    assert "urn:li:tag:pii" in ungated

    monkeypatch.setitem(minimum_server_version.MINIMUM_SERVER_MINOR_BY_ENTITY, "tag", (1, 8))
    source = _yaml_source(tmp_path, "v1.7.0")
    gated = {wu.get_urn() for wu in source.get_workunits()}

    assert not any(urn.startswith("urn:li:tag:") for urn in gated)
    assert any("tag: " in str(w) for w in source.report.warnings)
