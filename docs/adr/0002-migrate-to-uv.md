# Migrate to uv for dependency management and packaging

**Status**: accepted

Yaml-source used plain `pip` with a legacy `setup.py` and no committed
lockfile, so local and CI environments could resolve slightly different
dependency versions within each declared range even on nominally identical
runs. We migrated the project to `uv` (a `pyproject.toml`-driven project
with a committed `uv.lock`) to get reproducible installs, matching the
sibling repo `datahub-healthdcat-ap-exporter`, which already validated this
doesn't break DataHub CLI plugin compatibility: the CLI discovers ingestion
sources via a standard `importlib.metadata` entry point
(`datahub.ingestion.source.plugins`) that is unaffected by which build
backend or installer produced the installed wheel.

**Considered options**: add a `pip-compile` (pip-tools) lockfile on top of
the existing `pip`/`setup.py` setup instead of migrating to `uv` (rejected
— it would leave the two sibling repos on two different toolchains
indefinitely, doubling the surface a solo maintainer has to remember).

**Consequences**: CI install steps change from `pip install -e .[...]` to
`uv sync`; local dev instructions in `CONTRIBUTING.md` need updating; this
is a real migration touching CI, docs, and local dev workflow, not a
config toggle.
