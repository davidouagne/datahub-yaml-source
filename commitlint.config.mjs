// Conventional Commits policy (issue #52, part of the #48 standardization
// epic). Checked in CI by wagoid/commitlint-github-action
// (.github/workflows/commit-policy.yml) against every non-merge commit in
// a PR -- commitlint's built-in default-ignores rule already exempts
// merge-commit-shaped messages ("Merge pull request #N ...", "Merge
// branch '...'"), so no extra filtering is configured here.
//
// Design contract: spec/spec-process-cicd-commit-policy.md
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Dependabot's own commit subjects are capitalized ("Bump X from Y to
    // Z", "Update ... requirement" -- see this repo's actual merged
    // Dependabot commits), and this repo's own history already mixes
    // Sentence case and lowercase subjects. No case is enforced.
    'subject-case': [0],
    // A grouped Dependabot PR's commit body/footer (updated-dependencies
    // trailer block, release-notes/changelog/compare-URL lines) routinely
    // exceeds 100 characters per line -- not part of this repo's actual
    // commit-message convention, so line length isn't enforced there.
    // (header-max-length is left at config-conventional's default: 100
    // chars, which already matches the longest header in this repo's own
    // history.)
    'body-max-line-length': [0],
    'footer-max-line-length': [0],
  },
};
