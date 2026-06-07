# Cover Letter Template — Doctor-to-Doctor

Front page of the packet. 250-400 words. Tone: respectful peer-to-peer, not apologetic, not promotional.

## Localization

Write the letter in **`reviewer_locale`** — the target reviewing center's language (derived in `SKILL.md` → Locale; NOT `profile.json.locale`). See [../../../references/i18n.md](../../../references/i18n.md).

- The body below IS the `en` rendering (and the source-of-truth when a concierge translates to `ja`). For any other `reviewer_locale`, treat the fixed scaffold lines — the salutation, "Enclosed you will find:", the enclosure list labels, "Primary oncologist:", "Sincerely," and the contact-block labels — as a **`reviewer_locale → string table`**; localize those keys, keep the letter's order and structure 1:1.
- **Clinical entities stay verbatim regardless of `reviewer_locale`**: the diagnosis-with-stage, drug names, regimen names, and any embedded clinical values. Never translate, transliterate, or normalize them — mistranslation is a P0 medical-safety bug.

The text below is the `en` string-table values:

---

[Date]

Attn: Second Opinion Consultation Desk
[Center name, e.g., Memorial Sloan Kettering Cancer Center]
[Address]

Re: Second opinion request — [Patient initials, MRN if domestic], [primary diagnosis]

Dear Dr. [name if known, else "Second Opinion Reviewer"],

I am writing on behalf of my [patient / my spouse / my parent / myself], [Patient initials], a [age]-year-old [M/F] diagnosed with [specific diagnosis with stage] in [YYYY-MM]. I am requesting your center's second opinion on [specific clinical question in one sentence].

[1-2 sentences on current treatment status and why the second opinion is sought — e.g., "We are at an inflection point: [patient] has progressed on first-line osimertinib after 20 months, and we are weighing three options proposed by the primary team: (1) continuation with local radiotherapy, (2) switch to platinum-doublet, (3) enrollment in a resistance-mechanism-directed trial. Your center's experience with post-osimertinib management would significantly inform our decision."]

Enclosed you will find:
- 2-page case summary
- Records index
- Pathology reports (including IHC) — [number] documents
- Molecular / NGS panel — [YYYY-MM, platform]
- Imaging reports + key images (CD / digital link) — [number] studies
- Treatment history from primary institution

Primary oncologist: [Dr. name, institution]; contact [email]. [He / She] speaks [English / Chinese] and is available for direct communication if helpful.

I understand a formal second opinion typically takes [2-4 weeks / per your process]. We are happy to provide additional records if needed. For follow-up, please reach us at:

- [Email]
- [Phone with country code]
- [WeChat ID if applicable and the center accepts this]

We recognize the significant workload at your center and are grateful for your consideration. The [patient's] family and primary team will honor whatever recommendations you provide — whether that is to continue the current plan, refer to a trial, or a different approach altogether.

Sincerely,

[Name], [relation — self, spouse, adult child, primary caregiver]
[Email / phone]

---

## Formatting rules

- One page printed
- Written in `reviewer_locale` (English values shown); clinical entities verbatim
- No marketing language ("best center in the world", "only hope")
- No specific financial questions in the cover letter (save for intake form or separate email)
- Always name the specific question — reviewers triage by question relevance
- Keep respectful — they see thousands of these
