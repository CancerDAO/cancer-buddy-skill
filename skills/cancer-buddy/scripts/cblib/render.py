"""Deterministic HTML pages rendered from the patient_dir JSON (SPEC §6). The model never writes HTML.

Every dynamic string goes through ``html.escape``. Pages are fully offline: no scripts, no external
stylesheets, fonts or images. Red is used only for values the report itself flagged critical.

Public API
----------
render_case_summary(patient_dir, snapshot=True) -> Path
    Writes <patient_dir>/病情简要总结.html and (snapshot=True) a copy at
    case_summary_versions/病情简要总结_YYYY-MM-DD[_n].html.

render_visit_prep(patient_dir, data_path) -> Path
    Writes <patient_dir>/就诊准备包.html from a visit-prep JSON file of this shape::

      {
        "schema": "cancer_buddy_visit_prep_v1",
        "visit_type": "first" | "followup" | "decision_discussion",
        "visit_date": "YYYY-MM-DD" | null,            # optional
        "department": "肿瘤内科" | null,               # optional
        "snapshot": [ {"text": "...", "source_refs": ["<sidecar>.md#Lx-Ly", ...]} ],   # 医生 30 秒速览
        "questions": [
          {"group": "请医生帮忙确认",
           "kind": "review_flag" | "records" | "next_step" | "general",   # review_flag -> soft yellow box
           "items": [ {"text": "...", "why": "...", "source_ref": "...", "flag_id": "RF-001"} ]}
        ],
        "bring_list": ["...", ...],
        "changes_since_last": [ "..." | {"text": "...", "source_ref": "..."} ]  # shown for followup /
                                                                              # decision_discussion
      }
    Strings may contain ``{?X|Y}`` uncertain-read markers; they render as 待核对（读作 X；另一读法 Y）.

Language: Chinese when profile.locale starts with "zh" (default), otherwise English. Clinical strings
are always shown verbatim from the JSON.
"""
import html
import re
from pathlib import Path

from .common import load_json, today
from . import chart

GENERATOR = "cancer-buddy v2 render"

# --- strings ---------------------------------------------------------------------------------
STRINGS = {
    "zh": {
        "title": "病情简要总结", "generated": "生成日期", "code": "档案编号", "alias": "称呼",
        "missing": "资料缺失", "unknown_date": "日期不详", "uncertain": "待核对（读作 {x}；另一读法 {y}）",
        "uncertain1": "待核对（读作 {x}）", "source": "出处",
        "stale": "本档案最新一份资料日期为 {date}，距今 {n} 天，之后如有新检查请补充。",
        "acute_h": "需要尽快告知治疗团队的发现",
        "acute_intro": "这是报告里写到的、需要尽快告知治疗团队的发现。下面是报告原文，不代表严重程度的判断。",
        "translated": "转述，非报告原句", "exam_date": "检查日期", "vs_prior": "报告写的与前片对比",
        "changes_h": "自上次以来的变化",
        "basic_h": "基本信息", "sex": "性别", "age": "年龄", "age_fmt": "{v} 岁", "height": "身高",
        "weight": "体重", "ps": "体能状态（原文）", "conditions": "其他疾病", "meds": "在用药物（记录）",
        "allergies": "过敏", "as_of": "{d} 记录",
        "dx_h": "诊断与分期", "primary": "原发部位", "histology": "病理类型", "stage": "分期（原文）",
        "diagnosed_at": "诊断日期", "basis": "诊断依据", "mets": "转移部位（报告写到）",
        "other_primary": "其他原发肿瘤", "icd10": "ICD-10",
        "narr_h": "病情概要", "self_reported_h": "家属或患者的口述（未经报告核实）",
        "trend_h": "趋势图", "trend_none": "目前没有至少两次可以比较的检验结果，暂不画趋势图。",
        "trend_note": "每张图只画原报告里的数，单位不同的不放在一起；数值的变化是观察，不等于疗效判断。",
        "mol_h": "分子检测", "mol_none": "档案中没有分子检测结果。", "gene": "基因", "variant": "变异",
        "vaf": "丰度（原文）", "cls": "报告分类（原文）", "report": "报告", "germline": "胚系变异",
        "biomarkers": "其他标志物（原文）", "sample": "样本",
        "labs_h": "近期检验", "labs_none": "档案中没有检验结果。", "item": "项目", "date": "日期",
        "result": "结果", "unit": "单位", "range": "参考范围（该次报告）", "flag": "报告标记",
        "misaligned": "表格对不齐，读数未核实", "labs_note": "每项列出最近 3 次；参考范围和标记照抄各次报告。",
        "tx_h": "治疗经过", "tx_none": "档案中没有治疗记录。", "regimen": "方案", "period": "起止",
        "cycles": "周期（原文）", "line": "线次（原文）", "status": "状态（依据）",
        "response": "医生记录的疗效（原文）", "reason": "换方案原因（原文）", "current": "当前方案",
        "ongoing": "进行中", "stopped": "已停止", "status_unknown": "状态不详",
        "review_h": "需要核对的地方", "review_none": "这次整理没有发现需要核对的字段。",
        "sev_red": "请先核对，暂不能当确定事实用", "sev_yellow": "需要核对", "sev_info": "提示",
        "gaps": "已知缺少的资料", "pages_missing": "缺第 {p} 页",
        "footer": "本页是资料索引，不替代主诊医生的判断。内容照抄自档案里的报告与病历，如与原件不符，以原件为准。",
        "vp_title": "就诊准备包", "vp_type": {"first": "首次就诊", "followup": "复诊",
                                            "decision_discussion": "治疗决策讨论"},
        "vp_snapshot": "医生 30 秒速览", "vp_questions": "想问医生的问题", "vp_bring": "要带的东西",
        "vp_changes": "上次以来的变化", "vp_why": "为什么问", "vp_none": "（无）",
        "vp_flag_note": "下面这些是档案里读不准或对不上的地方，请医生帮忙确认。",
        "vp_footer": "本页只整理资料和问题，不替代主诊医生的判断。",
        "prov": {"patient_reported": "患者自述", "caregiver_reported": "家属自述",
                 "prior_archive": "来自既往摘要，原件未在本次资料中", "system_normalized": "系统整理"},
        "status_basis": {"administration_record": "给药记录", "clinician_note_current": "医生当次记录",
                  "order_or_indication_only": "仅医嘱或检查申请指征", "patient_reported": "患者或家属自述",
                  "dates_only": "只有日期"},
        "sep": "；", "list_sep": "、", "lp": "（", "rp": "）", "colon": "：",
    },
    "en": {
        "title": "Case summary", "generated": "Generated", "code": "Record code", "alias": "Alias",
        "missing": "Not in records", "unknown_date": "date unknown",
        "uncertain": "To be checked (read as {x}; could also be {y})", "uncertain1": "To be checked (read as {x})",
        "source": "Source",
        "stale": "The newest document in this record is dated {date}, {n} days ago. Please add any newer tests or visits.",
        "acute_h": "Findings to tell the care team about soon",
        "acute_intro": "These are findings written in the reports that the care team should hear about soon. "
                       "The wording is the report's own; it is not a severity judgement.",
        "translated": "paraphrased, not the report's wording", "exam_date": "Exam date",
        "vs_prior": "Report's comparison with prior", "changes_h": "Changes since last summary",
        "basic_h": "Basic information", "sex": "Sex", "age": "Age", "age_fmt": "{v}", "height": "Height",
        "weight": "Weight", "ps": "Performance status (verbatim)", "conditions": "Other conditions",
        "meds": "Medications (recorded)", "allergies": "Allergies", "as_of": "as of {d}",
        "dx_h": "Diagnosis and stage", "primary": "Primary site", "histology": "Histology",
        "stage": "Stage (verbatim)", "diagnosed_at": "Diagnosed", "basis": "Basis",
        "mets": "Metastatic sites (as reported)", "other_primary": "Other primary cancers", "icd10": "ICD-10",
        "narr_h": "Overview", "self_reported_h": "Reported by family or patient (not verified by a report)",
        "trend_h": "Trends", "trend_none": "No test has two comparable results yet, so no trend chart is drawn.",
        "trend_note": "Charts show only numbers printed on the reports; different units are never mixed. "
                      "Changes are observations, not a judgement of treatment effect.",
        "mol_h": "Molecular testing", "mol_none": "No molecular results in the record.", "gene": "Gene",
        "variant": "Variant", "vaf": "VAF (verbatim)", "cls": "Report classification", "report": "Report",
        "germline": "Germline variants", "biomarkers": "Other markers (verbatim)", "sample": "Sample",
        "labs_h": "Recent lab results", "labs_none": "No lab results in the record.", "item": "Test",
        "date": "Date", "result": "Result", "unit": "Unit", "range": "Reference range (that report)",
        "flag": "Report flag", "misaligned": "table misaligned; reading unverified",
        "labs_note": "Up to the 3 most recent results per test; ranges and flags as printed on each report.",
        "tx_h": "Treatment history", "tx_none": "No treatment records in the file.", "regimen": "Regimen",
        "period": "Dates", "cycles": "Cycles (verbatim)", "line": "Line (verbatim)", "status": "Status (basis)",
        "response": "Response as written by clinician", "reason": "Reason for change (verbatim)",
        "current": "Current regimen", "ongoing": "ongoing", "stopped": "stopped", "status_unknown": "unknown",
        "review_h": "Items to check", "review_none": "No fields needed checking in this run.",
        "sev_red": "check first; not yet usable as fact", "sev_yellow": "to be checked", "sev_info": "note",
        "gaps": "Known missing documents", "pages_missing": "page(s) {p} missing",
        "footer": "This page is an index of the records and does not replace your treating doctor's judgement. "
                  "If anything differs from the original documents, the originals are authoritative.",
        "vp_title": "Visit preparation", "vp_type": {"first": "First visit", "followup": "Follow-up",
                                                     "decision_discussion": "Treatment decision discussion"},
        "vp_snapshot": "30-second overview for the doctor", "vp_questions": "Questions for the doctor",
        "vp_bring": "What to bring", "vp_changes": "Changes since last visit", "vp_why": "Why",
        "vp_none": "(none)",
        "vp_flag_note": "These are places in the record that could not be read clearly or do not match. "
                        "Please ask the doctor to confirm.",
        "vp_footer": "This page organises records and questions only; it does not replace your doctor's judgement.",
        "prov": {"patient_reported": "patient-reported", "caregiver_reported": "family-reported",
                 "prior_archive": "from a prior summary; original not in this record",
                 "system_normalized": "system-normalised"},
        "status_basis": {"administration_record": "administration record", "clinician_note_current": "clinician note",
                  "order_or_indication_only": "order/indication only", "patient_reported": "patient/family report",
                  "dates_only": "dates only"},
        "sep": "; ", "list_sep": ", ", "lp": " (", "rp": ")", "colon": ": ",
    },
}

UNCERTAIN_RE = re.compile(r"\{\?([^|{}]*)(?:\|([^{}]*))?\}")
FONT = chart.FONT


class _Ctx:
    def __init__(self, patient_dir):
        self.pd = Path(patient_dir)
        prof = self.j("profile.json")
        self.locale = str(prof.get("locale") or "zh")
        self.S = STRINGS["zh" if self.locale.lower().startswith("zh") else "en"]
        self.zh = self.locale.lower().startswith("zh")

    def j(self, name):
        d = load_json(self.pd / name, {})
        return d if isinstance(d, dict) else {}

    def t(self, key, **kw):
        s = self.S[key]
        return s.format(**kw) if kw else s


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _txt(ctx, s) -> str:
    """Escape, then turn {?X|Y} markers into 待核对 prose (X, Y already escaped)."""
    esc = _e(s)

    def sub(m):
        x, y = m.group(1), m.group(2)
        body = ctx.t("uncertain", x=x, y=y) if y else ctx.t("uncertain1", x=x)
        return f'<span class="unc">{body}</span>'
    return UNCERTAIN_RE.sub(sub, esc)


def _missing(ctx) -> str:
    return f'<span class="miss">{_e(ctx.t("missing"))}</span>'


def _scalar(v):
    if isinstance(v, dict):
        for k in ("text", "name", "site", "primary", "value", "result_verbatim", "label"):
            if v.get(k) not in (None, ""):
                return v[k]
        return None
    return v


def _val(ctx, v) -> str:
    """Display value: None/'' -> 资料缺失; list -> joined; dict -> best text key."""
    if isinstance(v, list):
        parts = [_val(ctx, x) for x in v if _scalar(x) not in (None, "")]
        return _e(ctx.t("list_sep")).join(parts) if parts else _missing(ctx)
    v = _scalar(v)
    if v is None or (isinstance(v, str) and not v.strip()):
        return _missing(ctx)
    return _txt(ctx, v)


def _refs(row):
    if not isinstance(row, dict):
        return []
    r = row.get("source_refs")
    if isinstance(r, list):
        return [x for x in r if isinstance(x, str) and x]
    if isinstance(row.get("source_ref"), str) and row["source_ref"]:
        return [row["source_ref"]]
    return []


def _src(ctx, refs) -> str:
    if isinstance(refs, str):
        refs = [refs]
    labels = []
    for r in refs or []:
        lab = chart.source_label(ctx.pd, r)
        if lab and lab not in labels:
            labels.append(lab)
    if not labels:
        return ""
    return (f'<span class="src">{_e(ctx.t("source"))}{_e(ctx.t("colon"))}'
            f'{_e(ctx.t("list_sep").join(labels))}</span>')


def _prov(ctx, layer) -> str:
    lab = ctx.S["prov"].get(str(layer or ""))
    if not lab or layer == "system_normalized":
        return ""
    return f'<span class="prov">{_e(lab)}</span>'


def _with_date(ctx, v, as_of, fmt=None) -> str:
    if v in (None, ""):
        return _missing(ctx)
    shown = _txt(ctx, fmt.format(v=v) if fmt else v)
    d = ctx.t("as_of", d=as_of) if as_of else ctx.t("unknown_date")
    return f'{shown}<span class="asof">{_e(ctx.t("lp") + d + ctx.t("rp"))}</span>'


def _section(ctx, key, body, cls="") -> str:
    return f'<section class="{cls}"><h2>{_e(ctx.t(key))}</h2>\n{body}\n</section>'


def _table(head, rows, cls="") -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def _identity_values(pd):
    from .check import load_identity
    vals = {v for vs in load_identity(pd).values() for v in vs}
    return sorted(vals, key=len, reverse=True)


def _mask(pd, text) -> str:
    """Last line of defence: identity strings never reach a rendered page."""
    from .check import _identity_re
    for v in _identity_values(pd):
        for form in {v, _e(v)}:
            text = _identity_re(form).sub("[已遮蔽]", text)
    return text


# --- CSS --------------------------------------------------------------------------------------
CSS = """
@page { size: A4; margin: 12mm 14mm; }
* { box-sizing: border-box; }
body { font-family: %(font)s; color: #2d2640; background: #fff; margin: 0 auto; max-width: 820px;
       padding: 16px; font-size: 14px; line-height: 1.65; }
h1 { font-size: 22px; margin: 0 0 2px; }
h2 { font-size: 16.5px; margin: 20px 0 8px; padding-bottom: 3px; border-bottom: 2px solid #e4e1ea; }
h3 { font-size: 14.5px; margin: 12px 0 4px; }
.meta { color: #6f6a7d; font-size: 13px; }
.oneline { margin: 6px 0 0; font-weight: 600; }
.banner { background: #f3effa; border-left: 4px solid #8e7cc3; padding: 8px 12px; margin: 12px 0; border-radius: 4px; }
.acute { background: #fff6e0; border: 1px solid #e8c878; border-radius: 6px; padding: 4px 14px 10px; }
.acute h2 { border-bottom-color: #e8c878; }
.acute li { margin: 6px 0; }
.quote { font-weight: 600; }
.flagbox { background: #fffbe8; border: 1px solid #efe0a6; border-radius: 6px; padding: 8px 14px; margin: 8px 0; }
.sev { display: inline-block; font-size: 12px; padding: 0 6px; border-radius: 3px; background: #f1e6b8; color: #5a4a12; margin-right: 6px; }
.sev.info { background: #ece9f2; color: #4a4458; }
.miss { color: #8a8595; font-style: italic; }
.unc { background: #fff3c4; border-radius: 3px; padding: 0 3px; }
.asof { color: #6f6a7d; font-size: 12.5px; }
.src { display: block; color: #6f6a7d; font-size: 12px; }
td .src { display: inline; margin-left: 4px; }
.prov { display: inline-block; font-size: 12px; padding: 0 6px; border-radius: 3px; background: #e9f0f7; color: #2f4a66; margin-left: 4px; }
.crit { color: #c0392b; font-weight: 700; }
.tw { overflow-x: auto; }
table { border-collapse: collapse; width: 100%%; font-size: 13px; }
th, td { border-bottom: 1px solid #e4e1ea; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #f6f4f9; font-weight: 600; white-space: nowrap; }
table.kv th { width: 9em; white-space: normal; }
table:not(.kv) td:nth-child(2) { white-space: nowrap; }
figure { margin: 8px 0 14px; page-break-inside: avoid; break-inside: avoid; }
figcaption { font-size: 13px; color: #4a4458; margin-bottom: 2px; }
.note { color: #6f6a7d; font-size: 12.5px; }
ul { padding-left: 1.3em; margin: 4px 0; }
footer { margin-top: 24px; padding-top: 8px; border-top: 1px solid #e4e1ea; color: #6f6a7d; font-size: 12.5px; }
section { page-break-inside: auto; }
@media (max-width: 600px) { body { padding: 12px; font-size: 15px; } table { font-size: 13px; } h1 { font-size: 20px; } }
@media print { body { max-width: none; padding: 0; font-size: 10pt; } h2 { font-size: 12.5pt; }
  table { font-size: 9.5pt; } .src, .asof, .note, .meta, footer { font-size: 9pt; }
  .acute, .flagbox, .banner { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
""" % {"font": FONT}


def _page(ctx, title, body) -> str:
    return (f'<!DOCTYPE html>\n<html lang="{"zh-CN" if ctx.zh else "en"}"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="generator" content="{GENERATOR}">\n<title>{_e(title)}</title>\n'
            f"<style>{CSS}</style></head><body>\n{body}\n</body></html>\n")


# --- case summary sections ------------------------------------------------------------------

def _header(ctx, prof) -> str:
    summ = prof.get("summary") if isinstance(prof.get("summary"), dict) else {}
    bits = []
    if prof.get("patient_code"):
        bits.append(f'{_e(ctx.t("code"))}{_e(ctx.t("colon"))}{_e(prof["patient_code"])}')
    if prof.get("alias"):
        bits.append(f'{_e(ctx.t("alias"))}{_e(ctx.t("colon"))}{_e(prof["alias"])}')
    bits.append(f'{_e(ctx.t("generated"))}{_e(ctx.t("colon"))}{_e(today())}')
    one = summ.get("one_line_condition")
    out = f'<header><h1>{_e(ctx.t("title"))}</h1><div class="meta">{"　".join(bits)}</div>'
    if one:
        out += f'<p class="oneline">{_txt(ctx, one)}</p>'
    return out + "</header>"


def _stale(ctx, readiness) -> str:
    n = readiness.get("days_since_latest")
    if isinstance(n, (int, float)) and not isinstance(n, bool) and n > 14:
        return f'<div class="banner">{_e(ctx.t("stale", date=readiness.get("latest_source_date") or ctx.t("unknown_date"), n=int(n)))}</div>'
    return ""


def _acute(ctx, af) -> str:
    items = [f for f in af.get("findings") or [] if isinstance(f, dict)]
    if not items:
        return ""
    lis = []
    for f in items:
        label = f'<b>{_txt(ctx, f.get("label"))}</b>' if f.get("label") else ""
        quote = f'<span class="quote">“{_txt(ctx, f.get("verbatim_text"))}”</span>' if f.get("verbatim_text") else _missing(ctx)
        tr = f'<span class="note">{_e(ctx.t("lp") + ctx.t("translated") + ctx.t("rp"))}</span>' if f.get("verbatim_is_translation") else ""
        d = f.get("exam_date") or f.get("report_date")
        date = f'<span class="asof">{_e(ctx.t("exam_date"))}{_e(ctx.t("colon"))}{_e(d or ctx.t("unknown_date"))}</span>'
        cvp = f.get("change_vs_prior") if isinstance(f.get("change_vs_prior"), dict) else {}
        prior = (f'<span class="note">　{_e(ctx.t("vs_prior"))}{_e(ctx.t("colon"))}“{_txt(ctx, cvp["verbatim"])}”</span>'
                 if cvp.get("verbatim") else "")
        lis.append(f"<li>{label}{_e(ctx.t('colon')) if label else ''}{quote}{tr}　{date}{prior}{_src(ctx, _refs(f))}</li>")
    return (f'<section class="acute"><h2>{_e(ctx.t("acute_h"))}</h2><p>{_e(ctx.t("acute_intro"))}</p>'
            f'<ul>{"".join(lis)}</ul></section>')


def _changes(ctx, narr) -> str:
    ch = narr.get("changes_since_last")
    if not isinstance(ch, list) or not ch:
        return ""
    lis = []
    for c in ch:
        if isinstance(c, dict):
            lis.append(f"<li>{_val(ctx, c.get('text'))}{_src(ctx, _refs(c))}</li>")
        elif c not in (None, ""):
            lis.append(f"<li>{_txt(ctx, c)}</li>")
    return _section(ctx, "changes_h", f"<ul>{''.join(lis)}</ul>") if lis else ""


def _basic(ctx, prof, ps, com) -> str:
    d = ps.get("demographics") if isinstance(ps.get("demographics"), dict) else {}
    pd_ = prof.get("demographics") if isinstance(prof.get("demographics"), dict) else {}
    an = prof.get("anthropometrics") if isinstance(prof.get("anthropometrics"), dict) else {}

    def g(key, *alts):
        for src in (d, pd_, an):
            for k in (key,) + alts:
                if src.get(k) not in (None, ""):
                    return src[k]
        return None
    rows = []
    rows.append((ctx.t("sex"), _val(ctx, g("sex"))))
    rows.append((ctx.t("age"), _with_date(ctx, g("age"), g("age_as_of"), ctx.t("age_fmt"))))
    h = g("height_cm")
    rows.append((ctx.t("height"), _with_date(ctx, f"{h} cm" if h not in (None, "") else None,
                                             g("height_as_of") or (an.get("as_of") if an.get("height_cm") == h else None))))
    w = g("weight_kg")
    rows.append((ctx.t("weight"), _with_date(ctx, f"{w} kg" if w not in (None, "") else None,
                                             g("weight_as_of", "as_of"))))
    psv = g("performance_status_verbatim")
    if isinstance(psv, list) and psv:
        rows.append((ctx.t("ps"), "<br>".join(_with_date(ctx, _scalar(p), p.get("as_of") if isinstance(p, dict) else None)
                                               + _src(ctx, _refs(p) if isinstance(p, dict) else []) for p in psv)))
    elif g("ecog"):
        rows.append((ctx.t("ps"), _with_date(ctx, g("ecog"), g("ecog_as_of"))))
    else:
        rows.append((ctx.t("ps"), _missing(ctx)))
    conds = [c for c in com.get("conditions") or [] if isinstance(c, dict)]
    if conds:
        rows.append((ctx.t("conditions"), "<br>".join(
            _val(ctx, c.get("name")) + _prov(ctx, c.get("provenance_layer")) + _src(ctx, _refs(c)) for c in conds)))
    meds = [m for m in com.get("medications") or [] if isinstance(m, dict)]
    if meds:
        def med(m):
            extra = " ".join(str(m[k]) for k in ("dose", "frequency", "route") if m.get(k))
            s = _val(ctx, m.get("name")) + (" " + _txt(ctx, extra) if extra else "")
            if m.get("as_of"):
                s += f'<span class="asof">{_e(ctx.t("lp") + ctx.t("as_of", d=m["as_of"]) + ctx.t("rp"))}</span>'
            return s + _prov(ctx, m.get("provenance_layer")) + _src(ctx, _refs(m))
        rows.append((ctx.t("meds"), "<br>".join(med(m) for m in meds)))
    alls = [a for a in com.get("allergies") or [] if isinstance(a, dict)]
    if alls:
        rows.append((ctx.t("allergies"), "<br>".join(
            _val(ctx, a.get("allergen") or a.get("certainty_source")) + (" " + _txt(ctx, a["reaction"]) if a.get("reaction") else "")
            + _src(ctx, _refs(a)) for a in alls)))
    return _section(ctx, "basic_h", _kv(rows))


def _kv(rows) -> str:
    return '<div class="tw"><table class="kv"><tbody>' + "".join(
        f"<tr><th>{_e(k)}</th><td>{v}</td></tr>" for k, v in rows) + "</tbody></table></div>"


def _dx(ctx, prof, ps) -> str:
    dx = ps.get("diagnosis") if isinstance(ps.get("diagnosis"), dict) else {}
    summ = prof.get("summary") if isinstance(prof.get("summary"), dict) else {}

    def g(k):
        return dx.get(k) if dx.get(k) not in (None, "", []) else summ.get(k)
    stage_refs = [r for r in _refs(dx) if r] or _refs(summ)
    rows = [(ctx.t("primary"), _val(ctx, g("primary"))),
            (ctx.t("histology"), _val(ctx, g("histology"))),
            (ctx.t("stage"), _val(ctx, g("stage")) + (_src(ctx, stage_refs) if g("stage") else "")),
            (ctx.t("diagnosed_at"), _val(ctx, g("diagnosed_at"))),
            (ctx.t("basis"), _val(ctx, g("diagnosis_basis")))]
    if g("icd10"):
        rows.append((ctx.t("icd10"), _val(ctx, g("icd10"))))
    mets = g("metastasis_sites")
    rows.append((ctx.t("mets"), _val(ctx, mets) + (_src(ctx, dx.get("metastasis_source_refs") or []) if mets else "")))
    ap = [a for a in dx.get("additional_primaries") or [] if a]
    if ap:
        def one(a):
            if not isinstance(a, dict):
                return _val(ctx, a)
            s = _val(ctx, a.get("primary") or a.get("name"))
            extra = [str(a[k]) for k in ("diagnosed_at", "detail") if a.get(k)]
            if extra:
                s += _e(ctx.t("lp")) + _txt(ctx, ctx.t("sep").join(extra)) + _e(ctx.t("rp"))
            return s + _prov(ctx, a.get("provenance_layer")) + _src(ctx, _refs(a))
        rows.append((ctx.t("other_primary"), "<br>".join(one(a) for a in ap)))
    return _section(ctx, "dx_h", _kv(rows))


def _narrative(ctx, narr, prof, tl) -> str:
    text = narr.get("narrative")
    if not text:
        summ = prof.get("summary") if isinstance(prof.get("summary"), dict) else {}
        text = summ.get("one_line_condition")
    body = "".join(f"<p>{_txt(ctx, p)}</p>" for p in str(text).split("\n") if p.strip()) if text else f"<p>{_missing(ctx)}</p>"
    selfrep = [e for e in tl.get("events") or [] if isinstance(e, dict)
               and e.get("provenance_layer") in ("patient_reported", "caregiver_reported")]
    if selfrep:
        lis = []
        for e in selfrep:
            d = e.get("date") or ctx.t("unknown_date")
            lis.append(f"<li>{_prov(ctx, e.get('provenance_layer'))} {_txt(ctx, e.get('title') or '')}"
                       f'<span class="asof">{_e(ctx.t("lp") + str(d) + ctx.t("rp"))}</span>{_src(ctx, _refs(e))}</li>')
        body += f'<h3>{_e(ctx.t("self_reported_h"))}</h3><ul>{"".join(lis)}</ul>'
    return _section(ctx, "narr_h", body)


def _trends(ctx) -> str:
    figs = []
    for m in chart.trend_candidates(ctx.pd, limit=4):
        s = chart.series_for(ctx.pd, m)
        if not s or len(s["points"]) < 2:
            continue
        title = chart.default_title(s, ctx.locale)
        notes = []
        for ch in s["method_changes"]:
            notes.append(f"{ch['date']} 起检测方法变为“{ch['to'] or '未写明'}”，线在此断开" if ctx.zh
                         else f"method changed on {ch['date']}; line broken")
        n_unit = sum(1 for x in s["excluded"] if x["reason"] == "unit")
        if n_unit:
            notes.append(f"另有 {n_unit} 次单位不同，未画入" if ctx.zh else f"{n_unit} result(s) in other units not plotted")
        n_unv = sum(1 for x in s["excluded"] if x["reason"] == "unverified_read")
        if n_unv:
            notes.append(f"另有 {n_unv} 次读数未核实，未画入" if ctx.zh else f"{n_unv} unverified reading(s) not plotted")
        note = f'<div class="note">{_e(ctx.t("sep").join(notes))}</div>' if notes else ""
        figs.append(f"<figure><figcaption>{_e(title)}</figcaption>{chart.svg_trend(s, title=title, locale=ctx.locale)}{note}</figure>")
    if not figs:
        return _section(ctx, "trend_h", f'<p class="note">{_e(ctx.t("trend_none"))}</p>')
    return _section(ctx, "trend_h", f'<p class="note">{_e(ctx.t("trend_note"))}</p>' + "".join(figs))


def _molecular(ctx, mol) -> str:
    reports = {r.get("report_id"): r for r in mol.get("reports") or [] if isinstance(r, dict)}
    body = ""
    variants = [v for v in mol.get("variants") or [] if isinstance(v, dict)]
    if variants:
        rows = []
        for v in variants:
            rep = reports.get(v.get("report_id")) or {}
            rows.append([_val(ctx, v.get("gene")), _val(ctx, v.get("variant")), _val(ctx, v.get("vaf_raw")),
                         _val(ctx, v.get("classification_source")),
                         _val(ctx, rep.get("report_date") or v.get("report_id")) + _src(ctx, _refs(v))])
        body += _table([_e(ctx.t(k)) for k in ("gene", "variant", "vaf", "cls", "report")], rows)
    germ = [v for v in mol.get("germline") or [] if isinstance(v, dict)]
    if germ:
        rows = [[_val(ctx, v.get("gene")), _val(ctx, v.get("variant")),
                 _val(ctx, v.get("zygosity") or v.get("vaf_raw")), _val(ctx, v.get("classification_source")),
                 _val(ctx, (reports.get(v.get("report_id")) or {}).get("report_date") or v.get("report_id")) + _src(ctx, _refs(v))]
                for v in germ]
        body += f'<h3>{_e(ctx.t("germline"))}</h3>' + _table(
            [_e(ctx.t("gene")), _e(ctx.t("variant")), _e("合子型" if ctx.zh else "Zygosity"), _e(ctx.t("cls")), _e(ctx.t("report"))], rows)
    marks = []
    for key, lab in (("msi_results", "MSI"), ("tmb_results", "TMB"), ("mmr_results", "MMR"), ("ihc", "IHC"),
                     ("pharmacogenomics", "PGx"), ("hla_typing", "HLA")):
        for r in mol.get(key) or []:
            if isinstance(r, dict):
                if key == "hla_typing":
                    v = " ".join(str(r[k]) for k in ("locus", "allele", "zygosity") if r.get(k))
                else:
                    v = r.get("result_verbatim") or r.get("result") or _scalar(r)
                name = r.get("marker") or lab
            else:
                v, name = r, lab
            if v not in (None, ""):
                lead = "" if str(v).startswith(str(name)) else f"<b>{_e(name)}</b>{_e(ctx.t('colon'))}"
                marks.append(f"<li>{lead}{_txt(ctx, v)}{_src(ctx, _refs(r))}</li>")
    if marks:
        body += f'<h3>{_e(ctx.t("biomarkers"))}</h3><ul>{"".join(marks)}</ul>'
    rep_lines = []
    for r in reports.values():
        parts = [str(r[k]) for k in ("report_date", "assay", "sample_type", "tumor_purity") if r.get(k)]
        if parts:
            rep_lines.append(f"<li>{_txt(ctx, ctx.t('sep').join(parts))}{_src(ctx, _refs(r))}</li>")
    if rep_lines:
        body += f'<h3>{_e(ctx.t("report"))}</h3><ul>{"".join(rep_lines)}</ul>'
    if not body:
        body = f'<p>{_missing(ctx)}<span class="note">　{_e(ctx.t("mol_none"))}</span></p>'
    return _section(ctx, "mol_h", body)


def _date_key(d):
    return str(d or "")


def _labs(ctx, labs) -> str:
    panels = [p for p in labs.get("panels") or [] if isinstance(p, dict)]
    rows = []
    for p in panels:
        vals = sorted([v for v in p.get("values") or [] if isinstance(v, dict)],
                      key=lambda v: _date_key(v.get("date")), reverse=True)[:3]
        name = p.get("analyte") or p.get("normalized_analyte")
        if p.get("normalized_analyte") and p["normalized_analyte"] not in name:
            name = f"{name} {p['normalized_analyte']}"
        for i, v in enumerate(vals):
            if v.get("value") is None:
                res = _missing(ctx)
                if v.get("candidate_value") is not None:
                    res += f'<span class="note">{_e(ctx.t("lp") + ctx.t("misaligned") + ctx.t("rp"))}</span>'
            else:
                shown = v.get("raw_value") if v.get("raw_value") not in (None, "") else v.get("value")
                res = _txt(ctx, shown)
                if v.get("critical_flag"):
                    res = f'<span class="crit">{res}</span>'
            flag = _txt(ctx, v.get("report_flag")) if v.get("report_flag") else ""
            if v.get("critical_flag") and flag:
                flag = f'<span class="crit">{flag}</span>'
            rows.append([_txt(ctx, name) if i == 0 else "", _val(ctx, v.get("date")), res + _prov(ctx, v.get("provenance_layer")),
                         _txt(ctx, v.get("unit") or ""), _txt(ctx, v.get("reference_range") or ""), flag,
                         _src(ctx, _refs(v))])
    if not rows:
        return _section(ctx, "labs_h", f'<p>{_missing(ctx)}<span class="note">　{_e(ctx.t("labs_none"))}</span></p>')
    head = [_e(ctx.t(k)) for k in ("item", "date", "result", "unit", "range", "flag", "source")]
    return _section(ctx, "labs_h", f'<p class="note">{_e(ctx.t("labs_note"))}</p>' + _table(head, rows))


def _treatment(ctx, prof, ps, tx) -> str:
    eps = [e for e in tx.get("episodes") or [] if isinstance(e, dict)]
    latest = prof.get("latest_status") if isinstance(prof.get("latest_status"), dict) else {}
    cur = ps.get("current_status") if isinstance(ps.get("current_status"), dict) else {}
    ongoing = [e for e in eps if e.get("status") == "ongoing"]
    regimen = latest.get("regimen") or cur.get("regimen") or (ongoing[-1].get("regimen") if ongoing else None)
    body = ""
    if regimen:
        basis = latest.get("status_basis") or (ongoing[-1].get("status_basis") if ongoing else None)
        as_of = latest.get("as_of") or cur.get("as_of") or (ongoing[-1].get("status_as_of") if ongoing else None)
        extra = [ctx.S["status_basis"].get(basis, basis)] if basis else []
        if as_of:
            extra.append(ctx.t("as_of", d=as_of))
        refs = _refs(latest) or _refs(cur) or (_refs(ongoing[-1]) if ongoing else [])
        prov = _prov(ctx, ongoing[-1].get("provenance_layer")) if ongoing else ""
        body += (f'<p><b>{_e(ctx.t("current"))}{_e(ctx.t("colon"))}</b>{_txt(ctx, regimen)}{prov}'
                 + (f'<span class="asof">{_e(ctx.t("lp") + ctx.t("sep").join(extra) + ctx.t("rp"))}</span>' if extra else "")
                 + _src(ctx, refs) + "</p>")
    if eps:
        body += chart.svg_treatment_timeline(eps, locale=ctx.locale)
        rows = []
        status_word = {"ongoing": ctx.t("ongoing"), "stopped": ctx.t("stopped")}
        for e in eps:
            period = f"{e.get('started_at') or '?'} – {e.get('ended_at') or ('' if e.get('status') == 'ongoing' else '?')}"
            st = status_word.get(e.get("status"), ctx.t("status_unknown"))
            if e.get("status_basis"):
                st += ctx.t("lp") + ctx.S["status_basis"].get(e["status_basis"], e["status_basis"]) + ctx.t("rp")
            resp = e.get("clinician_reported_response")
            rows.append([_val(ctx, e.get("regimen")) + _prov(ctx, e.get("provenance_layer")) + _src(ctx, _refs(e)),
                         _txt(ctx, period), _txt(ctx, e.get("cycle_label_verbatim") or ""),
                         _txt(ctx, e.get("documented_line_label") or e.get("phase_or_intent_source") or ""),
                         _txt(ctx, st), _txt(ctx, resp) if resp else "",
                         _txt(ctx, e.get("reason_for_change_source") or "")])
        body += _table([_e(ctx.t(k)) for k in ("regimen", "period", "cycles", "line", "status", "response", "reason")], rows)
    if not body:
        body = f'<p>{_missing(ctx)}<span class="note">　{_e(ctx.t("tx_none"))}</span></p>'
    return _section(ctx, "tx_h", body)


def _review(ctx, readiness, mi) -> str:
    body = ""
    flags = [f for f in readiness.get("review_flags") or [] if isinstance(f, dict)
             and f.get("resolution_status") in (None, "", "unresolved")]
    order = {"red": 0, "yellow": 1, "info": 2}
    flags.sort(key=lambda f: order.get(f.get("severity"), 3))
    for f in flags:
        sev = f.get("severity") or "info"
        lab = ctx.t({"red": "sev_red", "yellow": "sev_yellow"}.get(sev, "sev_info"))
        vals = [v for v in f.get("values") or f.get("current_source_values") or [] if isinstance(v, dict)]
        vtxt = ctx.t("list_sep").join(str(v.get("value")) for v in vals if v.get("value") not in (None, ""))
        refs = [v.get("source_ref") for v in vals if v.get("source_ref")]
        body += (f'<div class="flagbox"><span class="sev{" info" if sev == "info" else ""}">{_e(lab)}</span>'
                 f'{_val(ctx, f.get("issue") or f.get("affected_field"))}'
                 + (f'<span class="note">{_e(ctx.t("lp"))}{_txt(ctx, vtxt)}{_e(ctx.t("rp"))}</span>' if vtxt else "")
                 + _src(ctx, refs) + "</div>")
    gaps = [g for g in mi.get("document_gaps") or [] if isinstance(g, dict)]
    if gaps:
        lis = []
        for g in gaps:
            s = _val(ctx, g.get("document_category"))
            if g.get("pages_missing"):
                s += _e(ctx.t("lp") + ctx.t("pages_missing", p=g["pages_missing"]) + ctx.t("rp"))
            if g.get("reason_for_artifact"):
                s += _e(ctx.t("colon")) + _txt(ctx, g["reason_for_artifact"])
            lis.append(f"<li>{s}{_src(ctx, _refs(g))}</li>")
        body += f'<h3>{_e(ctx.t("gaps"))}</h3><ul>{"".join(lis)}</ul>'
        if mi.get("disclaimer"):
            body += f'<p class="note">{_txt(ctx, mi["disclaimer"])}</p>'
    warns = [w for w in readiness.get("warnings") or [] if isinstance(w, str)
             and not w.startswith("本档案最新一份资料") and not w.startswith("The newest document")]
    if warns:
        body += "<ul>" + "".join(f"<li>{_txt(ctx, w)}</li>" for w in warns) + "</ul>"
    if not body:
        body = f'<p class="note">{_e(ctx.t("review_none"))}</p>'
    return _section(ctx, "review_h", body)


def _snapshot(pd, text) -> Path:
    vdir = pd / "case_summary_versions"
    vdir.mkdir(parents=True, exist_ok=True)
    existing = sorted(vdir.glob("病情简要总结_*.html"), key=lambda q: q.stat().st_mtime)
    if existing and existing[-1].read_text(encoding="utf-8") == text:
        return existing[-1]                           # nothing changed since the last snapshot
    base = f"病情简要总结_{today()}"
    p = vdir / f"{base}.html"
    n = 2
    while p.exists():
        p = vdir / f"{base}_{n}.html"
        n += 1
    p.write_text(text, encoding="utf-8")
    return p


def render_case_summary(patient_dir, snapshot=True) -> Path:
    """Render <patient_dir>/病情简要总结.html (SPEC §6) and optionally snapshot it."""
    ctx = _Ctx(patient_dir)
    pd = ctx.pd
    prof, ps = ctx.j("profile.json"), ctx.j("patient_summary.json")
    readiness = ctx.j("readiness.json")
    narr = load_json(pd / ".work" / "summary_narrative.json", {})
    narr = narr if isinstance(narr, dict) else {}
    parts = [
        _header(ctx, prof),
        _stale(ctx, readiness),
        _acute(ctx, ctx.j("acute_findings.json")),
        _changes(ctx, narr),
        _basic(ctx, prof, ps, ctx.j("comorbidities.json")),
        _dx(ctx, prof, ps),
        _narrative(ctx, narr, prof, ctx.j("timeline.json")),
        _trends(ctx),
        _molecular(ctx, ctx.j("molecular.json")),
        _labs(ctx, ctx.j("labs.json")),
        _treatment(ctx, prof, ps, ctx.j("treatment_lines.json")),
        _review(ctx, readiness, ctx.j("missing_items.json")),
        f'<footer>{_e(ctx.t("footer"))}<br>{_e(ctx.t("generated"))} {_e(today())} · {_e(GENERATOR)}</footer>',
    ]
    text = _mask(pd, _page(ctx, ctx.t("title"), "\n".join(p for p in parts if p)))
    out = pd / "病情简要总结.html"
    out.write_text(text, encoding="utf-8")
    if snapshot:
        _snapshot(pd, text)
    return out


# --- visit prep ------------------------------------------------------------------------------

def render_visit_prep(patient_dir, data_path) -> Path:
    """Render <patient_dir>/就诊准备包.html from the visit-prep JSON (shape in module docstring)."""
    ctx = _Ctx(patient_dir)
    pd = ctx.pd
    data = load_json(Path(data_path), {})
    data = data if isinstance(data, dict) else {}
    prof = ctx.j("profile.json")
    vt = data.get("visit_type") if data.get("visit_type") in ("first", "followup", "decision_discussion") else "followup"
    head_bits = [ctx.S["vp_type"][vt]]
    for k in ("visit_date", "department"):
        if data.get(k):
            head_bits.append(str(data[k]))
    if prof.get("patient_code"):
        head_bits.append(f'{ctx.t("code")}{ctx.t("colon")}{prof["patient_code"]}')
    parts = [f'<header><h1>{_e(ctx.t("vp_title"))}</h1><div class="meta">{_e("　".join(head_bits))}'
             f'　{_e(ctx.t("generated"))}{_e(ctx.t("colon"))}{_e(today())}</div></header>']

    snap = data.get("snapshot") or []
    lis = []
    for s in snap:
        if isinstance(s, dict):
            lis.append(f"<li>{_val(ctx, s.get('text'))}{_src(ctx, _refs(s))}</li>")
        elif s not in (None, ""):
            lis.append(f"<li>{_txt(ctx, s)}</li>")
    parts.append(_section(ctx, "vp_snapshot", f"<ul>{''.join(lis)}</ul>" if lis else f"<p>{_missing(ctx)}</p>"))

    qhtml = ""
    for g in data.get("questions") or []:
        if not isinstance(g, dict):
            continue
        items = []
        for it in g.get("items") or []:
            if isinstance(it, str):
                it = {"text": it}
            if not isinstance(it, dict) or not it.get("text"):
                continue
            why = (f'<span class="note">　{_e(ctx.t("vp_why"))}{_e(ctx.t("colon"))}{_txt(ctx, it["why"])}</span>'
                   if it.get("why") else "")
            items.append(f"<li>{_txt(ctx, it['text'])}{why}{_src(ctx, _refs(it))}</li>")
        if not items:
            continue
        inner = f'<h3>{_txt(ctx, g.get("group") or "")}</h3>'
        if g.get("kind") == "review_flag":
            qhtml += (f'<div class="flagbox">{inner}<p class="note">{_e(ctx.t("vp_flag_note"))}</p>'
                      f'<ol>{"".join(items)}</ol></div>')
        else:
            qhtml += f'{inner}<ol>{"".join(items)}</ol>'
    parts.append(_section(ctx, "vp_questions", qhtml or f"<p>{_e(ctx.t('vp_none'))}</p>"))

    bring = [b for b in data.get("bring_list") or [] if b not in (None, "")]
    parts.append(_section(ctx, "vp_bring", "<ul>" + "".join(
        f"<li>☐ {_val(ctx, b)}</li>" for b in bring) + "</ul>" if bring else f"<p>{_e(ctx.t('vp_none'))}</p>"))

    ch = data.get("changes_since_last") or []
    if vt != "first" or ch:
        lis = []
        for c in ch:
            if isinstance(c, dict):
                lis.append(f"<li>{_val(ctx, c.get('text'))}{_src(ctx, _refs(c))}</li>")
            elif c not in (None, ""):
                lis.append(f"<li>{_txt(ctx, c)}</li>")
        parts.append(_section(ctx, "vp_changes", f"<ul>{''.join(lis)}</ul>" if lis else f"<p>{_e(ctx.t('vp_none'))}</p>"))
    parts.append(f'<footer>{_e(ctx.t("vp_footer"))}<br>{_e(ctx.t("generated"))} {_e(today())} · {_e(GENERATOR)}</footer>')
    text = _mask(pd, _page(ctx, ctx.t("vp_title"), "\n".join(parts)))
    out = pd / "就诊准备包.html"
    out.write_text(text, encoding="utf-8")
    return out


__all__ = ["render_case_summary", "render_visit_prep", "STRINGS", "GENERATOR"]
