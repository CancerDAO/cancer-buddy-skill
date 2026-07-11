# Disclosure Behavior

`disclosure_state` is a communication-planning hint, not access control. Missing means `unknown`. A family member's preference cannot permanently hide an authorized, decision-capable adult's own records or override that adult's expressed wish to know.

## Operating rules

- First verify archive authorization per [`authorization-and-consent.md`](authorization-and-consent.md). A self-declared caregiver/family role does not grant access.
- If the current speaker is the patient and asks to see their own authorized archive, do not redact diagnosis or stage merely because a caregiver previously wrote `suppressed`. Offer sensitive, paced communication and ask how much detail they want now.
- If the patient explicitly says they do not want details, honor that current preference while keeping a reversible path to ask later.
- If capacity is uncertain, do not let the model decide capacity or surrogate authority. Route the decision to the clinical team/ethics/social-work process while continuing general support.
- For minors, follow guardian/legal requirements and age-appropriate assent; do not use adult family-suppression rules.
- Other speakers receive only information within their verified authorization scope. When no grant exists, use stateless general mode.

## Skill adaptations

All skills may offer general, non-archive help. For authorized personalized output, ask the patient how much diagnostic detail should appear and provide a preview before generating or exporting. Second-opinion, public/research, and cross-border artifacts require explicit scope-specific consent and must not infer consent from `disclosure_state`.

Never fail silently, maintain deception, or reveal that an archive exists to an unauthorized person.
