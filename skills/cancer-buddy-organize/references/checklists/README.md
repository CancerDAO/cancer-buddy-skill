# Cancer-Type Minimum Data Checklists

These YAML files drive `missing_items.json` generation in `cancer-buddy-organize`. For each cancer type, they list the **minimum investigations and documents** that the patient should gather to enable a standard-of-care treatment plan + clinical trial matching.

| File | Cancer Type | Source guidelines |
|---|---|---|
| [CRC.yaml](CRC.yaml) | Colorectal | NCCN Colon/Rectal v3.2024 + CSCO 2024 |
| [NSCLC.yaml](NSCLC.yaml) | Non-Small-Cell Lung | NCCN NSCLC v4.2024 + CSCO 2024 |
| [SCLC.yaml](SCLC.yaml) | Small-Cell Lung | NCCN SCLC 2024 + CSCO 2024 |
| [BC.yaml](BC.yaml) | Breast | NCCN Breast v4.2024 + CSCO 2024 |
| [GC.yaml](GC.yaml) | Gastric | NCCN Gastric v2.2024 + CSCO 2024 |
| [EC.yaml](EC.yaml) | Esophageal | NCCN Esophageal 2024 + CSCO 2024 + ESMO |
| [HCC.yaml](HCC.yaml) | Hepatocellular | NCCN Hepatobiliary v3.2024 + CSCO 2024 |
| [CCA.yaml](CCA.yaml) | Cholangiocarcinoma | NCCN Hepatobiliary 2024 + CSCO 2024 + ESMO |
| [PDAC.yaml](PDAC.yaml) | Pancreatic (ductal adeno) | NCCN Pancreatic 2024 + CSCO 2024 |
| [OC.yaml](OC.yaml) | Ovarian | NCCN Ovarian 2024 + CSCO 2024 + ESMO |
| [CC.yaml](CC.yaml) | Cervical | NCCN Cervical 2024 + CSCO 2024 |
| [UCEC.yaml](UCEC.yaml) | Endometrial / Uterine | NCCN Uterine 2024 + FIGO/ESGO 2023 |
| [PC.yaml](PC.yaml) | Prostate | NCCN Prostate 2024 + CSCO 2024 |
| [RCC.yaml](RCC.yaml) | Renal Cell | NCCN Kidney 2024 + CSCO 2024 |
| [BLCA.yaml](BLCA.yaml) | Bladder / Urothelial | NCCN Bladder 2024 + CSCO 2024 |
| [THCA.yaml](THCA.yaml) | Thyroid | NCCN Thyroid 2024 + ATA + CSCO 2024 |
| [NPC.yaml](NPC.yaml) | Nasopharyngeal | NCCN Head&Neck 2024 + CSCO 2024 |
| [HNSCC.yaml](HNSCC.yaml) | Head & Neck SCC | NCCN Head&Neck 2024 + CSCO 2024 |
| [DLBCL.yaml](DLBCL.yaml) | Diffuse Large B-Cell Lymphoma | NCCN B-Cell Lymphomas 2024 + Lugano + CSCO 2024 |

**Any cancer type without a shipped YAML above is handled at runtime** — the synthesis worker generates a checklist in-session from current NCCN/CSCO/ESMO standard-of-care (marked `checklist_version: <code>-rt<date>` + a `checklist_generated_runtime` warning); it never silently returns an empty checklist. The shipped YAMLs are the curated, cached common cases.

## Schema (informal)

```yaml
cancer_type: <code>            # CRC | NSCLC | BC | GC | HCC | ...
version: <code>-v<N>           # CRC-v1 — used as checklist_version in missing_items.json
last_updated: YYYY-MM-DD
sources: [<guideline citations>]

stages:
  all:                          # items needed regardless of stage
    - item: <plain-language description>
      priority: P0|P1|P2        # required
      category: pathology|imaging|lab|molecular|history|consent   # required
      reason: <why this is needed>   # recommended (most items carry it; not enforced)
  <stage-context>:              # e.g. "IV", "II-III", "early", "DTC", "BCLC B-C"
    - ...                       # keying varies by cancer type — TNM, histology
                                # (THCA DTC/MTC/ATC), risk group, or early/advanced

followup:                       # OPTIONAL top-level block (sibling to `stages:`)
  - item: <surveillance item>   # post-treatment / surveillance items, applied
    priority: P0|P1|P2          # regardless of stage. FORWARD-LOOKING reference —
    category: lab|imaging|...    # NOT unioned into the missing-now `missing_items.json`
                                # diff; consumed by downstream monitoring features.
```

> **Block-name uniformity**: the surveillance block is a single key `followup:` across all YAMLs (earlier files used `postoperative_followup` / `response_followup` / `posttreatment_followup` — reconciled to one name so consumers find it deterministically).

The synthesis worker:

1. Reads `profile.json.summary.stage` + `profile.json.summary.primary` (v3 nested under `summary`) → maps to a cancer_type code.
2. Loads the matching YAML; if none is shipped for that code, generates the checklist in-session (see the runtime note above).
3. Unions `stages.all` with the closest-fit `stages.<stage>` block.
4. For each item, checks `profile.json` / `molecular.json` / `timeline.json` / `labs.json` to see if it's already present.
5. Emits the residual into `missing_items.json` sorted by priority (P0 first).

## Adding a new cancer type

1. Copy any existing YAML as template.
2. Update `cancer_type`, `version`, `sources`.
3. List the required items by stage. Each item needs `priority` + `category` (both required); `reason` is recommended but optional (the synthesis worker does not enforce it, and several shipped items omit it).
4. Reference up-to-date guideline (NCCN / CSCO / ESMO / ASCO).
5. Open PR; reviewer should be a clinical oncologist when the cancer type is new.

## Cancer-type code conventions

Use the most widely recognized abbreviation. Examples:

- CRC — Colorectal Cancer
- NSCLC — Non-Small-Cell Lung Cancer
- SCLC — Small-Cell Lung Cancer
- BC — Breast Cancer (TNBC / HRPBC etc. are histology/receptor SUBTYPES, not stage_context keys — the shipped `BC.yaml` keys its `stages` block by TNM stage like the other YAMLs; record subtype as an item, not a stage key)
- GC — Gastric Cancer
- HCC — Hepatocellular Carcinoma
- PDAC — Pancreatic Ductal Adenocarcinoma
- OC — Ovarian Cancer
- CCA — Cholangiocarcinoma
- EC — Esophageal Cancer
