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
