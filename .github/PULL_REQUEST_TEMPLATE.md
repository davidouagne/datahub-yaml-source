<!--
The PR title becomes the merge commit's subject: it must itself be a valid
Conventional Commit (type: subject, e.g. `fix: handle empty containers`),
same as every commit on this branch -- checked in CI (commit-policy.yml).
-->

## Summary

<!-- What and why, in a few lines. -->

## Checklist

- [ ] Every commit is a valid Conventional Commit (`feat` / `fix` / `docs` /
      `build` / `ci` / `refactor` / `style` / `test` / `chore` / `perf` /
      `revert`), and the PR title is too.
- [ ] `uv run pytest tests/unit tests/integration` passes.
- [ ] If `src/datahub_yaml_source/models.py` changed: `docs/sources/yaml/reference.md`
      and the JSON Schema were regenerated (`uv run python scripts/generate_json_schema.py`
      && `uv run python scripts/generate_markdown_docs.py`) and committed alongside it —
      see AGENTS.md's "one rule that bites silently".
- [ ] If the connector's output intentionally changed: the integration golden
      file was refreshed (`--update-golden-files`) and the diff reviewed by hand.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy`
      are all clean.
