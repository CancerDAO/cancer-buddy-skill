# Vendored: web-access

This directory (`skills/web-access/`) is **vendored** from an upstream project.
It is not original to cancer-buddy; do not edit the other files here directly.

| Field | Value |
|---|---|
| Upstream author | 一泽Eze |
| License | MIT |
| Version | 2.5.0 |
| Upstream repo | https://github.com/eze-is/web-access |
| Vendored on | 2026-06 |

## Local divergence (cancer-buddy hardening)

`SKILL.md` and `references/cdp-api.md` carry **deliberate cancer-buddy
rewrites** on top of upstream 2.5.0: patient-data-stays-local rules, explicit
consent before using a logged-in browser profile, read-only default, no
anti-bot/paywall circumvention, CDP demoted to last resort, runtime-neutral
paths, and a frontmatter reduced to `name` + `description` (required by
`scripts/validate_codex_skills.py`; upstream `license`/`github`/`metadata`
attribution lives in this file instead). `scripts/find-url.mjs` and
`scripts/match-site.mjs` are retained verbatim from upstream but are
**deliberately not referenced** by the hardened SKILL.md (local
history/bookmark mining is out of policy); treat them as inert vendored code.

## Re-syncing updates

Pull the new version from the upstream repo, but do **not** blindly overwrite
`SKILL.md` / `references/cdp-api.md` — re-apply the hardening above (or port
upstream changes into the hardened text), bump the version recorded above, and
re-run `python3 scripts/validate_codex_skills.py`. Everything else under
`skills/web-access/` except this `VENDOR.md` may be replaced from upstream.
