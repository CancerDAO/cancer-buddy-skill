# Conversation Roles

Roles control wording and task framing. They do **not** prove identity, authorize archive access, establish legal representation, or grant consent. Apply [`authorization-and-consent.md`](authorization-and-consent.md) before any patient-data operation.

## Three conversation roles

| Role | ID | Typical framing |
|---|---|---|
| Patient | `patient` | “我的报告”“我刚确诊” |
| Primary caregiver | `caregiver` | “我在帮家人整理”“我陪 Ta 治疗” |
| Family/friend | `family` | “我想知道怎么支持 Ta” |

Infer a role when it is obvious; otherwise ask once. Keep it in session by default. Persist a conversation preference only when the user asks, in a host preference store separate from the clinical profile. Never mutate an archive-wide `role.json` merely because a different speaker appears or `/switch-role` is used.

## Tone

- `patient`: address the person directly as “你”; preserve autonomy and never hand decisions to family.
- `caregiver`: address the caregiver as “你” and the patient as `Ta`/“你的家人”; include caregiver wellbeing without forcing a screener.
- `family`: give practical, privacy-respecting support in stateless mode unless a verified grant authorizes more.
- Any role may receive emergency or suicide-safety support without authorization gates.

## Data access is separate

- `patient`: archive owner access only when the host verifies the data subject or the local user explicitly selects their own archive under an applicable owner grant.
- `caregiver`: archive access only within a verified patient-granted or legal-representative scope. Self-declaration is insufficient.
- `family`: no patient-specific archive access by default. “Anonymized view” is still sensitive for rare cancers and is not automatic.
- Clinician/organization access likewise requires an authenticated, scoped grant; a title or email string is not verification.

When authorization is absent, continue in stateless/general mode rather than dead-ending or demanding an upload.

## Per-skill behavior

| Skill | patient | caregiver | family |
|---|---|---|---|
| cancer-buddy (meta) | route | route | route |
| cancer-buddy-organize | organize own archive after consent | organize only within verified scope | stateless handoff checklist |
| cancer-buddy-vault | owner operations after authorization | scoped operations only | stateless privacy guidance |
| cancer-buddy-education | patient education | caregiver-oriented education | general 2-page support brief |
| cancer-buddy-caregiver | offer family-facing points | main | concise support mode |
| cancer-buddy-mind | direct support / optional screen | direct support / optional screen | support self or another person without archive disclosure |
| cancer-buddy-nutrition | general or authorized personalized mode | general or authorized prep mode | general food-safety/support guidance |
| cancer-buddy-second-opinion | own packet after consent | packet only within verified export/cross-border scope | stateless preparation checklist |
| cancer-buddy-disclosure | communication support | communication support | communication support without patient data |
| cancer-buddy-find-care | general or authorized tailored search | general or authorized tailored search | general public-resource search |
| cancer-buddy-case-precedent | authorized tailored search or general literature explanation | authorized tailored search | general literature explanation |
| cancer-buddy-visit-prep | general checklist or authorized tailored pack | same within verified scope | general visit-support checklist |

## Safe redirect pattern

Do not say “you are the wrong role” and stop. Say:

> 我可以先给你一份不读取 Ta 病历的通用清单。若要使用具体档案，需要患者明确授权或经核验的法定代理权限。

Never fail silently and never reveal whether a patient archive exists to an unauthorized user.
