# AGENTS.md

`datahub-yaml-source` is a standalone DataHub ingestion source plugin: it
reads a directory tree of declarative YAML ("metadata as code") and emits
the DataHub entities they describe. No SQL parsing, no live connection —
translation only. See [README.md](README.md) for install/usage and
[_PLANNING.md](_PLANNING.md) for why the connector is shaped the way it is
(SDK V2 vs. raw MCP per kind, the cross-cutting `Has*` mixin architecture,
emission ordering, reference-resolution strategy).

Full dev workflow — setup, running tests, regenerating docs, adding a new
`kind:`, code style, submitting changes — lives in
[CONTRIBUTING.md](CONTRIBUTING.md). Read it before making a change; it is
written for exactly this purpose and this file does not repeat it.

## The one rule that bites silently

Editing `src/datahub_yaml_source/models.py` and stopping there leaves the
repo in a broken state that only shows up in CI, not locally at a glance:
`docs/sources/yaml/reference.md` and the JSON Schema are generated from it.
After any model change, always run:

```bash
python scripts/generate_json_schema.py
python scripts/generate_markdown_docs.py
```

and commit the regenerated files alongside the model change.
`tests/unit/test_json_schema_generation.py` /
`test_markdown_docs_generation.py` fail on drift, so treat a failure there
as "you forgot to regenerate," not as a bug to work around.

## Before trusting a secondhand algorithm description

If asked to reproduce an external/legacy system's ID or hashing scheme (e.g.
a pasted snippet claiming to describe it), don't implement it on faith — the
existing `container_key()` docstring in `src/datahub_yaml_source/urns.py` is
a worked example of a pasted snippet contradicting real production output.
Verify against a real, confirmed output value before trusting the
description, and say so explicitly if no such value is available yet.
