# Changelog

## 0.1.0 - 2026-09-06

Initial source release of the existing decision and research scripts, with a
reviewed development baseline and explicit operating limits.

- Share agent guidance through `AGENTS.md` and a `CLAUDE.md` import.
- Refuse redirects on authenticated provider requests so credentials stay at
  the intended endpoint.
- Select the newest eligible injury report by its timestamp instant, including
  when reports use different timezone offsets.
- Reject historical-source and frozen-prediction manifest paths that leave
  their snapshot directory, including external symlinks.
- Raise dependency floors to the verified current releases and pin CI actions.
- Publish complete decision archives atomically and reject incomplete existing
  packages so interrupted writes cannot masquerade as preserved decisions.
- Add five synthetic integrity regression tests; the full suite has 44 tests.

This release does not refresh provider inputs, rewrite frozen research artifacts,
change recommendation policy, or enable a live draft integration. Code changes
invalidate existing source freezes by design; preserve earlier freezes and use
the documented amendment workflow when a new prospective baseline is approved.
