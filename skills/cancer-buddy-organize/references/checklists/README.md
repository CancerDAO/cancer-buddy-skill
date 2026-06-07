# Cancer-Type Minimum Data Checklists

These YAML files drive `missing_items.json` generation in `cancer-buddy-organize`. For each cancer type, they list the **minimum investigations and documents** that the patient should gather to enable a standard-of-care treatment plan + clinical trial matching.

| File | Cancer Type | Source guidelines |
|---|---|---|
| [CRC.yaml](CRC.yaml) | Colorectal | NCCN Colon/Rectal v3.2024 + CSCO 2024 |
| [NSCLC.yaml](NSCLC.yaml) | Non-Small-Cell Lung | NCCN NSCLC v4.2024 + CSCO 2024 |
| [BC.yaml](BC.yaml) | Breast | NCCN Breast v4.2024 + CSCO 2024 |
| [GC.yaml](GC.yaml) | Gastric | NCCN Gastric v2.2024 + CSCO 2024 |
| [HCC.yaml](HCC.yaml) | Hepatocellular | NCCN Hepatobiliary v3.2024 + CSCO 2024 |

## Schema (informal)

```yaml
cancer_type: <code>            # CRC | NSCLC | BC | GC | HCC | ...
version: <code>-v<N>           # CRC-v1 — used as checklist_version in missing_items.json
last_updated: YYYY-MM-DD
sources: [<guideline citations>]

stages:
  all:                          # items needed regardless of stage
    - item: <plain-language description>
      priority: P0|P1|P2
      category: pathology|imaging|lab|molecular|history|consent
      reason: <why this is needed>
  <stage-context>:              # e.g. "IV", "II-III", "BCLC B-C"
    - ...
```

The synthesis worker:

1. Reads `profile.json.diagnosis.stage` + `primary_cancer` → maps to a cancer_type code.
2. Loads the matching YAML.
3. Unions `stages.all` with the closest-fit `stages.<stage>` block.
4. For each item, checks `profile.json` / `molecular.json` / `timeline.json` / `labs.json` to see if it's already present.
5. Emits the residual into `missing_items.json` sorted by priority (P0 first).

## Adding a new cancer type

1. Copy any existing YAML as template.
2. Update `cancer_type`, `version`, `sources`.
3. List the required items by stage. Each item needs `priority` + `category` + `reason`.
4. Reference up-to-date guideline (NCCN / CSCO / ESMO / ASCO).
5. Open PR; reviewer should be a clinical oncologist when the cancer type is new.

## Cancer-type code conventions

Use the most widely recognized abbreviation. Examples:

- CRC — Colorectal Cancer
- NSCLC — Non-Small-Cell Lung Cancer
- SCLC — Small-Cell Lung Cancer
- BC — Breast Cancer (use TNBC, HRPBC for subtypes in stage_context only)
- GC — Gastric Cancer
- HCC — Hepatocellular Carcinoma
- PDAC — Pancreatic Ductal Adenocarcinoma
- OC — Ovarian Cancer
- CCA — Cholangiocarcinoma
- EC — Esophageal Cancer
