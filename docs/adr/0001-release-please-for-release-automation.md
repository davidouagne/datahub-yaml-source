# Adopt release-please for release automation

**Status**: accepted

Yaml-source previously required a manually pushed `vX.Y.Z` git tag to trigger
a release. We replaced this with `release-please`, which keeps a running
"release PR" that bundles pending Conventional-Commit changes and only cuts
a release (version bump, changelog, PyPI publish) when that PR is merged.
We chose this over keeping the manual-tag flow to remove the toil of
hand-computing the next semver bump and hand-writing a changelog, and
because the sibling repo `datahub-healthdcat-ap-exporter` (same solo
maintainer) already runs this exact flow successfully, including a manual
`workflow_dispatch` recovery path for a tag whose automated run failed.

**Considered options**: keep the manual tag-push flow (rejected — pure
toil, no changelog automation, and it was the only mechanism the two
sibling repos didn't already share).

**Consequences**: Conventional Commit messages become load-bearing
throughout the repo, not just a style preference — `commitlint` and a
semantic PR-title check are now enforced in CI as a direct corollary of
this decision, since release-please parses commit messages to compute the
next version and changelog entries.
