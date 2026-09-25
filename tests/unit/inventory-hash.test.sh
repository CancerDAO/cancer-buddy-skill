#!/usr/bin/env bash
# O-07 input inventory (scripts/inventory_hash.py): sha256 / size / page_count for every
# input, a skip ledger with the pinned reason enum, and de-identified handles only —
# the original upload names never reach stdout. Synthetic byte fixtures built here.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/skills/cancer-buddy-organize/scripts/inventory_hash.py"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$SCRIPT" "$tmp" "$REPO_ROOT" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
script, tmp, repo = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def pdf(n_pages: int) -> bytes:
    kids = " ".join(f"{i + 3} 0 R" for i in range(n_pages))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()]
    objs += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>" for _ in range(n_pages)]
    out = b"%PDF-1.4\n"
    offs = []
    for i, o in enumerate(objs, start=1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


up = tmp / "upload"
(up / "__MACOSX").mkdir(parents=True)
(up / "子目录").mkdir()
files = {
    "张测试-门诊病历.jpg": b"\xff\xd8synthetic-jpeg-1",
    "子目录/报告两页.pdf": pdf(2),
    "张测试-门诊病历-副本.jpg": b"\xff\xd8synthetic-jpeg-1",   # byte-identical copy
    ".DS_Store": b"ds",
    "__MACOSX/._x.jpg": b"apple-double",
    "空文件.txt": b"",
    "打包.zip": b"PK\x03\x04synthetic",
    "无关截图.png": b"\x89PNGsynthetic",
    "排除.docx": b"PKdocx",
}
for rel, data in files.items():
    (up / rel).write_bytes(data)

p = subprocess.run([sys.executable, script, str(up), "--exclude", "排除.docx", "--quarantined", "无关截图.png",
                    "--mapping-out", str(tmp / "mapping.json")], capture_output=True, text=True)
check("exit 0", p.returncode == 0, p.stderr)
r = json.loads(p.stdout)
check("never prints an original upload name", all(name not in p.stdout for name in
      ("张测试", "门诊病历", "报告两页", "无关截图", "排除", "打包", "空文件")), p.stdout[:200])
ing = {row["input_ref"]: row for row in r["files"]}
check("two inputs ingested (duplicate skipped)", len(ing) == 2, str(list(ing)))
jpg = next(row for row in r["files"] if row["ext"] == ".jpg")
pdfrow = next(row for row in r["files"] if row["ext"] == ".pdf")
check("jpeg sha256/size", jpg["sha256"] == hashlib.sha256(files["张测试-门诊病历.jpg"]).hexdigest()
      and jpg["size_bytes"] == len(files["张测试-门诊病历.jpg"]))
check("image page_count 1", jpg["page_count"] == 1)
check("pdf page_count 2", pdfrow["page_count"] == 2, str(pdfrow))
reasons = sorted(s["reason"] for s in r["skipped_inputs"])
check("skip reasons", reasons == sorted(["duplicate_sha256", "ds_store", "macosx", "empty", "archive_container",
                                         "quarantined_irrelevant", "user_excluded"]), str(reasons))
check("skip rows carry exactly the 4 schema keys", all(set(s) == {"input_ref", "reason", "sha256", "size_bytes"}
                                                    for s in r["skipped_inputs"]))
dup = next(s for s in r["skipped_inputs"] if s["reason"] == "duplicate_sha256")
check("duplicate recorded against the kept input", r["duplicate_of"][dup["input_ref"]] == jpg["input_ref"])
check("handles are in-NNN / skip-NNN", all(k.startswith("in-") for k in ing) and
      all(s["input_ref"].startswith("skip-") for s in r["skipped_inputs"]))
mapping = json.loads((tmp / "mapping.json").read_text(encoding="utf-8"))
check("mapping (for raw/ only) resolves handles to names", mapping[jpg["input_ref"]] in ("张测试-门诊病历.jpg", "张测试-门诊病历-副本.jpg"))
check("no raw_path outside vault mode", "raw_path" not in jpg and r["vault_mode"] is False)

# page_count without pypdf (CI installs only jsonschema): the `/Type /Page` fallback
sys.path.insert(0, str(Path(script).parent))
import inventory_hash as ih
saved = sys.modules.get("pypdf", "absent")
sys.modules["pypdf"] = None          # makes `from pypdf import …` raise ImportError
try:
    three = tmp / "three.pdf"
    three.write_bytes(pdf(3))
    check("regex fallback counts pages (no pypdf)", ih.page_count(three) == 3, str(ih.page_count(three)))
    check("regex fallback: not a PDF → null", ih.page_count(tmp / "mapping.json") is None)
finally:
    if saved == "absent":
        del sys.modules["pypdf"]
    else:
        sys.modules["pypdf"] = saved

# vault mode: a de-identified raw/ vault → raw_path, organize infra entries ignored
vault = tmp / "PTX" / "raw"
(vault / "_extract").mkdir(parents=True)
(vault / "s001.jpg").write_bytes(b"\xff\xd8vault")
(vault / "_FILENAME_MAPPING.md").write_text("x", encoding="utf-8")
(vault / "_extract" / "s001.vision.txt").write_text("x", encoding="utf-8")
r = json.loads(subprocess.run([sys.executable, script, str(vault)], capture_output=True, text=True).stdout)
check("vault mode: only the upload is an input", [row.get("raw_path") for row in r["files"]] == ["raw/s001.jpg"]
      and r["skipped_inputs"] == [])

# file inputs: a worker's own file list, or an earlier archive's source_inventory.json
prior = tmp / "prior_archive"
prior.mkdir()
(prior / "source_inventory.json").write_bytes(b'{"schema": "source_inventory_v2.1", "files": []}\n')
pr = subprocess.run([sys.executable, script, str(prior / "source_inventory.json")], capture_output=True, text=True)
r = json.loads(pr.stdout)
check("single file input → one row, exit 0", pr.returncode == 0 and len(r["files"]) == 1
      and r["files"][0]["input_ref"] == "in-001", pr.stderr)
check("single file input: sha256 of its bytes", r["files"][0]["sha256"]
      == hashlib.sha256((prior / "source_inventory.json").read_bytes()).hexdigest())
two = [up / "张测试-门诊病历.jpg", up / "子目录" / "报告两页.pdf", up / "张测试-门诊病历-副本.jpg"]
pr = subprocess.run([sys.executable, script, *map(str, two), "--mapping-out", str(tmp / "m2.json")],
                    capture_output=True, text=True)
r = json.loads(pr.stdout)
check("file list: handles follow the input order", [x["input_ref"] for x in r["files"]] == ["in-001", "in-002"]
      and r["files"][1]["page_count"] == 2, str(r["files"]))
check("file list: a byte-identical later input is a duplicate skip",
      [(s["input_ref"], s["reason"]) for s in r["skipped_inputs"]] == [("skip-001", "duplicate_sha256")]
      and r["duplicate_of"] == {"skip-001": "in-001"}, str(r["skipped_inputs"]))
check("file list: upload names never reach stdout", "张测试" not in pr.stdout and "报告两页" not in pr.stdout)
m2 = json.loads((tmp / "m2.json").read_text(encoding="utf-8"))
check("file list: the private mapping keeps each input's name", m2["in-002"].endswith("报告两页.pdf"), str(m2))
mixed = subprocess.run([sys.executable, script, str(vault), str(prior / "source_inventory.json")],
                       capture_output=True, text=True)
r = json.loads(mixed.stdout)
check("dir + file: dir rows first, raw_path only for the vault rows",
      [x.get("raw_path") for x in r["files"]] == ["raw/s001.jpg", None], str(r["files"]))
bad = subprocess.run([sys.executable, script, str(tmp / "no-such-input")], capture_output=True, text=True)
check("an input that is neither file nor dir → exit 2", bad.returncode == 2)

# the skip ledger validates against source_inventory skipped_inputs[]
try:
    sys.path.insert(0, repo + "/tests/fixtures/organize-regress")
    import synlib
    inv = synlib.fixture_doc("source_inventory.json")
    up_r = json.loads(p.stdout)
    inv["skipped_inputs"] = up_r["skipped_inputs"]
    check("skipped_inputs output is schema-valid", synlib.schema_errors("source_inventory.schema.json", inv) == [])
except ImportError:
    print("SKIP: jsonschema not installed (schema half)", file=sys.stderr)

print(f"inventory-hash: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
