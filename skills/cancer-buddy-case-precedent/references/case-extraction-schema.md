# 病例抽取结构

每个字段保存原文、位置和标准化值，标准化不能覆盖原文。

```yaml
record_id: stable-id
citation:
  title: ""
  doi: null
  pmid: null
  direct_url: ""
  publication_status: published|corrected|retracted|expression_of_concern|unverified
  accessed_at: YYYY-MM-DD
patient:
  age_source: null
  sex_source: null
  diagnosis_source: null
  stage_source: null
  normalized_diagnosis: null
  normalized_stage: null
  normalization_status: verified|uncertain|not_done
disease:
  histology_source: null
  molecular_source: []
  test_method_source: []
  sample_context_source: []
treatment:
  intervention_source: []
  concomitant_treatment_source: []
  prior_treatment_source: []
outcomes:
  author_reported_response: null
  assessment_method: null
  follow_up: null
  adverse_events: []
  death_or_rapid_deterioration: null
  outcome_missing: false
provenance:
  field_quotes: []
  page_or_section: []
duplicate_case_links: []
uncertainties: []
```

Rules:

- `author_reported_response` is copied only when the publication states it; do not calculate RECIST.
- “Not reported” remains null/unknown; no model normalization may invent intent, stage, status or outcome.
- Record concurrent interventions so causal attribution is not implied.
- Keep negative outcomes and severe adverse events with the same visibility as favorable outcomes.
- Patient-level details must remain within copyright, privacy and data-use limits; use short quotations only when necessary for verification.
