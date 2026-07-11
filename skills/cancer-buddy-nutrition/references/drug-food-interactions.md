# Drug-food and supplement interaction verification

This workflow prevents plausible but unsafe interaction advice. Model memory is not a source.

## Required inputs

Collect the exact product name, active ingredient, formulation, strength, country/region, current schedule as prescribed, and indication. Include prescription medicines, OTC products, vitamins, herbs, teas/powders and other supplements. If the medication list is incomplete or an OCR drug name is unconfirmed, do not personalize the interaction review.

## Source hierarchy

For each product, check a **current source for the user's jurisdiction**:

1. Current regulator-approved product label or medication guide (for example NMPA, FDA, EMA or the relevant national regulator).
2. The treating center's written instructions for that exact product/formulation.
3. Direct confirmation by the dispensing or oncology pharmacist.

An interaction database can help locate a question but does not override the current label or pharmacist. A blog, search snippet, marketing page, forum, or model training knowledge is not sufficient.

## Workflow

1. Transcribe the label's exact food, drink, supplement, timing, swallowing and missed-dose instructions with a source URL/document title, revision date if shown, jurisdiction and access date.
2. Separate `verified instruction`, `pharmacist clarification needed`, and `no relevant statement located`. The last category does **not** mean “no interaction.”
3. If sources conflict, formulations differ, the product cannot be identified, or the patient has organ dysfunction/polypharmacy, mark the item unresolved and route to the prescribing team/pharmacist.
4. Never create a severity color from pharmacology intuition. A red/urgent flag is reserved for an explicit label warning or a pharmacist/clinician instruction, quoted accurately.
5. Never advise changing a prescribed dose, medicine timing, or treatment. Never propose a supplement “separation window” as a workaround.

## Output record

For each item in `interactions-flagged.md`, record:

```yaml
product: <verbatim>
formulation_and_region: <verbatim or unknown>
status: verified_instruction | pharmacist_clarification_needed | no_relevant_statement_located
instruction_or_question: <locale prose; clinical entities verbatim>
source_title: <official label/team instruction/pharmacist>
source_url: <URL or not_applicable>
source_revision: <date or not_shown>
checked_at: <ISO date>
```

Patient-facing uncertainty wording: “I could not verify a food/supplement instruction for `<product>` from a current official source. That is not the same as confirming there is no interaction. Please check with the oncology pharmacist or prescribing team before changing food, supplements, or medicine timing.” Render this meaning in the resolved locale.

Herbal mixtures and supplements often lack reliable product composition or interaction data. List the full product/ingredients if available and use `pharmacist_clarification_needed`; do not infer safety from “natural,” food-sized use, or a gap between doses.
