# DataHub version support policy

**Status**: accepted (2026-11-06)

Decided on the wayfinder map
[Support several DataHub server (GMS) versions in parallel](https://github.com/davidouagne/datahub-yaml-source/issues/129).
The decision tickets hold the detail. Adapted from the sibling exporter's
[ADR-0004](https://github.com/davidouagne/datahub-healthdcat-ap-exporter/blob/main/docs/adr/0004-support-versions-datahub.md),
whose mechanisms are kept by default. Every deviation is listed below with
its reason. Terms (**Supported DataHub version**, **Version check**,
**Minimum server version**) are defined in `CONTEXT.md`.

## Decisions

1. **The target is the server.** A Supported DataHub version is a GMS
   version. The aim is 1.7.x → 1.9.x, but the announced range only ever
   contains verified minors: today `acryl-datahub>=1.7.0.9,<1.8` in
   `pyproject.toml`, which is the single source of the range. A minor enters
   only through a widening PR, reviewed by hand, that passed the Version
   check.

2. **Comparison is per minor.** Only the server's `major.minor` is compared
   with the minors the specifier covers. The patch-level floor `1.7.0.9` is a
   **client SDK constraint, not a server promise**: GMS 1.7 reports `v1.7.0`
   or `v1.7.0.1`, and every server patch is in range.
   *Deviation*: the exporter's `>=1.7` floor never raised this.

3. **Version check: local, never in CI.** `scripts/verify-datahub-version.sh
   <version> [--keep]` ingests the integration fixture
   (`tests/integration/yaml_source/resources`, every `kind:`) into an
   isolated Docker GMS through `datahub-rest` in `mode: SYNC`. It passes when
   the report has 0 failures and 0 warnings **and** every emitted aspect,
   read back from GMS (timeseries by latest value, the `PATCH` by resulting
   state), still contains what was sent.
   *Deviation*: the baseline is the run's own emitted MCPs, with no per-minor
   reference file and no `--update-reference`. GMS rejects an unknown aspect
   on rest.li but silently trims unknown fields (and drops unknown aspects on
   OpenAPI v3), so a clean report alone proves nothing
   ([research](https://github.com/davidouagne/datahub-yaml-source/issues/131)).

4. **Out of range: warn, don't block.** `YamlSource.__init__` reads
   `ctx.graph.server_config`, which is already fetched and cached. Out of
   range, unparsable, or DataHub Cloud → `report.warning`. No graph (`file`
   or `console` sink) → info log only. A recipe field `strict_version: false`
   turns every warning case, and the no-graph case, into an init failure.
   *Deviation*: a recipe field, since a source has no CLI flag like the
   exporter's `--strict-version`.

5. **Narrow preventive branching.** Every kind works on every supported
   server at or above its Minimum server version. That minimum is the range
   floor for all current kinds. Only a new kind or aspect may declare a
   higher one, in the PR that introduces it. One static table, *entity type
   / aspect name → minimum minor*, is applied by a single filter over emitted
   MCPs. On an older server the matching MCPs are skipped, with one
   aggregated warning per kind/aspect. When the version is unknowable,
   everything is emitted. The Version check excludes exactly those table-derived
   skips. No other exception list exists: a minor that breaks a kind gets an
   adaptation after the break is observed, or stays out of the range. Fields
   are never gated: a new field enters only when every supported minor keeps
   it.
   *Deviation*: the exporter allows no preventive branching. An emitter must
   be able to ship a recent kind without dropping older minors; a reader
   never faces that.

6. **CI covers the client surface.** The test job runs three legs:
   `highest` on Python 3.11 and 3.12 from the lock (coverage, Codecov), and
   `lowest` (`--resolution lowest-direct`, outside the lock, `uv run
   --no-sync`) on 3.11 without coverage. The golden file must match at the
   floor, otherwise the floor is wrong and gets raised. `ci-status` already
   covers every leg, so the ruleset doesn't change.

7. **Widening.** `CONTRIBUTING.md` documents the procedure, and the PR
   template carries "Version check passed on X.Y". Patches (`1.7.0.x`) stay
   auto-merged without a Version check. A client-side `datahub.sdk.*` break
   is caught by the `highest` leg, a server-side one by the Version check.
   Raising the floor past the previous minor drops server minors, so it is a
   breaking change (`!` + `BREAKING CHANGE:`).

8. **Tooling.** The exporter's `scripts/lib/datahub-isolation.sh` and
   `datahub-local.sh` are copied and adapted, with their source cited.
   Compose projects are named `dhys-verify-<version>` and
   `dhys-local-<version>`. No library is shared across the two repos.

## Considered options

- **Ceiling at the target (`<1.10` or `<2`)**: would announce minors never
  verified.
- **Docker integration workflow in CI**: about 10 minutes of quickstart per
  minor, for rare minor bumps that already get human review.
- **Clean ingest report as the whole Version check**: blind to silently
  trimmed fields and dropped aspects.
- **Per-minor committed read-back reference** (exporter style): would freeze
  server-added values that are not part of the promise.
- **No preventive branching at all** (exporter style): a new kind would
  force dropping older minors or waiting for the floor to catch up.
- **A hand-written exception list in the Version check**: would announce as
  supported a minor that loses what we emit.

## Consequences

- No breaking change today: the range is unchanged, and `strict_version` is
  additive.
- `packaging` becomes an explicit dependency (it is only transitive
  today), since the range is parsed from installed package metadata.
- `docs/sources/yaml/yaml.md`'s "Target GMS compatibility" becomes
  "Supported DataHub versions". The "older GMS" caveats, now simply out of
  range, go, and `_PLANNING.md`'s matching Known Limitations and open
  questions 2–3 are realigned. `schemaField` UI surfacing stays a deployment
  note, not a version matter.
- Widening to 1.8 waits for a non-yanked `acryl-datahub` 1.8 client (none
  as of 2026-11-06).
