"""Version check: ingest the fixture into a live DataHub server, read it back.

Called by scripts/verify-datahub-version.sh against an isolated Docker GMS
(ADR-0007 §3; CONTEXT.md "Version check"). Exits 0 only if:

1. ingesting tests/integration/yaml_source/resources through `datahub-rest`
   in `mode: SYNC` reports no failure and no warning, source or sink, apart
   from the skips the Minimum server version table predicts;
2. every aspect emitted, read back from the server, still contains what was
   sent -- the server may add values, never drop or change them.

The baseline is the run's own emitted MCPs, not a committed reference.
Never run in CI.
"""

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "integration" / "yaml_source" / "resources"
SKIP_WARNING_TITLE = "Skipped: needs a newer DataHub server"


# --- verdict logic (unit-tested in tests/unit/test_version_check.py) --------


def containment_diffs(sent: Any, read_back: Any, path: str = "") -> list[str]:
    """Where `read_back` does not contain everything in `sent`.

    Dicts: every sent key must be present and contained. Lists: every sent
    element must be contained in some read-back element, in any order.
    Scalars: equal. Values only present in `read_back` are allowed.
    """
    if read_back is None and path == "":
        return ["aspect missing"]
    if isinstance(sent, dict):
        if not isinstance(read_back, dict):
            return [f"{path or '/'}: sent an object, read back {read_back!r}"]
        diffs: list[str] = []
        for key, value in sent.items():
            if key not in read_back:
                diffs.append(f"{path}/{key}: missing")
            else:
                diffs.extend(containment_diffs(value, read_back[key], f"{path}/{key}"))
        return diffs
    if isinstance(sent, list):
        if not isinstance(read_back, list):
            return [f"{path or '/'}: sent a list, read back {read_back!r}"]
        return [
            f"{path}/{i}: no matching element"
            for i, element in enumerate(sent)
            if not any(containment_diffs(element, other, "/") == [] for other in read_back)
        ]
    if sent != read_back:
        return [f"{path or '/'}: sent {sent!r}, read back {read_back!r}"]
    return []


def patch_diffs(ops: Iterable[dict[str, Any]], read_back: Any) -> list[str]:
    """Where the state read back does not reflect a JSON Patch's `add` ops."""
    if read_back is None:
        return ["aspect missing"]
    diffs: list[str] = []
    for op in ops:
        if op.get("op") != "add":
            continue
        node = read_back
        for part in op["path"].strip("/").split("/"):
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is None:
            diffs.append(f"{op['path']}: missing")
        else:
            diffs.extend(containment_diffs(op["value"], node, op["path"]))
    return diffs


# --- live run ----------------------------------------------------------------


def _relpath(path: Path) -> str:
    # The file source/sink misread a Windows drive letter as a URL scheme.
    return str(Path(path).resolve().relative_to(Path.cwd().resolve()))


class _SinkFailures(logging.Handler):
    """Collects the sink's write failures.

    In `mode: SYNC` the datahub-rest sink hands a failed write only to the
    pipeline's write callback, which logs it; it never reaches
    `sink.get_report().failures` (only the async modes record it there).
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        failure = record.exc_info[1] if record.exc_info else None
        self.messages.append(f"{record.getMessage().strip()}: {failure}")


def _ingest(server: str) -> list[str]:
    """Run the real pipeline; return every unexpected report problem."""
    from datahub.ingestion.run.pipeline import Pipeline

    sink_failures = _SinkFailures()
    callback_logger = logging.getLogger("datahub.ingestion.run.sink_callback")
    callback_logger.addHandler(sink_failures)
    try:
        pipeline = Pipeline.create(
            {
                "run_id": "version-check",
                "source": {"type": "yaml", "config": {"path": _relpath(FIXTURE)}},
                "sink": {"type": "datahub-rest", "config": {"server": server, "mode": "SYNC"}},
            }
        )
        pipeline.run()
    finally:
        callback_logger.removeHandler(sink_failures)

    source_report = pipeline.source.get_report()
    sink_report = pipeline.sink.get_report()
    problems = [f"source failure: {f}" for f in source_report.failures]
    problems += [
        f"source warning: {w}"
        for w in source_report.warnings
        if getattr(w, "title", None) != SKIP_WARNING_TITLE
    ]
    problems += [f"sink failure: {m}" for m in sink_failures.messages]
    problems += [f"sink failure: {f}" for f in sink_report.failures]
    problems += [f"sink warning: {w}" for w in sink_report.warnings]
    return problems


def _emitted(graph: Any) -> list[Any]:
    """The MCPs a run emits against this server, minimum-version skips applied."""
    from datahub.ingestion.api.common import PipelineContext
    from datahub.sdk._attribution import KnownAttribution, change_default_attribution

    from datahub_yaml_source.yaml_source import YamlSource

    ctx = PipelineContext(run_id="version-check-baseline", graph=graph)
    source = YamlSource.create({"path": _relpath(FIXTURE)}, ctx)
    # The pipeline runs sources under the INGESTION attribution, which makes
    # the SDK write descriptions to e.g. datasetProperties instead of
    # editableDatasetProperties; the baseline must be built the same way.
    with change_default_attribution(KnownAttribution.INGESTION):
        return [wu.metadata for wu in source.get_workunits()]


def _read_back(graph: Any, mcps: list[Any]) -> list[str]:
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import ASPECT_NAME_MAP

    latest: dict[tuple[str, str], Any] = {}
    patches: list[Any] = []
    for mcp in mcps:
        if not isinstance(mcp, MetadataChangeProposalWrapper):
            patches.append(mcp)
            continue
        key = (mcp.entityUrn, mcp.aspectName)
        aspect = mcp.aspect
        if aspect.ASPECT_TYPE == "timeseries":
            kept = latest.get(key)
            if kept is not None and kept.timestampMillis > aspect.timestampMillis:
                continue
        latest[key] = aspect  # last UPSERT of a versioned aspect wins

    diffs: list[str] = []
    for (urn, aspect_name), aspect in sorted(latest.items()):
        cls = type(aspect)
        if aspect.ASPECT_TYPE == "timeseries":
            read = graph.get_latest_timeseries_value(
                entity_urn=urn, aspect_type=cls, filter_criteria_map={}
            )
        else:
            read = graph.get_aspect(urn, cls)
        found = containment_diffs(aspect.to_obj(), read.to_obj() if read is not None else None)
        diffs.extend(f"{urn} {aspect_name}: {d}" for d in found)

    for mcp in patches:
        cls = ASPECT_NAME_MAP[mcp.aspectName]
        read = graph.get_aspect(mcp.entityUrn, cls)
        ops = json.loads(mcp.aspect.value)
        found = patch_diffs(ops, read.to_obj() if read is not None else None)
        diffs.extend(f"{mcp.entityUrn} {mcp.aspectName} (PATCH): {d}" for d in found)

    print(f"Read back {len(latest)} aspects and {len(patches)} patches.")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", default="http://localhost:8080")
    args = parser.parse_args()

    from datahub.ingestion.graph.client import DatahubClientConfig, DataHubGraph

    graph = DataHubGraph(DatahubClientConfig(server=args.server))
    print(f"Server {graph.server_config.service_version} at {args.server}")

    # Baseline first, against the still-empty server: once entities exist,
    # the default processors emit extra PATCHes (e.g. `status`) that the
    # ingestion itself never sent.
    emitted = _emitted(graph)
    problems = _ingest(args.server)
    problems += _read_back(graph, emitted)

    if problems:
        print(f"\nVersion check FAILED: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nVersion check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
