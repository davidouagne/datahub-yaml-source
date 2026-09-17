# Force a checkpoint release via Release-As, and stop hiding infra commit types from the changelog

**Status**: accepted

By 2026-09-17, 37 commits had landed on `main` since `v0.1.0` — all `ci:`,
`docs:`, `build:`, or `chore:`. None were `feat:`/`fix:`, so release-please
had nothing to propose: its version bump and changelog generation are both
driven off those two types. We still wanted to cut `v0.2.0` as a checkpoint
of the accumulated CI/tooling work, so we forced it with a `Release-As:
0.2.0` trailer on a dedicated commit, merged through a normal PR like every
other change in this repo (ADR-0001). Because that release's
substance is entirely `ci`/`build`/`chore`/`docs` work, we also removed
those types from `release-please-config.json`'s default `hidden: true`
`changelog-sections` — permanently, for all future releases, not just this
one — so the generated `CHANGELOG.md` actually reflects what shipped instead
of rendering an empty entry under a bumped version number.

**Considered options**: bypass release-please entirely via the
`workflow_dispatch` manual-tag recovery path (rejected — that path is
documented in `release.yml` as failure recovery, not a routine release
mechanism, and skips the PR/CHANGELOG step); wait for real `feat:`/`fix:`
work before releasing (rejected — the point was specifically to checkpoint
the infra work now); expose the hidden changelog sections only for this one
release and revert them afterward (rejected — not worth the extra commit
and git noise for a solo-maintained repo, where a fuller changelog going
forward is a net win, not a cost).

**Consequences**: every future release's changelog will now list routine
`ci`/`build`/`chore`/`docs` commits (e.g. routine Dependabot bumps) as
visible sections, not just `feat`/`fix`/`perf`/`revert` — changelogs will be
noisier but more complete. A version bump with no `feat:`/`fix:` commit no
longer implies "nothing happened, don't bother reading the changelog";
future readers should check the changelog content itself, not infer scope
from the version number's normal SemVer meaning.
