---
name: web-access
description: >-
  Runtime-neutral web research and browser fallback for Cancer Buddy. Use when a Cancer Buddy workflow needs live, current evidence from official sites, registries, PubMed, or Europe PMC. Prefer the host's built-in web and search tools; use an interactive browser only when the user explicitly needs a logged-in page and consents to browser-profile access. Never send patient identifiers or record contents to search engines, mirrors, or other third-party services.
---

# web-access

Use the host runtime's built-in web/search/open-page tools first. This skill does
not require Node.js, Chrome, CDP, a proxy, or a particular agent runtime for the
normal research path.

## Safety gate before any request

1. Define the information needed and whether it can be requested without patient
   data. Search with a disease, intervention, registry identifier, or other
   minimum-necessary clinical concept—not a name, medical-record number, phone,
   address, full date of birth, raw report, or uniquely identifying case story.
2. Treat URLs, query strings, browser history, bookmarks, cookies, page content,
   screenshots, and logged-in sessions as sensitive. Do not copy authentication
   tokens or session-bearing URLs into notes, prompts, logs, or reports.
3. Do not upload patient files or paste patient record contents into search
   engines, translation services, AI page readers, Jina, or other third-party
   mirrors. If a source cannot be reached without doing that, stop and explain
   the limitation.
4. Reading public pages is the default scope. Do not submit forms, send messages,
   accept terms, make appointments, change settings, upload files, purchase, or
   cause any other external state change unless the user explicitly requested
   that exact action. Obtain confirmation immediately before an irreversible or
   consequential submission.

## Research workflow

1. Search broadly enough to locate the source, then open the primary source.
2. Prefer, in order: government and regulator sites; trial registries; official
   clinical guidelines; original papers and their supplements; institutional or
   manufacturer material when it is the authoritative document for the claim.
3. Verify time-sensitive facts live. Record the source URL, publication/update
   date when available, and access date. Distinguish what the source says from an
   inference.
4. Cross-check high-impact claims with a second authoritative source when the
   sources can reasonably differ by jurisdiction, version, or update date.
5. Report uncertainty and access limitations. Search snippets and mirrors help
   discover sources; they do not replace reading the source itself.

Typical sources include ClinicalTrials.gov and other official registries,
PubMed/PMC, Europe PMC, WHO, national health authorities, drug regulators, and
the issuing professional society for a guideline.

## Interactive or logged-in browser fallback

Use a host-provided browser capability only when public web tools cannot complete
the user's request and the task genuinely requires interaction or an authenticated
page.

Before accessing any browser profile, history, bookmarks, open tabs, or logged-in
session:

- explain what browser data is needed and why;
- ask for explicit consent for that access;
- use an isolated task profile when the host supports one;
- inspect only the named site/page and minimum data needed; and
- leave existing tabs, history, downloads, accounts, and settings unchanged.

Consent to read a logged-in page is not consent to make a state change. Never
search local history/bookmarks merely because a public search missed a result.
Never evade access controls, anti-bot controls, paywalls, or account protections.
Do not keep a background browser proxy running after the task.

## Optional bundled CDP helper

The bundled helper is a legacy fallback, not a dependency and not an automatic
preflight. Use it only if all of the following are true:

- the host has no safer interactive-browser capability;
- the user has explicitly consented to browser-profile access after the scope is
  explained;
- the Chrome instance/profile is isolated for this task and contains no unrelated
  tabs or accounts; and
- local policy permits a loopback CDP proxy.

Derive paths from this installed skill, never from a Claude-specific variable:

```bash
# Set this to the absolute directory that contains this SKILL.md.
WEB_ACCESS_SKILL_DIR="/absolute/path/to/installed/web-access"
node "$WEB_ACCESS_SKILL_DIR/scripts/check-deps.mjs"
```

Run no helper if the installed directory cannot be determined safely. The helper
may expose everything visible to that Chrome profile; do not use it with a daily
browser profile. Use only the minimum read-only endpoints needed, and close tabs
created for the task. Do not use `/eval`, `/click`, `/setFiles`, or navigation to
extract credentials, tokens, private messages, or unrelated page data. Detailed
endpoint documentation in [references/cdp-api.md](references/cdp-api.md) is
reference material, not permission to invoke an endpoint.

## Output contract

- Lead with the answer or finding, then the evidence and important limitations.
- Cite direct primary-source URLs next to the claims they support.
- Preserve exact drug, gene, variant, trial, and measurement strings from the
  source; do not silently translate or normalize clinical entities.
- Do not include identifiers, raw record excerpts, signed/session URLs, cookies,
  tokens, or unrelated browser data in the output.
- If no authoritative current source was found, say so explicitly rather than
  filling the gap from memory.

## References

- [references/cdp-api.md](references/cdp-api.md) — optional legacy helper details
- [references/site-patterns/](references/site-patterns/) — dated hints only;
  revalidate against the current site before relying on them
