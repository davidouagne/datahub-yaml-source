# YAML Metadata Source

## Overview

Reads a directory tree of declarative YAML "metadata as code" files and emits the
DataHub entities they describe. This is not a connector for one external system —
it's a generic authoring format, closest in spirit to DataHub's built-in
`datahub-business-glossary` and `datahub-lineage-file` sources, generalized to
most of the DataHub entity model.

Every YAML document declares its own platform, environment, and (where relevant)
platform instance, so a single tree of files can describe entities spanning many
different source systems (e.g. `postgres`, `duckdb`, `dbt`, `s3`) without the
source itself connecting to any of them.

**Scope note**: through Phase 5B this was purely a *data* catalog format (datasets,
pipelines, BI assets, ML entities, the semantic layer). Phase 5C adds `REPOSITORY`,
`API`, `AGENT_SKILL`, `AI_AGENT`, and `SERVICE` — cataloging source-code repositories,
callable APIs, AI agents, and running services. This is a deliberate widening of the
connector's *subject matter* to a software/AI-agent catalog, not just its kind count:
these five entities describe software artifacts rather than data assets, and their
registry-permitted metadata is correspondingly thinner (e.g. `SERVICE` only accepts
`tags`/`owners`/`subTypes` among the cross-cutting aspects below).

## Capabilities

- Data platforms (registers custom platforms not built into DataHub)
- Tags, glossary terms/nodes (incl. related-term relationships), structured
  property definitions, domains (nestable via `parentDomain`)
- Containers (databases, schemas, ...), with automatic parent/child ordering
- Datasets: schema (columns, types, foreign keys), containers, tags, glossary
  terms, ownership, domains, applications, custom properties
- **Cross-cutting metadata uniformly on every kind that DataHub's entity
  registry permits it for**: `owners`, `tags`, `glossaryTerms`, `domains`,
  `applications`, `links` (institutional memory), `deprecation`,
  `structuredProperties`, `subTypes`. Which of these a given `kind` accepts is
  listed in that kind's own section of [reference.md](reference.md) — an
  unrecognized or not-applicable field is reported as a warning (or a hard
  error under `fail_on_unresolved_reference`), never silently dropped.
- Table-level and column-level lineage (`upstreamLineage`), fully hand-declared
  in the YAML — no SQL parsing is involved
- Column-level metadata: `tags`, `glossaryTerms`, `deprecation`, and
  `structuredProperties` on an individual `schema.fields[]` entry (e.g. tagging
  a single column as PII), emitted on that column's `schemaField` entity
- Charts and dashboards (BI-tool assets), linked to the datasets that feed
  them and to each other (a dashboard's charts, nested sub-dashboards)
- Saved/observed queries, with the dataset(s)/column(s) they read as subjects
- Data quality/operational incidents, optionally linked back to the
  `ASSERTION` that triggered them
- Knowledge-base documents (runbooks, FAQs, AI-context notes), authored
  natively or referencing an external system (e.g. Confluence)
- ML feature store metadata (feature tables, features, primary keys) and ML
  model versions/groups, including a full model card (intended use, ethical
  considerations, caveats, training/evaluation data, metrics, source code)
- Semantic-layer models (e.g. a dbt semantic model) and the business metrics
  defined against them, with AI-consumption hints (`aiContext`: synonyms,
  instructions, examples)
- **Software and AI-agent catalog** (`REPOSITORY`, `API`, `AGENT_SKILL`,
  `AI_AGENT`, `SERVICE`): source repositories, callable APIs, AI agents and
  their skills, and running services (including MCP servers) — see the note
  below, this is a genuine widening of the connector's subject matter beyond
  data assets
- Data products
- Pipelines (`DataFlow`/`DataJob`) with fine-grained lineage, job-to-job DAG
  edges (`inputDataJobs`), and optional parent containers
- Pipeline run history (`DataProcessInstance`, including incremental run events)
- Data quality assertions (freshness, volume, SQL, field-level, schema, custom)
- A small set of raw DataHub aspects that don't have their own `kind` (dataset
  profiles, usage statistics, operations, assertion/process-instance run events)

## Prerequisites

`*.yml` / `*.yaml` files in the format described below, provided via `path`
(a single location, or a list to combine several) in any of these ways:

- **Local directory** (default) — `path` points at an already-checked-out
  directory (e.g. a manually cloned git repository) on the filesystem where
  ingestion runs, scanned recursively. No network access or credentials are
  required.
- **`s3://bucket/prefix`** — listed recursively the same way a local
  directory is (paginated, arbitrarily deep). Requires the `s3` extra:
  `pip install datahub-yaml-source[s3]`, and `aws_connection` (same shape as
  other DataHub sources' AWS config — set it to `{}` to fall back to the
  default boto3 credential chain instead of explicit keys). See Mode C in
  [yaml_recipe.yml](yaml_recipe.yml).
- **`https://.../file.yml`** — unlike a local directory or an `s3://` prefix,
  an http(s) URL has no directory listing, so each entry must name a single
  file directly; since the format is multi-document YAML, one URL can still
  carry a whole catalog. A glob pattern in an http(s) URL is rejected with a
  clear error rather than silently matching nothing. `http_connection` is
  only needed for an authenticated endpoint (bearer token or basic auth) —
  omit it for a public URL. See Mode D in [yaml_recipe.yml](yaml_recipe.yml).
  Verified end-to-end against two real files from
  `https://raw.githubusercontent.com/aphp/datahub-sample/main/` (294
  workunits, 0 failures).
- **Automatic git clone** — set `git_info` and the source shallow-clones the
  repository itself into a temporary directory before scanning it; `path` then
  resolves relative to that checkout (default `"."`, or a subdirectory to
  scope the scan to a subtree) — `s3://`/`http(s)://` entries are not allowed
  in `path` together with `git_info`. Requires the `git` extra:
  `pip install datahub-yaml-source[git]`. `git_info` accepts the same shape as
  DataHub's `GitReference`/`GitInfo` (`datahub.configuration.git`), used the
  same way by the `lookml` and `odcs` sources — see `git_info` in
  [yaml_recipe.yml](yaml_recipe.yml) for fully-worked examples of both forms
  below.

  This source uses its own `git_info` type (`YamlGitInfo`, a subclass of
  DataHub's `GitInfo`) that fixes two `GitInfo.clone()` defaults which
  otherwise trip up a plain `repo: https://...` config:
  - **Public repo, no deploy key**: core's `GitInfo.clone()` always clones
    via `repo_ssh_locator`, which it derives as an SSH URL
    (`git@github.com:org/repo.git`) even when `repo` is a plain `https://`
    URL — with no deploy key, that SSH clone has no key to authenticate with
    and fails. `YamlGitInfo` instead derives an anonymous
    `https://.../repo.git` clone URL automatically whenever no
    `repo_ssh_locator`/`deploy_key`/`deploy_key_file` is set. Set
    `repo_ssh_locator` explicitly to override this — e.g. to force an
    ambient SSH key (agent or `~/.ssh`) instead of an HTTPS clone.
  - **Private repo**: set `deploy_key_file` or `deploy_key` to an SSH deploy
    key with read access; `repo_ssh_locator` is then inferred automatically
    as an SSH URL for GitHub/GitLab, same as core.
  - **Windows**: GitPython's `kill_after_timeout`, used internally to
    enforce the default 300s `clone_timeout`, is unconditionally unsupported
    on Windows and would otherwise make every clone fail outright
    (`'"kill_after_timeout" feature is not supported on Windows'`).
    `YamlGitInfo` disables `clone_timeout` automatically when running on
    Windows. Set `clone_timeout` explicitly to override this on any OS.

  Verified end-to-end against a real clone of
  `https://github.com/aphp/datahub-sample.git` on Windows, using only
  `git_info: {repo: https://github.com/aphp/datahub-sample, branch: main}` —
  no `repo_ssh_locator` or `clone_timeout` override (8 files, 1702
  workunits, 0 failures).

## Required Permissions

This source has no connection of its own, so there are no source-system
permissions to configure.

- Local directory mode: the DataHub ingestion process needs read access to the
  directory configured in `path`.
- Automatic git clone mode: the ingestion process needs outbound network
  access to the git host — over HTTPS (443) for a public repo (the default,
  no deploy key configured), or over SSH (22) for a private repo
  authenticated with a deploy key — and, for a private repository, an SSH
  deploy key with read access to that repository.
- `s3://` entries: the credentials in `aws_connection` (or the ambient boto3
  credential chain, if `aws_connection: {}`) need `s3:ListBucket` on the
  bucket and `s3:GetObject` on the scanned prefix.
- `http(s)://` entries: outbound network access to the host, and — for an
  authenticated endpoint — the bearer token or basic-auth credentials set in
  `http_connection`.

## Document Format

Every file may contain multiple YAML documents separated by `---`. Each document
is either:

- an **entity document**, identified by a `kind:` field, or
- a **raw aspect document**, identified by an `aspectName:` field (no `kind`)

### Editor autocomplete and validation (JSON Schema)

A [JSON Schema](schema/yaml-metadata.schema.json) describing every `kind` and
the raw aspect passthrough format is generated directly from the Pydantic
models in `datahub_yaml_source/models.py` (`scripts/generate_json_schema.py`)
— it can't drift from what the connector actually accepts.

To get autocomplete, inline validation, and hover documentation while
authoring `*.yml` files in VS Code (via the
[YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml))
or IntelliJ, add a modeline at the top of the file:

```yaml
# yaml-language-server: $schema=/path/to/datahub-yaml-source/docs/sources/yaml/schema/yaml-metadata.schema.json
kind: DATASET
...
```

(Use a relative path from the YAML file to the schema if both live in the same
repository checkout.)

Regenerate the schema after changing any model in `models.py`:

```bash
python scripts/generate_json_schema.py
```

A test (`test_checked_in_schema_is_up_to_date_with_models`) fails CI if the
checked-in schema and the models have drifted apart.

### Entity kinds

| `kind`                 | DataHub entity                       | Key fields                                                                             |
| ----------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------- |
| `DATA_PLATFORM`         | Data platform                         | `name`, `displayName`, `type`, `logoUrl`, `datasetNameDelimiter`                        |
| `TAG`                   | Tag                                    | `name`, `description`                                                                    |
| `GLOSSARY_NODE`         | Glossary node                          | `id`, `name`, `definition`, `parentNode`                                                 |
| `GLOSSARY_TERM`         | Glossary term                          | `id`, `name`, `definition`, `parentNode`                                                 |
| `STRUCTURED_PROPERTY`   | Structured property definition         | `qualifiedName`, `valueType`, `cardinality`, `allowedValues`, `entityTypes`, `settings`  |
| `DOMAIN`                | Domain                                 | `id`, `name`, `description`                                                              |
| `APPLICATION`           | Application                            | `id`, `name`, `description`, `applicationLineage` (consumes/produces `API`/`DATASET`)     |
| `CONTAINER`             | Container (database/schema/...)        | `platform`, `database`, `schema`, `parentContainer`, `subTypes`, `owners`                |
| `DATASET`               | Dataset (table/view/...)               | `platform`, `name`, `schema` (fields + foreignKeys), `container`, `upstreamLineage`, `viewProperties`, `applications`, ... |
| `CHART`                 | Chart/visualization (BI tool)          | `platform`, `name`, `chartUrl`, `chartType`, `container`, `inputDatasets`                |
| `DASHBOARD`             | Dashboard (BI tool)                    | `platform`, `name`, `dashboardUrl`, `container`, `charts`, `dashboards`, `inputDatasets` |
| `QUERY`                 | Saved/observed query                   | `id`, `statement`, `language`, `source`, `subjects`                                      |
| `INCIDENT`              | Data quality/operational incident      | `id`, `type`, `entities`, `status`, `assignees`, `source`, `notes`                        |
| `DOCUMENT`              | Knowledge-base document                | `id`, `title`, `text`, `status`, `platform`+`externalUrl` (external docs), `parentDocument`, `relatedAssets`, `relatedDocuments` |
| `MLFEATURE`             | ML feature                             | `featureNamespace`, `name`, `dataType`, `sources`                                       |
| `MLPRIMARY_KEY`         | ML feature table primary key           | `featureNamespace`, `name`, `dataType`, `sources`                                       |
| `MLFEATURE_TABLE`       | ML feature table                       | `platform`, `name`, `mlFeatures`, `mlPrimaryKeys`                                       |
| `MLMODEL_GROUP`         | ML model group                         | `platform`, `name`, `container`                                                          |
| `MLMODEL`               | ML model version                       | `platform`, `name`, `modelGroup`, `mlFeatures`, `hyperParameters`, full model card       |
| `SEMANTIC_MODEL`        | Semantic-layer model (dbt/Looker/...)  | `platform`, `path`, `id`, `nativeDefinition`, `datasets`, `aiContext`                    |
| `METRIC`                | Business metric definition             | `platform`, `path`, `id`, `semanticModel`, `expression`, `derivedFrom`, `relatedMetrics`, `datasetUpstreams`, `aiContext` |
| `REPOSITORY`            | Source code repository                 | `id`, `name`, `defaultBranch`, `languages`, `license`, `source`, `forkOf`, `platform`+`instance` |
| `API`                   | Callable API (REST endpoint, ...)      | `id`, `name`, `sourceRepository`, `restApi`, `signature`, `platform`+`instance`          |
| `AGENT_SKILL`           | AI agent skill / capability bundle     | `id`, `name`, `instructions`, `requiredTools`, `sourceRepository`, `platform`+`instance` |
| `AI_AGENT`              | AI agent                               | `id`, `name`, `tagline`, `instructions`, `source`, `dependencies`, `displayProperties`, `platform`+`instance` |
| `SERVICE`               | Running service (incl. MCP servers)    | `id`, `displayName`, `lifecycle`, `apis`, `sourceRepository`, `mcpServer`, `definition`, `platform`+`instance` |
| `DATA_PRODUCT`          | Data product                           | `id`, `name`, `domains`, `assets`, `structuredProperties`                                |
| `DATA_FLOW`             | Pipeline                               | `orchestrator`, `flowId`, `cluster`, `name`                                              |
| `DATA_JOB`              | Pipeline task                          | `jobId`, `dataFlow`, `inputDatasets`, `outputDatasets`, `fineGrainedLineages`             |
| `DATA_PROCESS_INSTANCE` | Pipeline run                           | `id`, `parentTemplate`, `inputs`, `outputs`, `runEvents`                                  |
| `ASSERTION`             | Data quality assertion                 | `id`, `assertion` (discriminated by `assertion.type`: `FRESHNESS` / `VOLUME` / `SQL` / `FIELD` / `DATA_SCHEMA` / `CUSTOM`), `assertionActions` |

### Raw aspect documents

For a handful of aspects that don't map to their own `kind` (mostly time-series
data), use `aspectName:` instead of `kind:`:

| `aspectName`                      | Entity reference field       |
| ---------------------------------- | ----------------------------- |
| `DATASET_PROFILE`                  | `dataset:`                    |
| `DATASET_USAGE_STATISTICS`         | `dataset:`                    |
| `OPERATION`                        | `dataset:`                    |
| `ASSERTION_RUN_EVENT`              | `assertionUrn:` (full URN)    |
| `DATA_PROCESS_INSTANCE_RUN_EVENT`  | `dataProcessInstanceUrn:` (full URN) |

All remaining fields in the document become the aspect's payload.

### View definitions

`viewProperties:` on a `DATASET` records the view's SQL (`viewLogic`, `viewLanguage`,
`materialized`, `formattedViewLogic`). It's usually paired with `subTypes: View`.
No lineage is inferred from `viewLogic` — the connector never parses SQL, so declare
`upstreamLineage:` explicitly if the view has upstream tables.

### Cross-references and dangling references

Fields like `tags:`, `glossaryTerms:`, `domains:`, `applications:`, and
`container:`/`parentContainer:` reference other entities by name/id, which may be
declared in a completely different file. The source loads the entire directory tree
before emitting anything, so these references resolve regardless of file order.

If a reference points at something that was never declared anywhere in the tree
(e.g. a typo in a tag name), the source still emits the association using the
deterministically-computed URN, but reports a warning — set
`fail_on_unresolved_reference: true` to turn that into a hard error instead.

### Unrecognized fields

A field that's either misspelled or not valid for its `kind` (DataHub's entity
registry doesn't permit that aspect on that entity type — e.g. `glossaryTerms:`
on a `TAG`) is also reported as a warning rather than silently ignored, naming
the file, the `kind`, and the field. `fail_on_unresolved_reference: true` turns
this into a hard error too. Check that kind's field table in
[reference.md](reference.md) to see exactly which fields it accepts.

### Container hierarchy ordering

Containers are always emitted with parents before children (required for
DataHub's browse-path generation), regardless of the order they appear in the
YAML files.

### Container URN computation (important)

**A container's URN is a GUID computed from `platform` + `database` + `schema`
only** — it is not derived from `name`. Any two `CONTAINER`/`container:`/
`parentContainer:` blocks with the same values for those three fields resolve
to the exact same URN, regardless of which file declares them, what `name`
each usage gives it, or what they say for `instance`/`env`.

```text
guid_input = {
  "platform": "<platform>",     # raw platform name, NOT a platform URN
  "database": "<database>",     # only if set
  "schema":   "<schema>",       # only if set
  # "instance" and "env" are NEVER part of the hash.
}
guid = md5(json.dumps(guid_input, sort_keys=True, separators=(",", ":")))
urn  = f"urn:li:container:{guid}"
```

This was confirmed against three real container GUIDs from a production
DataHub instance (a database container, its schema container, and a dataset's
`container:` reference to that same schema) — see
`test_container_urn_matches_known_production_guid_*` and
`test_container_urn_ignores_instance_entirely` in `tests/unit/test_urns.py`.

**Neither `instance` nor `env` ever affects the container URN.** `instance`
is only used to set the separate `dataPlatformInstance` *aspect*
(display/filtering) — it is never part of a container's identity. `env`
similarly doesn't distinguish containers across environments (`PROD` vs `DEV`
resolve to the same URN) — this is DataHub's own convention, not a bug:
containers represent structural concepts (a database, a schema) that aren't
duplicated per environment.

⚠️ Getting this exactly right took a few iterations: a description of a
legacy Java/Kotlin pipeline suggested `instance` should be included (wrapped
as a platform URN, or defaulted from `platform` when absent) — both turned
out to contradict real, confirmed production GUIDs once checked. **Always
trust a real, confirmed production GUID over a secondhand description of the
code that (supposedly) produced it**, if the two disagree.

**Practical consequence**: since `instance` and `env` don't matter, a
container is fully identified by `platform` + `database` + `schema` alone —
you're free to set (or omit) `instance`/`env` inconsistently across
`CONTAINER`/`container:`/`parentContainer:` references to the same logical
container without breaking the link.

## Example

See [yaml_recipe.yml](yaml_recipe.yml) for a fully-commented example recipe, and
`tests/integration/yaml_source/resources/` in this repository for a complete
worked example covering every supported `kind`.

For a complete, field-by-field reference of every `kind` (required/optional,
types, defaults), see the generated [reference.md](reference.md).

## Troubleshooting

- **"Unknown kind '...'"** / **"Unsupported raw aspectName '...'"**: the
  document's `kind`/`aspectName` isn't one of the values listed above — check
  for typos.
- **Dangling reference warnings**: a `tags:`/`glossaryTerms:`/`domains:`/
  `container:` value doesn't match any declared `TAG`/`GLOSSARY_TERM`/`DOMAIN`/
  `CONTAINER` document. The association is still emitted; fix the typo or add
  the missing declaration to silence the warning.
- **Container hierarchy looks wrong in the UI**: double-check that
  `parentContainer` on the child matches the parent's own top-level fields
  exactly (`platform`, `instance`, `database`, `env`) — a mismatch (e.g. an
  `instance` set on one but not the other) produces two different container
  URNs instead of a parent/child relationship.
- **`git_info` clone fails with "SSH authentication failed — the deploy key
  does not have read access..." on a public repo with no deploy key
  configured**: this shouldn't happen anymore — `YamlGitInfo` derives an
  anonymous HTTPS clone URL automatically whenever no
  `repo_ssh_locator`/`deploy_key`/`deploy_key_file` is set. If you see this,
  check whether `repo_ssh_locator` was set explicitly (it takes priority) to
  an SSH URL that shouldn't be used, e.g. left over from copying a private-repo
  example.
- **`git_info` clone fails with `'"kill_after_timeout" feature is not
  supported on Windows'`**: this shouldn't happen anymore either —
  `YamlGitInfo` disables `clone_timeout` automatically on Windows. If you see
  this, check whether `clone_timeout` was set explicitly to a non-null value
  (it takes priority over the automatic Windows default).
- **"'aws_connection' is required..."**: an `s3://` entry in `path` needs
  `aws_connection` set (use `{}` to fall back to the default boto3 credential
  chain instead of explicit keys).
- **`ModuleNotFoundError: No module named 'boto3'`** (or a report failure
  titled "Cannot read s3:// path(s)"): install the `s3` extra —
  `pip install datahub-yaml-source[s3]`.
- **"Glob patterns are not supported for http(s):// URIs"**: an `http(s)://`
  entry in `path` has no directory listing — it must be the URL of a single
  YAML file, not a wildcard.
