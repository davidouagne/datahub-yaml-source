<!--
Rebase merge only (ADR-0005): every commit on this branch lands on `main`
as-is and feeds the changelog. The PR title never reaches history.
-->

## Summary

<!-- What and why, in a few lines. -->

## Checklist

- [ ] Every commit is a signed-off (`git commit -s`), valid Conventional Commit
      (`feat` / `fix` / `docs` / `build` / `ci` / `refactor` / `style` /
      `test` / `chore` / `perf` / `revert`).
- [ ] Clean branch history with no merge commit (interactive rebase before
      opening, update by rebase) — every commit lands on `main` as-is.
- [ ] `uv run pytest tests/unit tests/integration` passes.
- [ ] If `src/datahub_yaml_source/models.py` changed: `docs/sources/yaml/reference.md`
      and the JSON Schema were regenerated (`uv run python scripts/generate_json_schema.py`
      && `uv run python scripts/generate_markdown_docs.py`) and committed alongside it —
      see AGENTS.md's "one rule that bites silently".
- [ ] If the connector's output intentionally changed: the integration golden
      file was refreshed (`--update-golden-files`) and the diff reviewed by hand.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy`
      are all clean.
