#!/usr/bin/env python3
"""抗癌搭子 command line. Every command prints JSON on stdout.

  cb.py patients                                   list patient dirs under the root
  cb.py organize prepare <inputs…> [--patient DIR] [--locale zh]
  cb.py organize next|place|finish|check <DIR>
  cb.py organize note <DIR> --text … --layer patient_reported|caregiver_reported [--bucket 14] [--date YYYY-MM-DD]
  cb.py organize move <DIR> <sidecar> <bucket>
  cb.py organize discard <DIR> <sidecar> --confirm "<用户原话>"
  cb.py render summary <DIR>
  cb.py render visit-prep <DIR> <data.json>
  cb.py chart <DIR> <metric> [--title …] | cb.py chart <DIR> --list
  cb.py export <DIR> --out … --include … [--include …] --recipient … --purpose … --expires-at …
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cblib import VERSION  # noqa: E402
from cblib.common import patients_root, load_json, PATIENT_CODE_RE  # noqa: E402


def _out(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    sys.exit(code)


def cmd_patients(_):
    root = patients_root()
    rows = []
    if root.exists():
        for d in sorted(root.iterdir()):
            if d.is_dir() and PATIENT_CODE_RE.match(d.name):
                prof = load_json(d / "profile.json") or {}
                rows.append({"patient_dir": str(d), "alias": prof.get("alias"),
                             "one_line_condition": (prof.get("summary") or {}).get("one_line_condition"),
                             "updated": (load_json(d / "organize_meta.json") or {}).get("generated_at")})
    _out({"root": str(root), "patients": rows})


def cmd_organize(a):
    from cblib import organize
    if a.action == "prepare":
        from cblib.prepare import prepare
        _out(prepare(a.args, patient_dir=a.patient, locale=a.locale))
    if not a.args:
        _out({"error": "需要患者目录"}, 2)
    d = Path(a.args[0]).expanduser()
    if a.action == "next":
        _out(organize.next_step(d))
    if a.action == "place":
        _out(organize.place(d))
    if a.action == "finish":
        _out(organize.finish(d))
    if a.action == "check":
        from cblib.check import check
        _out(check(d))
    if a.action == "note":
        _out(organize.add_note(d, a.text, a.layer, a.bucket, a.date))
    if a.action == "move":
        _out(organize.move_sidecar(d, a.args[1], a.args[2]))
    if a.action == "discard":
        _out(organize.discard(d, a.args[1], a.confirm or ""))


def cmd_render(a):
    from cblib import render
    d = Path(a.patient_dir).expanduser()
    if a.what == "summary":
        _out({"html": str(render.render_case_summary(d, snapshot=True))})
    if a.what == "visit-prep":
        if not a.data:
            _out({"error": "需要 visit-prep 数据 JSON 路径"}, 2)
        _out({"html": str(render.render_visit_prep(d, Path(a.data)))})


def cmd_chart(a):
    from cblib import chart
    d = Path(a.patient_dir).expanduser()
    if a.list or not a.metric:
        _out({"chartable": chart.trend_candidates(d, limit=100)})
    try:
        _out({"html": str(chart.render_chart_page(d, a.metric, title=a.title))})
    except ValueError as e:
        _out({"error": str(e)}, 3)


def cmd_export(a):
    from cblib.export import export
    _out(export(a.patient_dir, a.out, a.include, a.recipient, a.purpose, a.expires_at, a.authorization_ref))


def main():
    ap = argparse.ArgumentParser(prog="cb.py", description=f"抗癌搭子 v{VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("patients").set_defaults(fn=cmd_patients)

    o = sub.add_parser("organize")
    o.add_argument("action", choices=["prepare", "next", "place", "finish", "check", "note", "move", "discard"])
    o.add_argument("args", nargs="*")
    o.add_argument("--patient")
    o.add_argument("--locale", default="zh")
    o.add_argument("--text")
    o.add_argument("--layer", default="patient_reported")
    o.add_argument("--bucket", default="14")
    o.add_argument("--date", default="")
    o.add_argument("--confirm")
    o.set_defaults(fn=cmd_organize)

    r = sub.add_parser("render")
    r.add_argument("what", choices=["summary", "visit-prep"])
    r.add_argument("patient_dir")
    r.add_argument("data", nargs="?")
    r.set_defaults(fn=cmd_render)

    c = sub.add_parser("chart")
    c.add_argument("patient_dir")
    c.add_argument("metric", nargs="?")
    c.add_argument("--title")
    c.add_argument("--list", action="store_true")
    c.set_defaults(fn=cmd_chart)

    e = sub.add_parser("export")
    e.add_argument("patient_dir")
    e.add_argument("--out", required=True)
    e.add_argument("--include", action="append", default=[])
    e.add_argument("--recipient", required=True)
    e.add_argument("--purpose", required=True)
    e.add_argument("--expires-at", dest="expires_at", required=True)
    e.add_argument("--authorization-ref", dest="authorization_ref", default="")
    e.set_defaults(fn=cmd_export)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
