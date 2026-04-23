# Integration Journey Test

Manual smoke test — one patient case walked end-to-end through every v1 sub-skill. Run this test before merging to main.

## Setup

Pick an anonymized test case from `tests/fixtures/` (or create one). Test case requirements:
- At least 5 PDF/image files (imaging report, pathology report, gene panel, blood work, treatment summary).
- At least one molecular driver (e.g., EGFR L858R).
- At least one prior line of treatment.

Reset test patients dir:
```bash
export CANCER_BUDDY_PATIENTS_DIR=/tmp/cancer-buddy-journey-test
rm -rf $CANCER_BUDDY_PATIENTS_DIR
mkdir -p $CANCER_BUDDY_PATIENTS_DIR
```

## Steps

Open Claude Code in a test project and say:

### Step 1 — organize

Input: "抗癌搭子，我有一堆病历要整理" + point to fixture folder.

Expected:
- Meta-skill routes to `cancer-buddy-organize`.
- cb-organizer subagent runs.
- `patients/<pid>/profile.json` exists with required fields populated.
- `patients/<pid>/timeline.md` shows chronological treatment.
- `patients/<pid>/readiness.json` grade is B or higher (since fixture is complete).

Run validator:
```bash
python3 -c "
import json
p = json.load(open('$CANCER_BUDDY_PATIENTS_DIR/<pid>/profile.json'))
for k in ('patient_id','diagnosis','molecular','treatment_history'):
    assert k in p, f'missing {k}'
print('profile.json OK')
"
```

### Step 2 — explore

Input: "还有什么诊断我应该补？"

Expected:
- Routes to `cancer-buddy-explore`.
- Output file: `patients/<pid>/reports/explore/diagnostic-plan.md` and `pathway-options.md`.
- 4 tier menu visible.
- 8 pathway dimensions visible.

### Step 3 — mtb-lite

Input: "给我一份 MTB 报告。"

Expected:
- Routes to `cancer-buddy-mtb-lite`.
- vmtb-skill NOT installed during this test run → mtb-lite runs silently without asking.
- Output: `patients/<pid>/reports/mtb-lite/mtb-report.html` + `.md`.
- Every recommendation has evidence grade A/B/C/D.
- Not-Recommended section present.
- Complexity hint appears at end if case is complex.

### Step 4 — trial-match

Input: "帮我找临床试验。"

Expected:
- Routes to `cancer-buddy-trial-match`.
- Output: `patients/<pid>/reports/trials/trials-report.html` + `.md`.
- Every trial has criterion-level ✅/❌/⚠️/❓ breakdown.
- Uses "匹配" never "推荐".

### Step 5 — access

Input: "我想申请 osimertinib 的扩展准入。" (or whichever drug the fixture has).

Expected:
- Routes to `cancer-buddy-access`.
- Output: `patients/<pid>/reports/access/osimertinib.md`.
- All 5 pathways analyzed.

### Step 6 — manage

Input: "我现在在用 osimertinib，怎么监测？"

Expected:
- Routes to `cancer-buddy-manage`.
- Output: `dashboard.md`, `drug-interactions.md`, `monitoring-calendar.md`, `response-assessment.md`.

### Step 7 — vault

Input: "帮我建个数据保险箱。"

Expected:
- Routes to `cancer-buddy-vault`.
- `sharing-settings.json`, `access.log`, `vault-manifest.md` appear.
- All files default to 🔒 Private.

### Step 8 — education

Input: "生成一份给我家人看的宣教手册。"

Expected:
- Routes to `cancer-buddy-education`.
- Handbook .md file exists with: cover, quick reference, health summary, drug sheets, daily living guide, follow-up schedule, cost guide, FAQ.
- Handbook read the full MTB if present, otherwise mtb-lite.

## Post checks

Run:
```bash
bash scripts/validate-plugin.sh
```
Expected: `plugin structure OK`

Check profile.json was not modified after Step 1:
```bash
ls -la $CANCER_BUDDY_PATIENTS_DIR/<pid>/profile.json
# Note the mtime after Step 1. It should equal the mtime now.
```

## Pass criteria

All 8 steps produce expected outputs. `profile.json` is written exactly once (by organize). No Python or bash errors surfaced to the user. Every patient-facing term follows bilingual format.
