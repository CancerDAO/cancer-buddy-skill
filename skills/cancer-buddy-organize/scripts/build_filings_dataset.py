#!/usr/bin/env python3
"""Build the L1 dataset `cn-biomed-newtech-filings.jsonl` from the source xlsx.

L1 is a structured fact layer, not a document layer, and no L1 dataset is
admitted without an update path -- this script is that path: rerun it when a new
filing batch is published.

Fixes the four defects the 2026-08-03 end-to-end run exposed
(`docs/prd/reference-library-and-instruction-layer.md` §5.9):

  1. target spellings are normalised through an alias table, and every record
     carries all known surface forms, so searching `Claudin18.2` or `CLDN18.2`
     returns the same rows;
  2. `targets[]` is an indexed field instead of something to be guessed from
     the free-text title;
  3. the technology keyword table is broadened, and titles that name a cell
     product without naming its modality get an explicit
     "细胞治疗（类型未标明）" tag rather than an empty list;
  4. `sponsor_institution` and `research_institution` are both emitted, plus
     `institutions_differ`, because the institution a patient must contact is
     the RESEARCH institution -- 17 of 59 rows disagree.

Reads xlsx with the standard library only (zipfile + ElementTree); no openpyxl.

Usage:
  python3 build_filings_dataset.py --out-dir /tmp/library --report
  python3 build_filings_dataset.py --src FILE.xlsx --as-of 2026-07-22 \
      --latest-batch 第4批 --source-url https://...
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
T_TAG = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"

DATASET_ID = "cn-biomed-newtech-filings"
DATASET_REL = f"datasets/{DATASET_ID}.jsonl"
DEFAULT_SRC = Path("~/CancerDAO/library/datasets/source_biomed-newtech-filings_b1-4.xlsx")

COLUMNS = {
    "province": "省级行政区",
    "filing_no": "备案号",
    "project_title": "项目名称",
    "sponsor_institution": "临床研究发起机构",
    "research_institution": "临床研究机构",
    "batch": "所属批次",
}

# --------------------------------------------------------------------------
# Defect 1 + 2: target alias table. Canonical name first, then surface forms
# that appear in filing titles. Matching is case-insensitive and ignores
# hyphens/spaces between the token and its number.
# --------------------------------------------------------------------------
TARGET_ALIASES: dict[str, list[str]] = {
    "CLDN18.2": ["CLDN18.2", "CLDN-18.2", "Claudin18.2", "Claudin-18.2", "Claudin 18.2", "CLDN18-2", "克劳丁18.2"],
    "MET": ["C-MET", "cMET", "c-Met", "MET基因", "间质表皮转化因子"],
    "CD19": ["CD19"],
    "CD20": ["CD20"],
    "CD22": ["CD22"],
    "CD7": ["CD7"],
    "CD30": ["CD30"],
    "CD70": ["CD70"],
    "CD123": ["CD123"],
    "BCMA": ["BCMA", "B细胞成熟抗原"],
    "GPC3": ["GPC3", "磷脂酰肌醇蛋白聚糖3"],
    "AFP": ["AFP", "甲胎蛋白"],
    "MSLN": ["MSLN", "mesothelin", "间皮素"],
    "FAP": ["FAP", "成纤维细胞活化蛋白"],
    "PD-1": ["PD-1", "PD1", "程序性死亡受体1"],
    "PD-L1": ["PD-L1", "PDL1"],
    "HER2": ["HER2", "ERBB2", "人表皮生长因子受体2"],
    "EGFR": ["EGFR", "表皮生长因子受体"],
    "TROP2": ["TROP2", "TACSTD2"],
    "B7-H3": ["B7-H3", "CD276"],
    "DLL3": ["DLL3"],
    "GD2": ["GD2"],
    "NKG2D": ["NKG2D"],
    "ROR1": ["ROR1"],
    "MUC1": ["MUC1"],
    "EpCAM": ["EpCAM"],
    "CEA": ["CEA", "癌胚抗原"],
    "EBV": ["EBV", "EB病毒", "Epstein-Barr"],
    "CD5": ["CD5"],
    "GPRC5D": ["GPRC5D"],
    "PSMA": ["PSMA"],
}

# --------------------------------------------------------------------------
# Defect 3: technology keyword table. Order matters -- the first pattern that
# matches wins for overlapping families (CAR-M before CAR-T etc.).
# --------------------------------------------------------------------------
TECHNOLOGY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("CAR-M", ["CAR-M", "CARM", "嵌合抗原受体巨噬细胞", "嵌合抗原受体单核细胞"]),
    ("CAR-NK", ["CAR-NK", "CARNK", "嵌合抗原受体自然杀伤细胞", "嵌合抗原受体NK细胞"]),
    ("CAR-DC", ["嵌合抗原受体树突状细胞", "CAR-DC"]),
    ("CAR-T", ["CAR-T", "CART细胞", "CAR T", "嵌合抗原受体T细胞", "嵌合抗原受体自体T细胞", "嵌合抗原受体的T细胞"]),
    ("TCR-T", ["TCR-T", "TCR T", "T细胞受体基因工程"]),
    ("TIL", ["TIL", "肿瘤浸润淋巴细胞"]),
    ("NK细胞", ["自然杀伤（NK）细胞", "自然杀伤细胞", "NK细胞"]),
    ("双特异性抗体", ["双特异性抗体", "BiTE", "双抗"]),
    ("抗原特异性T细胞", ["EBV特异性T细胞", "抗原特异性T细胞", "病毒特异性T细胞", "新抗原特异性T细胞"]),
    ("细胞毒性T淋巴细胞", ["MCTL", "细胞毒性T淋巴细胞", "CTL细胞"]),
    ("肿瘤引流淋巴结淋巴细胞", ["肿瘤引流淋巴结"]),
    ("DC疫苗", ["树突状细胞疫苗", "DC疫苗", "DC-CIK"]),
    ("CIK", ["CIK"]),
    ("肿瘤疫苗", ["肿瘤疫苗", "新抗原疫苗", "多肽疫苗", "mRNA疫苗"]),
    ("溶瘤病毒", ["溶瘤病毒", "溶瘤"]),
    ("外泌体", ["外泌体", "细胞外囊泡"]),
    ("基因编辑", ["基因编辑", "CRISPR", "敲除", "碱基编辑", "基因修饰"]),
    ("基因治疗", ["基因治疗", "腺相关病毒", "AAV", "慢病毒载体"]),
    ("间充质干细胞", ["间充质干细胞", "MSC", "华通氏胶"]),
    ("神经干细胞", ["神经干细胞", "神经前体细胞", "NSC"]),
    ("造血干细胞", ["造血干细胞", "脐带血移植"]),
    ("iPSC衍生细胞", ["iPS", "iPSC", "诱导多能干细胞"]),
    ("上皮/角膜缘干细胞", ["羊膜上皮干细胞", "角膜缘干细胞", "上皮干细胞"]),
    ("干细胞", ["干细胞"]),
    ("类器官", ["类器官"]),
    ("菌群移植", ["菌群移植", "粪菌", "肠道菌群"]),
    ("组织工程", ["组织工程", "生物3D打印", "支架材料"]),
    ("异种移植", ["异种移植", "猪源"]),
]

# Titles that name a cell product but no modality still get a tag, so the
# coverage number is honest instead of silently empty.
CELL_PRODUCT_MARKERS = ["细胞注射液", "细胞治疗", "细胞制剂", "细胞移植", "淋巴细胞", "T细胞"]
UNSPECIFIED_CELL_TAG = "细胞治疗（类型未标明）"

CANCER_KEYWORDS = [
    "癌", "肿瘤", "实体瘤", "白血病", "淋巴瘤", "骨髓瘤", "母细胞瘤", "肉瘤",
    "恶性血液", "转移性", "黑色素瘤", "胶质瘤",
]
# Substrings that contain a cancer keyword but do not indicate a cancer study.
CANCER_FALSE_FRIENDS = ["肉芽肿", "血管瘤样"]


def _norm(text: str) -> str:
    """Lowercase and drop separators so `Claudin-18.2` == `claudin18.2`."""
    return re.sub(r"[\s\-_－·]", "", text).lower()


def read_xlsx(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", NS):
                shared.append("".join(node.text or "" for node in item.iter(T_TAG)))
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows: list[dict[str, str]] = []
    header: dict[str, str] = {}
    for index, row in enumerate(sheet.find("m:sheetData", NS).findall("m:row", NS)):
        cells: dict[str, str] = {}
        for cell in row.findall("m:c", NS):
            ref = "".join(ch for ch in (cell.get("r") or "") if ch.isalpha())
            value_node = cell.find("m:v", NS)
            if value_node is None:
                inline = cell.find("m:is", NS)
                value = "".join(node.text or "" for node in inline.iter(T_TAG)) if inline is not None else ""
            elif cell.get("t") == "s":
                value = shared[int(value_node.text)]
            else:
                value = value_node.text or ""
            cells[ref] = value.strip()
        if index == 0:
            header = {ref: value for ref, value in cells.items() if value}
            continue
        if not any(cells.values()):
            continue
        rows.append({header.get(ref, ref): value for ref, value in cells.items()})
    return rows


def extract_targets(title: str) -> tuple[list[str], list[str]]:
    """Return (canonical targets, every known surface form of those targets)."""
    haystack = _norm(title)
    canonical: list[str] = []
    synonyms: list[str] = []
    for name, aliases in TARGET_ALIASES.items():
        if any(_norm(alias) in haystack for alias in aliases):
            canonical.append(name)
            for alias in aliases:
                if alias not in synonyms:
                    synonyms.append(alias)
    return canonical, synonyms


def extract_technology_tags(title: str) -> list[str]:
    haystack = _norm(title)
    tags: list[str] = []
    for tag, keywords in TECHNOLOGY_KEYWORDS:
        if any(_norm(keyword) in haystack for keyword in keywords):
            if tag not in tags:
                tags.append(tag)
    if "CAR-M" in tags or "CAR-NK" in tags or "CAR-DC" in tags:
        # `嵌合抗原受体巨噬细胞` also matches the generic CAR-T pattern in some
        # phrasings; keep the specific modality only.
        if "CAR-T" in tags and not re.search(r"CAR-?T|嵌合抗原受体(自体)?T细胞", title, re.IGNORECASE):
            tags.remove("CAR-T")
    if not tags and any(_norm(marker) in haystack for marker in CELL_PRODUCT_MARKERS):
        tags.append(UNSPECIFIED_CELL_TAG)
    return tags


def is_cancer_related(title: str) -> bool:
    cleaned = title
    for friend in CANCER_FALSE_FRIENDS:
        cleaned = cleaned.replace(friend, "")
    return any(keyword in cleaned for keyword in CANCER_KEYWORDS)


def build_records(rows: list[dict[str, str]]) -> list[dict]:
    records: list[dict] = []
    for row in rows:
        title = row.get(COLUMNS["project_title"], "")
        if not title:
            continue
        targets, synonyms = extract_targets(title)
        sponsor = row.get(COLUMNS["sponsor_institution"], "")
        research = row.get(COLUMNS["research_institution"], "")
        records.append(
            {
                "filing_no": row.get(COLUMNS["filing_no"], ""),
                "project_title": title,
                "sponsor_institution": sponsor,
                "research_institution": research,
                "institutions_differ": bool(sponsor and research and sponsor != research),
                "province": row.get(COLUMNS["province"], ""),
                "batch": row.get(COLUMNS["batch"], ""),
                "targets": targets,
                "target_synonyms": synonyms,
                "technology_tags": extract_technology_tags(title),
                "cancer_related": is_cancer_related(title),
            }
        )
    return records


README_TEMPLATE = """# L1 数据集：生物医学新技术临床研究备案项目表

由 `scripts/build_filings_dataset.py` 生成，请勿手工编辑。新批次公示后重跑脚本。

- 文件：`{dataset_rel}`（一行一条备案项目，JSONL）
- 收录：{record_count} 条，其中肿瘤相关 {cancer_count} 条
- 数据截止：{as_of}｜收录到：{latest_batch}
- 官方公示入口：{source_url}

## 字段

| 字段 | 说明 |
|---|---|
| `filing_no` | 备案号 |
| `project_title` | 项目名称（原文，未改写） |
| `sponsor_institution` | **申办/发起机构** |
| `research_institution` | **临床研究机构 —— 患者要联系的是这一栏** |
| `institutions_differ` | 两者是否不同（本批次 {differ_count} 条不同） |
| `province` / `batch` | 省级行政区 / 所属批次 |
| `targets` / `target_synonyms` | 归一后的靶点，及其全部已知写法（`CLDN18.2` 与 `Claudin18.2` 命中同一批记录） |
| `technology_tags` | 技术类别（CAR-T / CAR-M / TIL / 干细胞 …），标题未标明类型的细胞产品标 `{unspecified_tag}` |
| `cancer_related` | 是否肿瘤相关 |

**申办方 ≠ 研究机构。** 患者或家属打电话找的是 `research_institution`；
按 `sponsor_institution` 去联系会打错地方。呈现时两栏都要给，并说明区别。

## 呈现边界（硬，见 `references/reference-library.md`）

**备案 ≠ 可以入组 ≠ 适合本人。** 备案只说明该项目在该机构合法开展。
只呈现事实与联系路径；不排序、不推荐、不判断入组资格。
在招状态、最新批次属时效敏感项，回答时必须并列 answer-time 实时核验。
"""


def write_outputs(
    out_dir: Path,
    records: list[dict],
    *,
    as_of: str,
    latest_batch: str,
    source_url: str,
    retrieved_at: str,
) -> dict:
    dataset_path = out_dir / DATASET_REL
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    with dataset_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    entry = {
        "file": DATASET_REL,
        "title": "生物医学新技术临床研究备案项目表",
        "publisher": "国家卫生健康委员会（备案公示）",
        "version": f"收录至{latest_batch}",
        "date": as_of,
        "retrieved_at": retrieved_at,
        "lang": "zh",
        "redistribution": "allowed",
        "patient_scope": "general",
        "as_of": as_of,
        "latest_batch": latest_batch,
        "record_count": len(records),
        "update_cadence": "按批次公示，约季度级",
        "build_script": "skills/cancer-buddy-organize/scripts/build_filings_dataset.py",
    }
    if source_url:
        entry["source_url"] = source_url
    else:
        entry["notes"] = (
            "原始公示页尚未核实：公开检索只能确认至第3批，本表含第4批，可能来自转发整理版。"
            "来源确认前不得按官方公示原件引用。"
        )

    index_path = out_dir / "index.json"
    if index_path.is_file():
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
            raise SystemExit(f"existing {index_path} is not a canonical index.json")
    else:
        payload = {"schema_version": 1, "entries": []}
    payload["entries"] = [e for e in payload["entries"] if e.get("file") != DATASET_REL]
    payload["entries"].append(entry)
    payload["schema_version"] = 1
    payload["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    payload["generated_by"] = "build_filings_dataset.py"
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    differ = sum(1 for r in records if r["institutions_differ"])
    readme_path = dataset_path.parent / "README.md"
    readme_path.write_text(
        README_TEMPLATE.format(
            dataset_rel=DATASET_REL,
            record_count=len(records),
            cancer_count=sum(1 for r in records if r["cancer_related"]),
            as_of=as_of,
            latest_batch=latest_batch,
            source_url=source_url or "**待确认**（见 index.json `notes`）",
            differ_count=differ,
            unspecified_tag=UNSPECIFIED_CELL_TAG,
        ),
        encoding="utf-8",
    )
    return {
        "dataset": str(dataset_path),
        "index": str(index_path),
        "readme": str(readme_path),
    }


def summarise(records: list[dict]) -> dict:
    tag_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    for record in records:
        for tag in record["technology_tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for target in record["targets"]:
            target_counts[target] = target_counts.get(target, 0) + 1
    tagged = sum(1 for r in records if r["technology_tags"])
    targeted = sum(1 for r in records if r["targets"])
    return {
        "records": len(records),
        "cancer_related": sum(1 for r in records if r["cancer_related"]),
        "institutions_differ": sum(1 for r in records if r["institutions_differ"]),
        "technology_tag_coverage": f"{tagged}/{len(records)}",
        "target_coverage": f"{targeted}/{len(records)}",
        "technology_tags": dict(sorted(tag_counts.items(), key=lambda kv: -kv[1])),
        "targets": dict(sorted(target_counts.items(), key=lambda kv: -kv[1])),
        "provinces": len({r["province"] for r in records if r["province"]}),
        "research_institutions": len({r["research_institution"] for r in records if r["research_institution"]}),
        "batches": dict(sorted({b: sum(1 for r in records if r["batch"] == b) for b in {r["batch"] for r in records}}.items())),
    }


def _in_git_worktree(path: Path) -> Path | None:
    probe = path if path.exists() else path.parent
    for candidate in [probe, *probe.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    default_out = Path(__file__).resolve().parents[3] / "skills" / "cancer-buddy" / "references" / "library"
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out-dir", type=Path, default=default_out)
    parser.add_argument("--as-of", default="2026-07-22")
    parser.add_argument("--latest-batch", default="第4批")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--retrieved-at", default=None)
    parser.add_argument("--report", action="store_true", help="print coverage statistics")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-unverified-source",
        action="store_true",
        help="publish into a repository-tracked L1 root even though --source-url is empty",
    )
    args = parser.parse_args(argv)

    src = Path(args.src).expanduser()
    if not src.is_file():
        print(f"ERROR source workbook not found: {src}", file=sys.stderr)
        return 2

    records = build_records(read_xlsx(src))
    if not records:
        print("ERROR no rows parsed from the workbook", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir).expanduser()
    stats = summarise(records)

    if not args.dry_run:
        repo = _in_git_worktree(out_dir)
        if repo is not None and not args.source_url and not args.allow_unverified_source:
            print(
                "ERROR refusing to publish into the repository-tracked L1 root "
                f"({out_dir}) without --source-url: L1 means we vouch for the "
                "source, and this table's official page is unconfirmed "
                "(PRD §5.9). Pass --source-url once confirmed, or "
                "--allow-unverified-source to override deliberately.",
                file=sys.stderr,
            )
            return 2
        written = write_outputs(
            out_dir,
            records,
            as_of=args.as_of,
            latest_batch=args.latest_batch,
            source_url=args.source_url,
            retrieved_at=args.retrieved_at or dt.date.today().isoformat(),
        )
        stats["written"] = written

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if args.report:
        empty = [r["filing_no"] for r in records if not r["technology_tags"]]
        if empty:
            print(f"WARN {len(empty)} record(s) without a technology tag: {empty}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
