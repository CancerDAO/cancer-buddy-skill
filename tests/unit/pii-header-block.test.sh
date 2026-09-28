#!/usr/bin/env bash
# pii_rescan.py: the whole leading sidecar header block (consecutive `KEY: value`
# lines from line 1 to the first blank line, first key a known header key) is skipped,
# so SHA256 / EXTRACTOR / SECOND_READ_CHANNEL lines cannot false-fire; the body after
# the block is still scanned — including `KEY:`-looking body lines. Hex digests
# (sha256 / git sha / md5) are masked before the ≥11-digit shape, so source_inventory /
# update_log / organize_meta (delivered surfaces) do not fail on their own hashes.
# All values synthetic (phone-shaped strings are fake).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, sys
from pathlib import Path
repo, tmp = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, repo + "/skills/cancer-buddy-organize/scripts")
import pii_rescan as pr

passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


SHA_WITH_RUN = "a" + "12345678901" + "b" * 52           # 64 hex, holds an 11-digit run
assert len(SHA_WITH_RUN) == 64


_seq = [0]


def sidecar(text):
    _seq[0] += 1
    p = tmp / "05_影像" / "CT" / f"s{_seq[0]:03d}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return pr.scan_sidecar(p)


HDR = (f"SOURCE: raw/s001.jpg\nFILE_ID: f001\nEXTRACTOR: p1w-20300120-0930\n"
       f"PRIMARY_CHANNEL: deterministic_ocr:apple_vision\nSECOND_READ_CHANNEL: text_layer\n"
       f"INDEPENDENT_REREAD: true\nREAD_MODE: hybrid_verified\nADAPTER: none\nCONFIDENCE: 0.9\n"
       f"SHA256: {SHA_WITH_RUN}\nPAGE_LABEL: 第1页，共2页\nMODALITY: text\n")

check("header block (SHA256 hex digest with an 11-digit run, numbered worker id) does not false-fire",
      sidecar(HDR + "\n# 正文\n\n合成示例文字。\n") == [])
# the header VALUES are scanned: a sidecar without an inventory row has nothing binding them
res = sidecar(HDR.replace("PAGE_LABEL: 第1页，共2页", "PAGE_LABEL: 第1页 共1页 联系电话13812345678") + "\n# 正文\n\n合成\n")
check("a phone number written into PAGE_LABEL is found", any(t == "phone" for _, t, _ in res), str(res))
res = sidecar(HDR.replace(f"SHA256: {SHA_WITH_RUN}", "SHA256: 110101199003071234") + "\n# 正文\n\n合成\n")
check("SHA256 that is not a hex digest is scanned (an ID number there is found)",
      any(t == "id_number" for _, t, _ in res), str(res))
# an early / duplicated `## PII` heading no longer hides the body after it
res = sidecar(HDR + "\n## PII\n\n示例 联系电话 13812345678\n\n## PII\n\n- 无\n")
check("body after an early `## PII` heading is still scanned", any(t == "phone" for _, t, _ in res), str(res))
check("mask_snippet never echoes the value", "13812345678" not in pr.mask_snippet("13812345678", "phone")
      and "张测试" not in pr.mask_snippet("张测试", "identity_denylist"))
res = sidecar(HDR + "\n# 正文\n\n联系电话 13800138000\n")
check("body after the header block is still scanned", any(t == "phone" for _, t, _ in res), str(res))
res = sidecar(HDR + "\n# 正文\n\nEXTRACTOR: 13800138000\n")
check("a KEY:-looking line AFTER the blank line is scanned", any(t == "phone" for _, t, _ in res), str(res))
res = sidecar("PATIENT_ID: 110101199003071234\nSOURCE: raw/x.jpg\n\n正文\n")
check("block not starting with a known header key is NOT skipped", any(t == "id_number" for _, t, _ in res), str(res))
# an unknown KEY: line right under a known header key ENDS the exempt block (it used to
# ride along as "header" and skip the shape scan)
res = sidecar("SOURCE: s009\nMRN: 110101199003071234\nPHONE: 13800138000\n\n正文\n")
check("`MRN:` identifier directly under `SOURCE:` is scanned (id_number)", any(t == "id_number" for _, t, _ in res), str(res))
check("…and the phone line after it too", any(t == "phone" for _, t, _ in res), str(res))
check("header_block_length stops at the first unknown key",
      pr.header_block_length(["SOURCE: s1", "MRN: 1", "FILE_ID: f1", ""]) == 1)
res = sidecar(HDR.replace("MODALITY: text\n", "MODALITY: text\nCONTACT: 13800138000\n") + "\n# 正文\n")
check("an unknown key after the last pinned key is scanned", any(t == "phone" for _, t, _ in res), str(res))
res = sidecar("正文第一行\nSOURCE: raw/x.jpg\n")
check("header-less sidecar: nothing skipped", res == [])
res = sidecar(HDR + "\n# 正文\n\n样本号 12345678901234\n")
check("a bare ≥11-digit id in the body still fires", any(t == "numeric_id" for _, t, _ in res), str(res))
res = sidecar(HDR + f"\n# 正文\n\n原始读数引用 {SHA_WITH_RUN}\n")
check("a hex digest in the body does not fire", res == [], str(res))
check("parse_header returns the block", pr.parse_header(HDR + "\nbody\n")["SHA256"] == SHA_WITH_RUN)
check("all-digit 64-char run is NOT treated as a digest", pr.scan_line("1" * 64) != [])

# the appendix blocks sit BEFORE `## PII` and are body: identifiers inside them are found
UNC = ("\n# 正文\n\n联系[OCR_UNCERTAIN:U-001]\n\n## 高风险字段复读\n\n| 字段 | 行 | 主通道 | 第二通道 | 一致 |\n"
       "|---|---|---|---|---|\n| 日期 | 4 | 2030-01-10 | 2030-01-10 | 是 |\n\n## 不确定字段\n\n- id: U-001\n  line: 4\n"
       "  readings:\n    - {channel: llm_vision, text: \"13800138000\", confidence: 0.4}\n\n## PII\n\n- 电话 13900139000\n")
res = sidecar(HDR + UNC)
check("phone inside a `## 不确定字段` reading → finding", any(t == "phone" and s == "13800138000" for _, t, s in res), str(res))
check("…and a value written into the `## PII` trailer is found too (it lists categories, never values)",
      any(s == "13900139000" for _, _, s in res), str(res))
res = sidecar(HDR + "\n# 正文\n\n合成\n\n## 列配对\n\n- 数值列原串：13800138000\n\n## PII\n\n- 无\n")
check("identifier inside `## 列配对` → finding", any(t == "phone" for _, t, _ in res), str(res))

# delivered surfaces: inventory / update_log / organize_meta hashes do not fire
pd = tmp / "pt"
pd.mkdir()
(pd / "source_inventory.json").write_text(json.dumps({"files": [{"sha256": SHA_WITH_RUN}]}), encoding="utf-8")
(pd / "update_log.json").write_text(json.dumps({"entries": [{"inputs": [{"sha256": SHA_WITH_RUN}]}]}), encoding="utf-8")
(pd / "organize_meta.json").write_text(json.dumps({"skill_commit": "0123456789a123456789b123456789c123456789",
                                                    "skill_fingerprint": "sha256:" + SHA_WITH_RUN}), encoding="utf-8")
surfaces, _ = pr.scan_delivered_surfaces(pd)
check("delivered hashes (inventory / update_log / organize_meta) are clean", surfaces == {}, str(surfaces))
(pd / "update_log.json").write_text(json.dumps({"entries": [{"note": "handle 12345678901"}]}), encoding="utf-8")
surfaces, _ = pr.scan_delivered_surfaces(pd)
check("a bare 11-digit run on a delivered surface still fires", "update_log.json" in surfaces, str(surfaces))
check("organize_meta.json is a delivered surface", "organize_meta.json" in pr.DELIVERED_SURFACES)
check("acute_findings.json is a scanned surface", "acute_findings.json" in pr.SYNTHESIZED_SURFACES)

print(f"pii-header-block: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
