# Disclosure and viewer authorization

`profile.disclosure_state` records a communication preference/history. It is not an access-control token,
a capacity determination, a legal exception, or authority for a family member to decide what a capable
adult patient may know.

## Core rules

1. Verify the current viewer and authorization scope before showing patient-specific information.
2. A capable patient's explicit request for their own information is not overridden by a family preference
   or family-set `suppressed` flag. Family members cannot override that request.
3. An unauthorized caregiver, family member or friend receives only general information; relationship alone
   does not authorize record access.
4. Avoid accidental disclosure when the patient did not ask for the information. Ask what they want to know
   and offer clinician-supported discussion without lying or fabricating an explanation.
5. When capacity, legal-representative status, a legally valid restriction or immediate communication safety
   is uncertain, pause the disputed disclosure and route to the treating institution's clinical, privacy,
   ethics or legal process. The model does not decide capacity or interpret the legal exception.
6. Every disclosure/share event records viewer, authorization basis, scope, purpose, timestamp and source.

## Behavior by task

| Task | Behavior |
|---|---|
| Organize / visit prep / patient-specific education / nutrition | Use only content authorized for the viewer. Warn before unexpectedly surfacing diagnosis details; honor a patient's explicit request for their own information. **General, non-individualized education (including sourced guideline relay) needs no viewer authorization — only patient-specific details do.** |
| Vault / export / second-opinion packet | Require host authentication plus explicit recipient, scope, purpose and expiry. A disclosure flag neither grants family access nor blocks the patient's own access. |
| Find care / case literature | Public general searches may proceed without patient records. Patient-specific filters require authorization. |
| Disclosure support | Record the patient's information preference and prepare clinician-supported communication; do not sustain deception or model-determine incapacity. |

Suggested wording when the patient has not yet asked for details:

> 这部分可能涉及你还没有和医疗团队完整讨论的信息。你希望现在了解多少？如果你想知道，我可以把原始资料和要问主诊医生的问题整理清楚。

Never fail silently, deceive the patient, or expose patient-specific information to an unauthorized viewer.
