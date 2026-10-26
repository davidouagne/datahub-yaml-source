# Auto-merge low-risk Dependabot PRs

**Status**: accepted

Yaml-source previously required every Dependabot PR, including trivial
patch bumps, to be reviewed and merged by hand. We adopted the sibling
repo `datahub-healthdcat-ap-exporter`'s policy instead: patch-level bumps
(any dependency) and minor-level bumps to dev-only dependencies are
auto-merged once required CI checks pass; majors and minor bumps to
production dependencies still require manual review. This trades a small
amount of residual risk (an unexpected breaking change in a patch release
slipping through unreviewed) for meaningfully less manual toil on a
solo-maintained repo, mirroring a policy already operating without
incident on the sibling repo.

**Considered options**: keep full manual review of every Dependabot PR
(status quo, rejected as pure toil with no compensating benefit for
low-risk bumps); auto-merge everything including majors (rejected — majors
can carry real breaking changes that CI alone won't always catch).

**Revised 2026-10-26** (PR #112, aligned with the sibling's #110 and
#113): minor-level bumps to transitive (`indirect`) dependencies now
auto-merge too. PR #112 (certifi 2026.7.22 → 2026.10.19, CalVer read as a
semver minor) stayed open with green checks while the same bump
auto-merged on the sibling. Unlike the sibling, which only sees transitive
bumps as security updates, this repo's `allow: all` (issue #96) also
produces weekly version updates for them: we accept that, because
`uv.lock` is not shipped in the wheel, so such a bump only changes the
CI/dev environment the required checks validate. When Dependabot leaves
a single-dependency PR's bump type empty (an `indirect` security update),
the workflow derives it from the PR title; an unrecognized title stays in
manual review. Majors and minor bumps to direct production dependencies
still wait for review.
