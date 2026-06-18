#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cancer Buddy Report Template v2
用法: python report_template.py <report_data.json> <output.docx> [--type brief|detailed]
"""

import sys
import json
import argparse
from datetime import datetime
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ── Design tokens ──────────────────────────────────────────────────────────────
PRIMARY   = RGBColor(0x1F, 0x3B, 0x5C)
ACCENT    = RGBColor(0x2E, 0x75, 0xB6)
ALERT_T   = RGBColor(0xC0, 0x00, 0x00)
WARN_T    = RGBColor(0xAD, 0x57, 0x00)
OK_T      = RGBColor(0x1B, 0x5E, 0x20)

HDR_BG   = "D6E4F0"
ALERT_BG = "FCE8E8"
WARN_BG  = "FFF3E0"

FONT_CN = "Microsoft YaHei"
FONT_EN = "Arial"

# A4 版心：2.5cm 边距 → 16cm = 9072 DXA
CONTENT_DXA = 9072

# 治疗线配色（左边框）
LINE_ACCENT_HEX = ["1A6EA8", "C0600A", "1A6E1A", "6A1A8A"]
LINE_BG_HEX     = ["EBF4FB", "FEF3E8", "EBF5EB", "F5EBF9"]


# ── Low-level helpers ──────────────────────────────────────────────────────────
def _set_font(run, size_pt, bold=False, italic=False, color=None):
    run.font.name = FONT_EN
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), FONT_CN)


def _shading(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _borders(cell, color="D0D7DE", size=4):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    tcB = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        tcB.append(el)
    tcPr.append(tcB)


def _left_border_only(cell, color, size=24):
    """左粗边框，其余无边框（治疗卡片用）。"""
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    tcB = OxmlElement("w:tcBorders")
    sides = {"top": ("single", 4, "E0E8F0"),
             "bottom": ("single", 4, "E0E8F0"),
             "right": ("single", 4, "E0E8F0"),
             "left": ("single", size, color)}
    for side, (val, sz, col) in sides.items():
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), val)
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), col)
        tcB.append(el)
    tcPr.append(tcB)


def _bottom_rule(para, color="2E75B6", size=8, space=4):
    pPr = para._element.get_or_add_pPr()
    for old in pPr.findall(qn("w:pBdr")):
        pPr.remove(old)
    pBdr = OxmlElement("w:pBdr")
    bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single")
    bot.set(qn("w:sz"), str(size))
    bot.set(qn("w:space"), str(space))
    bot.set(qn("w:color"), color)
    pBdr.append(bot)
    pPr.append(pBdr)


def _fix_table(table, col_widths_dxa):
    """固定列宽：tblGrid + tblLayout fixed + tcW。"""
    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    for tag in ("w:tblW", "w:tblLayout", "w:tblInd"):
        for old in tblPr.findall(qn(tag)):
            tblPr.remove(old)
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(sum(col_widths_dxa)))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)
    tblLayout = OxmlElement("w:tblLayout")
    tblLayout.set(qn("w:type"), "fixed")
    tblPr.append(tblLayout)
    old_grid = tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl.remove(old_grid)
    tblGrid = OxmlElement("w:tblGrid")
    for w in col_widths_dxa:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(w))
        tblGrid.append(gc)
    tblPr.addnext(tblGrid)
    for row in table.rows:
        for ci, cell in enumerate(row.cells):
            if ci >= len(col_widths_dxa):
                continue
            tcPr = cell._tc.get_or_add_tcPr()
            for old in tcPr.findall(qn("w:tcW")):
                tcPr.remove(old)
            tcW = OxmlElement("w:tcW")
            tcW.set(qn("w:w"), str(col_widths_dxa[ci]))
            tcW.set(qn("w:type"), "dxa")
            tcPr.append(tcW)


def _page_setup(doc):
    for sec in doc.sections:
        sec.page_width    = Cm(21)
        sec.page_height   = Cm(29.7)
        sec.top_margin    = Cm(2.5)
        sec.bottom_margin = Cm(2.5)
        sec.left_margin   = Cm(2.5)
        sec.right_margin  = Cm(2.5)
    doc.styles["Normal"].paragraph_format.space_before = Pt(0)
    doc.styles["Normal"].paragraph_format.space_after  = Pt(3)


def _footer(doc):
    section = doc.sections[0]
    footer  = section.footer
    para    = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.clear()
    run = para.add_run("第 ")
    _set_font(run, 8, color=RGBColor(0x88, 0x88, 0x88))
    for txt, ftype in [(" PAGE ", "begin"), (" PAGE ", None), (" PAGE ", "end"),
                       (" NUMPAGES ", "begin2"), (" NUMPAGES ", None), (" NUMPAGES ", "end2")]:
        pass
    # Simplified field insertion
    def _field(r, instr):
        fc1 = OxmlElement("w:fldChar"); fc1.set(qn("w:fldCharType"), "begin"); r._element.append(fc1)
        it  = OxmlElement("w:instrText"); it.text = instr; r._element.append(it)
        fc2 = OxmlElement("w:fldChar"); fc2.set(qn("w:fldCharType"), "end"); r._element.append(fc2)
    r1 = para.add_run("第 "); _set_font(r1, 8, color=RGBColor(0x88, 0x88, 0x88)); _field(r1, " PAGE ")
    r2 = para.add_run(" 页 / 共 "); _set_font(r2, 8, color=RGBColor(0x88, 0x88, 0x88)); _field(r2, " NUMPAGES ")
    r3 = para.add_run(" 页"); _set_font(r3, 8, color=RGBColor(0x88, 0x88, 0x88))


# ── Section headings ───────────────────────────────────────────────────────────
def heading_brief(doc, text):
    """简要版：左蓝边栏 + 浅蓝底色。"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after  = Pt(6)
    p.paragraph_format.left_indent  = Cm(0.4)
    pPr = p._element.get_or_add_pPr()
    # 浅蓝背景
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), "EBF3FB")
    for old in pPr.findall(qn("w:shd")): pPr.remove(old)
    pPr.append(shd)
    # 左边框
    pBdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single"); left.set(qn("w:sz"), "28")
    left.set(qn("w:space"), "8");   left.set(qn("w:color"), "2E75B6")
    pBdr.append(left)
    for old in pPr.findall(qn("w:pBdr")): pPr.remove(old)
    pPr.append(pBdr)
    r = p.add_run(text)
    _set_font(r, 11, bold=True, color=PRIMARY)


def heading_numbered(doc, number, text):
    """详细版：[N] 蓝色徽章 + 标题文字 + 分隔线。"""
    BADGE = 544
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    _fix_table(tbl, [BADGE, CONTENT_DXA - BADGE])
    # 徽章
    bc = tbl.rows[0].cells[0]
    _shading(bc, "2E75B6")
    _borders(bc, color="2E75B6", size=4)
    bp = bc.paragraphs[0]
    bp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    bp.paragraph_format.space_before = Pt(4)
    bp.paragraph_format.space_after  = Pt(4)
    _set_font(bp.add_run(str(number)), 10, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
    # 标题
    tc = tbl.rows[0].cells[1]
    _borders(tc, color="2E75B6", size=4)
    tp = tc.paragraphs[0]
    tp.paragraph_format.space_before = Pt(4)
    tp.paragraph_format.space_after  = Pt(4)
    tp.paragraph_format.left_indent  = Cm(0.4)
    _set_font(tp.add_run(text), 13, bold=True, color=PRIMARY)
    # 分隔线
    rule = doc.add_paragraph()
    _bottom_rule(rule, color="C5D8EC", size=4)
    rule.paragraph_format.space_before = Pt(0)
    rule.paragraph_format.space_after  = Pt(8)


# ── Covers ─────────────────────────────────────────────────────────────────────
def cover_brief(doc, data):
    patient = data.get("patient", {})
    dx      = data.get("diagnosis", {})
    p = doc.add_paragraph()
    _set_font(p.add_run("病情简要总结"), 22, bold=True, color=PRIMARY)
    p.paragraph_format.space_after = Pt(6)
    # 副标题
    parts = [dx.get("histology",""), dx.get("stage",""), dx.get("current_status","")]
    subtitle = "  ·  ".join(x for x in parts if x and x != "—")
    if not subtitle:
        subtitle = patient.get("diagnosis", "")
    if subtitle:
        ps = doc.add_paragraph()
        _set_font(ps.add_run(subtitle), 11, color=RGBColor(0x44, 0x44, 0x44))
        ps.paragraph_format.space_after = Pt(4)
    # 日期 + 声明
    date = patient.get("report_date", data.get("generated_at","")[:10])
    pd = doc.add_paragraph()
    _set_font(pd.add_run(f"报告日期：{date}"), 9, color=RGBColor(0x55, 0x55, 0x55))
    _set_font(pd.add_run("  |  仅用于临床交流参考，不替代主治医师的判断"), 9, color=RGBColor(0x88, 0x88, 0x88))
    pd.paragraph_format.space_after = Pt(6)
    # 分隔线
    rule = doc.add_paragraph()
    _bottom_rule(rule, color="2E75B6", size=8)
    rule.paragraph_format.space_after = Pt(12)


def cover_detailed(doc, data):
    patient = data.get("patient", {})
    dx      = data.get("diagnosis", {})
    # 面包屑
    pc = doc.add_paragraph()
    _set_font(pc.add_run("-- 病情详细总结"), 9, color=RGBColor(0x66, 0x66, 0x66))
    pc.paragraph_format.space_after = Pt(10)
    # 大标题
    parts = [dx.get("stage",""), dx.get("histology", patient.get("diagnosis","病情详细总结"))]
    title = "  ".join(x for x in parts if x and x != "—")
    pt = doc.add_paragraph()
    _set_font(pt.add_run(title), 26, bold=True, color=PRIMARY)
    pt.paragraph_format.space_after = Pt(8)
    # 副标题
    sub_parts = [dx.get("current_status",""), dx.get("initial_or_recurrence","")]
    subtitle = "  ·  ".join(x for x in sub_parts if x and x != "—")
    if subtitle:
        ps = doc.add_paragraph()
        _set_font(ps.add_run(subtitle), 11, color=RGBColor(0x44, 0x44, 0x44))
        ps.paragraph_format.space_after = Pt(10)
    # 元数据格（报告日期 / 分析文件数 / 语言）
    date    = patient.get("report_date", data.get("generated_at","")[:10])
    files_n = data.get("files_analyzed", 0)
    meta    = [("报告日期", date), ("分析文件", f"{files_n} 份"), ("语言", "简体中文")]
    MW = CONTENT_DXA // 4
    tbl = doc.add_table(rows=1, cols=4)
    _fix_table(tbl, [MW, MW, MW, CONTENT_DXA - 3*MW])
    for i, (lbl, val) in enumerate(meta):
        c = tbl.rows[0].cells[i]
        _borders(c, color="E8E8E8", size=2)
        p = c.paragraphs[0]
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after  = Pt(3)
        _set_font(p.add_run(lbl + "\n"), 8, color=RGBColor(0x88, 0x88, 0x88))
        _set_font(p.add_run(val), 10, bold=True, color=PRIMARY)
    _borders(tbl.rows[0].cells[3], color="E8E8E8", size=2)
    # 分隔线
    rule = doc.add_paragraph()
    _bottom_rule(rule, color="2E75B6", size=8)
    rule.paragraph_format.space_before = Pt(10)
    rule.paragraph_format.space_after  = Pt(14)


# ── Patient info table ─────────────────────────────────────────────────────────
def patient_info_table(doc, patient, extended=False):
    """无外框的患者信息表。extended=True 显示更多字段。"""
    LABEL_W = 2000
    VALUE_W = CONTENT_DXA - LABEL_W
    if extended:
        rows = [
            ("患者姓名",    patient.get("name","—")),
            ("性别 / 年龄", f"{patient.get('sex','—')} / {patient.get('age','—')}"),
            ("就诊医院",    patient.get("hospital","—")),
            ("主管医生",    patient.get("doctor","—")),
            ("ECOG 体能评分", patient.get("ecog","待医生评估")),
            ("临床诊断",    patient.get("diagnosis","—")),
            ("报告日期",    patient.get("report_date","—")),
            ("住院号",      patient.get("admission_no","—")),
            ("病员号",      patient.get("patient_id","—")),
            ("病历编号",    patient.get("patient_code","—")),
        ]
    else:
        rows = [
            ("性别 / 年龄",  f"{patient.get('sex','—')} / {patient.get('age','—')}"),
            ("就诊医院",     patient.get("hospital","—")),
            ("ECOG 体能评分", patient.get("ecog","待医生评估")),
            ("临床诊断",     patient.get("diagnosis","—")),
            ("报告日期",     patient.get("report_date","—")),
            ("病员号",       patient.get("patient_id","—")),
        ]
    tbl = doc.add_table(rows=len(rows), cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    _fix_table(tbl, [LABEL_W, VALUE_W])
    for ri, (lbl, val) in enumerate(rows):
        lc, vc = tbl.rows[ri].cells
        _shading(lc, "F2F6FB")
        _borders(lc, color="D0DCEB", size=4)
        lp = lc.paragraphs[0]
        lp.paragraph_format.space_before = Pt(4)
        lp.paragraph_format.space_after  = Pt(4)
        lp.paragraph_format.left_indent  = Cm(0.2)
        _set_font(lp.add_run(lbl), 9.5, bold=True, color=PRIMARY)
        _borders(vc, color="D0DCEB", size=4)
        vp = vc.paragraphs[0]
        vp.paragraph_format.space_before = Pt(4)
        vp.paragraph_format.space_after  = Pt(4)
        vp.paragraph_format.left_indent  = Cm(0.2)
        is_pending = str(val) in ("—","未取得") or "待" in str(val)
        _set_font(vp.add_run(str(val)), 9.5,
                  color=RGBColor(0x88,0x88,0x88) if is_pending else RGBColor(0x1A,0x1A,0x1A))
    doc.add_paragraph()


# ── Labs ───────────────────────────────────────────────────────────────────────
def labs_cards(doc, labs, n=4):
    """卡片网格（简要版）。"""
    if not labs:
        _set_font(doc.add_paragraph("暂无检验数据。").add_run(""), 10, color=RGBColor(0x88,0x88,0x88))
        return
    CW = CONTENT_DXA // n
    nrows = (len(labs) + n - 1) // n
    tbl = doc.add_table(rows=nrows, cols=n)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _fix_table(tbl, [CW]*n)
    for idx, item in enumerate(labs):
        ri, ci = divmod(idx, n)
        c = tbl.rows[ri].cells[ci]
        flag = item.get("flag","normal")
        if flag in ("high","low"):
            _shading(c, ALERT_BG)
        _borders(c, color="D0D8E4", size=4)
        # 项目名
        p1 = c.paragraphs[0]
        p1.paragraph_format.space_before = Pt(6)
        p1.paragraph_format.space_after  = Pt(1)
        p1.paragraph_format.left_indent  = Cm(0.25)
        _set_font(p1.add_run(item.get("item","—")), 8, color=RGBColor(0x77,0x77,0x77))
        # 值
        p2 = c.add_paragraph()
        p2.paragraph_format.space_before = Pt(0)
        p2.paragraph_format.space_after  = Pt(1)
        p2.paragraph_format.left_indent  = Cm(0.25)
        val = item.get("value","—")
        if flag == "high": val += " +"
        elif flag == "low": val += " -"
        _set_font(p2.add_run(val), 10, bold=True,
                  color=ALERT_T if flag in ("high","low") else PRIMARY)
        # 参考区间
        ref = item.get("reference","")
        if ref:
            p3 = c.add_paragraph()
            p3.paragraph_format.space_before = Pt(0)
            p3.paragraph_format.space_after  = Pt(6)
            p3.paragraph_format.left_indent  = Cm(0.25)
            _set_font(p3.add_run(ref), 7.5, color=RGBColor(0xAA,0xAA,0xAA))
        else:
            c.add_paragraph().paragraph_format.space_after = Pt(6)
    # 补空格
    filled = len(labs) % n
    if filled:
        for ci in range(filled, n):
            _borders(tbl.rows[nrows-1].cells[ci], color="F0F0F0", size=2)
    doc.add_paragraph()


def labs_table(doc, labs):
    """标准表格（详细版）。"""
    if not labs:
        _set_font(doc.add_paragraph("暂无检验数据。").add_run(""), 10, color=RGBColor(0x88,0x88,0x88))
        return
    headers   = ["日期","类别","检验项目","结果","参考值","临床意义"]
    col_widths = [1361, 998, 1814, 1270, 1179, 2450]
    tbl = doc.add_table(rows=1, cols=6)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _fix_table(tbl, col_widths)
    for i, h in enumerate(headers):
        c = tbl.rows[0].cells[i]
        _shading(c, HDR_BG); _borders(c)
        p = c.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_font(p.add_run(h), 9.5, bold=True, color=PRIMARY)
    for item in labs:
        flag = item.get("flag","normal")
        ab   = flag in ("high","low")
        row  = tbl.add_row()
        vals = [item.get("date","—"), item.get("category","—"), item.get("item","—"),
                item.get("value","—"), item.get("reference","—"), item.get("note","—")]
        for i, val in enumerate(vals):
            c = row.cells[i]; _borders(c)
            if ab: _shading(c, ALERT_BG)
            p = c.paragraphs[0]
            p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(2)
            if i == 3 and ab:
                arrow = " +" if flag=="high" else " -"
                _set_font(p.add_run(str(val)+arrow), 9.5, bold=True, color=ALERT_T)
            else:
                _set_font(p.add_run(str(val)), 9.5,
                          color=ALERT_T if (ab and i==5) else RGBColor(0x1A,0x1A,0x1A))
    doc.add_paragraph()


# ── Molecular ──────────────────────────────────────────────────────────────────
def molecular_table(doc, molecular):
    if not molecular:
        _set_font(doc.add_paragraph("暂无分子检测数据。").add_run(""), 10, color=RGBColor(0x88,0x88,0x88))
        return
    headers   = ["检测项目","结果 / 状态","优先级","临床意义"]
    col_widths = [2268, 2540, 998, 3266]
    tbl = doc.add_table(rows=1, cols=4)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _fix_table(tbl, col_widths)
    for i, h in enumerate(headers):
        c = tbl.rows[0].cells[i]
        _shading(c, HDR_BG); _borders(c)
        p = c.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_font(p.add_run(h), 9.5, bold=True, color=PRIMARY)
    PMAP = {"high": (ALERT_BG, ALERT_T, "关键"), "medium": (WARN_BG, WARN_T, "建议"), "low": ("", OK_T, "参考")}
    for item in molecular:
        bg, tc, lbl = PMAP.get(item.get("priority","medium"), (WARN_BG, WARN_T, "建议"))
        status = item.get("status","—")
        missing = any(kw in status for kw in ["未检测","未取得","Pending","待回报"])
        row = tbl.add_row()
        for i, val in enumerate([item.get("item","—"), status, lbl, item.get("note","—")]):
            c = row.cells[i]; _borders(c)
            if bg: _shading(c, bg)
            p = c.paragraphs[0]
            p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(2)
            if i==1 and missing:
                _set_font(p.add_run(str(val)), 9.5, color=RGBColor(0x88,0x88,0x88))
            elif i==2:
                _set_font(p.add_run(str(val)), 9.5, bold=True, color=tc)
            else:
                _set_font(p.add_run(str(val)), 9.5, color=RGBColor(0x1A,0x1A,0x1A))
    doc.add_paragraph()


# ── Imaging ────────────────────────────────────────────────────────────────────
def imaging_section(doc, imaging):
    note  = imaging.get("note")  if imaging else None
    items = imaging.get("items", []) if imaging else []
    if note:
        p = doc.add_paragraph(note)
        _set_font(p.runs[0] if p.runs else p.add_run(""), 10, color=RGBColor(0x88,0x88,0x88))
        doc.add_paragraph(); return
    if not items:
        p = doc.add_paragraph("暂无影像学报告。")
        _set_font(p.runs[0] if p.runs else p.add_run(""), 10, color=RGBColor(0x88,0x88,0x88))
        doc.add_paragraph(); return
    col_widths = [2268, CONTENT_DXA - 2268]
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _fix_table(tbl, col_widths)
    for i, h in enumerate(["日期 / 类型","影像学摘要"]):
        c = tbl.rows[0].cells[i]; _shading(c, HDR_BG); _borders(c)
        p = c.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_font(p.add_run(h), 9.5, bold=True, color=PRIMARY)
    for item in items:
        row = tbl.add_row()
        for i, val in enumerate([item.get("date_type","—"), item.get("summary","—")]):
            c = row.cells[i]; _borders(c)
            p = c.paragraphs[0]
            p.paragraph_format.space_before = Pt(3); p.paragraph_format.space_after = Pt(3)
            _set_font(p.add_run(str(val)), 9.5,
                      bold=(i==0), color=PRIMARY if i==0 else RGBColor(0x1A,0x1A,0x1A))
    doc.add_paragraph()


# ── Treatment timeline ─────────────────────────────────────────────────────────
def treatment_history(doc, treatment):
    lines   = treatment.get("lines", [])
    current = treatment.get("current", "")
    note    = treatment.get("note", "")
    if note:
        p = doc.add_paragraph(note)
        _set_font(p.runs[0] if p.runs else p.add_run(""), 10, color=RGBColor(0x88,0x88,0x88))
        doc.add_paragraph(); return
    if not lines:
        p = doc.add_paragraph("暂无既往治疗记录。")
        _set_font(p.runs[0] if p.runs else p.add_run(""), 10, color=RGBColor(0x88,0x88,0x88))
        doc.add_paragraph(); return
    if current:
        p = doc.add_paragraph()
        _set_font(p.add_run("当前状态  "), 9.5, bold=True, color=ACCENT)
        _set_font(p.add_run(current), 9.5, color=RGBColor(0x1A,0x1A,0x1A))
        p.paragraph_format.space_after = Pt(10)
    EFFICACY = {"CR": OK_T, "PR": OK_T, "SD": WARN_T, "PD": ALERT_T}
    for idx, line in enumerate(lines):
        ah = LINE_ACCENT_HEX[idx % len(LINE_ACCENT_HEX)]
        bh = LINE_BG_HEX[idx % len(LINE_BG_HEX)]
        ar = RGBColor(int(ah[0:2],16), int(ah[2:4],16), int(ah[4:6],16))
        # 卡片（1x1 table，左彩色粗边框）
        card = doc.add_table(rows=1, cols=1)
        card.alignment = WD_TABLE_ALIGNMENT.CENTER
        _fix_table(card, [CONTENT_DXA])
        cc = card.rows[0].cells[0]
        _shading(cc, bh)
        _left_border_only(cc, ah, size=20)
        # 标题行
        ph = cc.paragraphs[0]
        ph.paragraph_format.space_before = Pt(8)
        ph.paragraph_format.space_after  = Pt(4)
        ph.paragraph_format.left_indent  = Cm(0.5)
        _set_font(ph.add_run(f"第 {line.get('line', idx+1)} 线  --  "), 9.5, bold=True, color=ar)
        _set_font(ph.add_run(line.get("regimen","—")), 11, bold=True, color=PRIMARY)
        period = line.get("period","")
        if period:
            _set_font(ph.add_run(f"  |  {period}"), 9, color=RGBColor(0x66,0x66,0x66))
        # 详细字段
        for lbl, key, use_ec in [("疗效","efficacy",True), ("停药原因","stop_reason",False), ("毒副反应","toxicity",False)]:
            val = line.get(key,"")
            if not val: continue
            pd = cc.add_paragraph()
            pd.paragraph_format.left_indent  = Cm(0.5)
            pd.paragraph_format.space_before = Pt(2)
            pd.paragraph_format.space_after  = Pt(2)
            _set_font(pd.add_run(f"{lbl}："), 9, bold=True, color=RGBColor(0x55,0x55,0x55))
            vc = RGBColor(0x1A,0x1A,0x1A)
            if use_ec:
                for k, col in EFFICACY.items():
                    if k in str(val): vc = col; break
            _set_font(pd.add_run(str(val)), 9.5, color=vc)
        cc.add_paragraph().paragraph_format.space_after = Pt(6)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)
    doc.add_paragraph()


# ── Gaps ───────────────────────────────────────────────────────────────────────
def gaps_section(doc, gaps):
    critical    = gaps.get("critical", [])
    recommended = gaps.get("recommended", [])
    covered     = gaps.get("covered", [])
    ACTION_LBL  = {"现医院补检":"现医院可补检", "调阅历史档案":"需调阅历史档案",
                   "转诊专项检查":"需转诊专项检查", "组织已不可及":"组织标本不可及"}
    def gap_item(g, tc):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent  = Cm(0.5)
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after  = Pt(0)
        _set_font(p.add_run(f"- {g.get('item','')}"), 10, bold=True, color=tc)
        if g.get("reason"):
            _set_font(p.add_run(f"  --  {g['reason']}"), 9.5, color=RGBColor(0x55,0x55,0x55))
        if g.get("action_detail"):
            p2 = doc.add_paragraph()
            p2.paragraph_format.left_indent  = Cm(1.2)
            p2.paragraph_format.space_before = Pt(1)
            p2.paragraph_format.space_after  = Pt(4)
            lbl = ACTION_LBL.get(g.get("action_category",""), g.get("action_category",""))
            if lbl:
                _set_font(p2.add_run(f"[{lbl}]  "), 9, bold=True, color=RGBColor(0x44,0x44,0x44))
            _set_font(p2.add_run(g["action_detail"]), 9, color=RGBColor(0x44,0x44,0x44))
    if critical:
        p = doc.add_paragraph()
        _set_font(p.add_run("(紧急) 对后续分析至关重要（建议尽快补充）"), 10, bold=True, color=ALERT_T)
        p.paragraph_format.space_before = Pt(6)
        for g in critical: gap_item(g, ALERT_T)
    if recommended:
        p = doc.add_paragraph()
        _set_font(p.add_run("(建议) 有助于提升分析精准度"), 10, bold=True, color=WARN_T)
        p.paragraph_format.space_before = Pt(8)
        for g in recommended: gap_item(g, WARN_T)
    if covered:
        p = doc.add_paragraph()
        _set_font(p.add_run("(已覆盖) 已充分覆盖"), 10, bold=True, color=OK_T)
        p.paragraph_format.space_before = Pt(8)
        for g in covered:
            p2 = doc.add_paragraph()
            p2.paragraph_format.left_indent  = Cm(0.5)
            p2.paragraph_format.space_before = Pt(3)
            p2.paragraph_format.space_after  = Pt(2)
            _set_font(p2.add_run(f"- {g.get('item','')}"), 10, bold=True, color=OK_T)
            if g.get("reason"):
                _set_font(p2.add_run(f"  --  {g['reason']}"), 9.5, color=RGBColor(0x55,0x55,0x55))
    doc.add_paragraph()


# ── Review flags ───────────────────────────────────────────────────────────────
def review_flags_section(doc, flags):
    if not flags:
        p = doc.add_paragraph("所有提取字段已通过可疑值检查，无待确认项。")
        _set_font(p.runs[0] if p.runs else p.add_run(""), 10, color=OK_T)
        return
    red    = [f for f in flags if f.get("severity")=="red"]
    yellow = [f for f in flags if f.get("severity")=="yellow"]
    if red:
        p = doc.add_paragraph()
        _set_font(p.add_run(f"(待确认) 以下 {len(red)} 项需在使用本报告做决策前确认："), 10, bold=True, color=ALERT_T)
        p.paragraph_format.space_before = Pt(4)
        for f in red:
            p2 = doc.add_paragraph()
            p2.paragraph_format.left_indent  = Cm(0.5)
            p2.paragraph_format.space_before = Pt(2)
            _set_font(p2.add_run(f"[{f.get('id','RF')}]  {f.get('issue','')}"), 9.5, color=ALERT_T)
            if f.get("suggested_action"):
                p3 = doc.add_paragraph()
                p3.paragraph_format.left_indent = Cm(1.2)
                _set_font(p3.add_run(f"建议：{f['suggested_action']}"), 9, color=RGBColor(0x55,0x55,0x55))
    if yellow:
        p = doc.add_paragraph()
        _set_font(p.add_run(f"(建议核对) 以下 {len(yellow)} 项建议核对（不影响报告生成）："), 10, bold=True, color=WARN_T)
        p.paragraph_format.space_before = Pt(6)
        for f in yellow:
            p2 = doc.add_paragraph()
            p2.paragraph_format.left_indent  = Cm(0.5)
            p2.paragraph_format.space_before = Pt(2)
            _set_font(p2.add_run(f"[{f.get('id','RF')}]  {f.get('issue','')}"), 9.5, color=WARN_T)
    doc.add_paragraph()


# ── Sources ────────────────────────────────────────────────────────────────────
def sources_table(doc, sources):
    if not sources: return
    col_widths = [1633, 3266, 4173]
    tbl = doc.add_table(rows=1, cols=3)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _fix_table(tbl, col_widths)
    for i, h in enumerate(["模块","数据点","来源文件"]):
        c = tbl.rows[0].cells[i]; _shading(c, HDR_BG); _borders(c)
        _set_font(c.paragraphs[0].add_run(h), 9.5, bold=True, color=PRIMARY)
    for s in sources:
        row = tbl.add_row()
        for i, val in enumerate([s.get("module",""), s.get("field",""), s.get("file","")]):
            c = row.cells[i]; _borders(c)
            p = c.paragraphs[0]
            p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(2)
            _set_font(p.add_run(str(val)), 9)
    doc.add_paragraph()


# ── Disclaimer ─────────────────────────────────────────────────────────────────
def disclaimer(doc, data):
    doc.add_paragraph()
    rule = doc.add_paragraph(); _bottom_rule(rule, color="CCCCCC", size=6)
    rule.paragraph_format.space_after = Pt(4)
    gen   = data.get("generated_at", datetime.now().isoformat())
    fn    = data.get("files_analyzed", 0)
    fr, fy, fg = data.get("review_flags_red",0), data.get("review_flags_yellow",0), data.get("review_flags_green",0)
    txt = (f"本报告由 Cancer Buddy 自动生成 | 生成时间：{gen[:19]} | "
           f"分析文件数：{fn} | 待确认 {fr} · 建议核对 {fy} · 已通过 {fg} | "
           f"本报告不替代主诊医生的临床判断，所有治疗决策须与医生确认。")
    p2 = doc.add_paragraph()
    _set_font(p2.add_run(txt), 8, color=RGBColor(0x88,0x88,0x88))
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _kv(doc, label, val):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1); p.paragraph_format.space_after = Pt(1)
    _set_font(p.add_run(f"{label}："), 10, bold=True, color=RGBColor(0x44,0x44,0x44))
    pending = any(kw in str(val) for kw in ["未检测","未取得","Pending","待","—"])
    _set_font(p.add_run(str(val)), 10,
              color=RGBColor(0x88,0x88,0x88) if pending else RGBColor(0x1A,0x1A,0x1A))


# ── Builders ───────────────────────────────────────────────────────────────────
def build_brief(data, output_path):
    doc = Document(); _page_setup(doc); _footer(doc)
    cover_brief(doc, data)
    patient = data.get("patient", {})
    dx      = data.get("diagnosis", {})
    heading_brief(doc, "患者标识")
    patient_info_table(doc, patient, extended=False)
    heading_brief(doc, "病情概要")
    for lbl, key in [("确诊时间","date"),("原发部位","primary_site"),("病理类型","histology"),
                     ("临床分期","stage"),("转移部位","metastasis"),
                     ("初诊 / 复发","initial_or_recurrence"),("目前治疗状态","current_status")]:
        _kv(doc, lbl, dx.get(key,"—"))
    doc.add_paragraph()
    km = [m for m in data.get("molecular",[]) if m.get("priority")=="high"]
    if km:
        heading_brief(doc, "核心分子检测")
        molecular_table(doc, km)
    img = data.get("imaging",{})
    if img and (img.get("items") or img.get("note")):
        heading_brief(doc, "主要病灶分布")
        imaging_section(doc, img)
    heading_brief(doc, "关键实验室指标")
    labs_cards(doc, data.get("labs",[]))
    tx = data.get("treatment",{})
    if tx.get("lines") or tx.get("note"):
        heading_brief(doc, "治疗史")
        treatment_history(doc, tx)
    gp = data.get("gaps",{})
    if gp.get("critical") or gp.get("recommended") or gp.get("covered"):
        heading_brief(doc, "待完善检查 / 建议补充记录")
        gaps_section(doc, gp)
    flags = [f for f in data.get("review_flags",[]) if not f.get("user_confirmed")]
    if flags:
        heading_brief(doc, "待确认项")
        review_flags_section(doc, flags)
    disclaimer(doc, data)
    doc.save(output_path)
    print(f"[brief] Saved: {output_path}")


def build_detailed(data, output_path):
    doc = Document(); _page_setup(doc); _footer(doc)
    cover_detailed(doc, data)
    patient = data.get("patient", {})
    dx      = data.get("diagnosis", {})
    # §1 患者基本信息（不重复）
    heading_numbered(doc, 1, "患者基本信息")
    patient_info_table(doc, patient, extended=True)
    # §2 病情概要
    heading_numbered(doc, 2, "病情概要")
    for lbl, key in [("确诊时间","date"),("原发部位","primary_site"),("病理类型","histology"),
                     ("分化程度","differentiation"),("临床分期","stage"),
                     ("初诊 / 复发","initial_or_recurrence"),("转移部位","metastasis"),
                     ("目前治疗状态","current_status")]:
        _kv(doc, lbl, dx.get(key,"—"))
    doc.add_paragraph()
    # §3 分子检测
    heading_numbered(doc, 3, "分子检测与标志物")
    molecular_table(doc, data.get("molecular",[]))
    # §4 影像学
    heading_numbered(doc, 4, "影像学评估")
    imaging_section(doc, data.get("imaging",{}))
    # §5 实验室指标
    heading_numbered(doc, 5, "实验室指标摘要")
    labs_table(doc, data.get("labs",[]))
    # §6 治疗史
    heading_numbered(doc, 6, "治疗史")
    treatment_history(doc, data.get("treatment",{}))
    # §7 治疗路径
    pathway = data.get("pathway",{})
    if pathway:
        heading_numbered(doc, 7, "治疗路径总结")
        for issue in pathway.get("pending_issues",[]):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.5)
            _set_font(p.add_run(f"- {issue}"), 10)
        ns = pathway.get("next_steps","")
        if ns:
            p = doc.add_paragraph()
            _set_font(p.add_run("下一步可探索方向（非推荐，需医生评估）"), 10, bold=True,
                      color=RGBColor(0x44,0x44,0x44))
            p.paragraph_format.space_before = Pt(6)
            p2 = doc.add_paragraph(ns)
            _set_font(p2.runs[0] if p2.runs else p2.add_run(""), 10)
        doc.add_paragraph()
    # 附录
    heading_numbered(doc, "A", "建议补充记录")
    gaps_section(doc, data.get("gaps",{}))
    heading_numbered(doc, "B", "待确认项")
    review_flags_section(doc, [f for f in data.get("review_flags",[]) if not f.get("user_confirmed")])
    if data.get("sources"):
        heading_numbered(doc, "C", "信息来源索引")
        sources_table(doc, data["sources"])
    disclaimer(doc, data)
    doc.save(output_path)
    print(f"[detailed] Saved: {output_path}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_json");  parser.add_argument("output_docx")
    parser.add_argument("--type", choices=["brief","detailed"], default="brief")
    args = parser.parse_args()
    with open(args.data_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    (build_brief if args.type=="brief" else build_detailed)(data, args.output_docx)

if __name__ == "__main__":
    main()
