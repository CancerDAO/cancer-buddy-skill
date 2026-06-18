#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cancer Buddy Report Template
用法: python report_template.py <report_data.json> <output.docx> [--type brief|detailed]

从 report_data.json 读取患者数据，生成统一排版的病例总结 Word 文档。
模板固定（字体/颜色/布局），数据变量（患者/检验/缺项）。
"""

import sys
import json
import argparse
from datetime import datetime
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ─────────────────────────────────────────────
# Design System
# ─────────────────────────────────────────────
PRIMARY   = RGBColor(0x1F, 0x3B, 0x5C)   # 深藏青  —— 文档标题
ACCENT    = RGBColor(0x2E, 0x75, 0xB6)   # 医疗蓝  —— 节标题
ALERT_T   = RGBColor(0xC0, 0x00, 0x00)   # 警示红  —— 异常值文字
WARN_T    = RGBColor(0xAD, 0x57, 0x00)   # 警示橙  —— 🟡 建议项
OK_T      = RGBColor(0x1B, 0x5E, 0x20)   # 深绿    —— ✅ 已覆盖

HDR_BG    = "D6E4F0"   # 表格表头背景（浅蓝）
ALERT_BG  = "FCE8E8"   # 异常行背景（浅红）
WARN_BG   = "FFF3E0"   # 建议项背景（浅橙）
OK_BG     = "E8F5E9"   # 正常背景（浅绿）
INFO_BG   = "EEF3F8"   # 患者信息块背景

FONT_CN   = "微软雅黑"
FONT_EN   = "Arial"

# A4 页面（DXA，1 DXA = 1/20 pt，1440 DXA = 1 inch）
# Content width = 21cm - 2.54cm*2 margins ≈ 15.92cm


# ─────────────────────────────────────────────
# Low-level helpers
# ─────────────────────────────────────────────

def _set_font(run, size_pt, bold=False, color=None, font_cn=FONT_CN, font_en=FONT_EN):
    run.font.name = font_en
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color
    # CJK font override
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), font_cn)


def _cell_shading(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    # Remove existing shd
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    tcPr.append(shd)


def _set_cell_borders(cell, color="D0D7DE", size=4):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        tcBorders.append(el)
    # Remove old borders
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    tcPr.append(tcBorders)


def _para_border_bottom(para, color="2E75B6", size=12, space=4):
    """Add bottom border to a paragraph (used as section divider)."""
    pPr = para._element.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single")
    bot.set(qn("w:sz"), str(size))
    bot.set(qn("w:space"), str(space))
    bot.set(qn("w:color"), color)
    pBdr.append(bot)
    pPr.append(pBdr)


def _page_number_footer(doc):
    """Add centered page number footer to all sections."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    section = doc.sections[0]
    footer = section.footer
    para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.clear()
    # "第 X 页 / 共 Y 页"
    run = para.add_run("第 ")
    _set_font(run, 8, color=RGBColor(0x88, 0x88, 0x88))
    fldChar = OxmlElement("w:fldChar")
    fldChar.set(qn("w:fldCharType"), "begin")
    run._element.append(fldChar)
    instrText = OxmlElement("w:instrText")
    instrText.text = " PAGE "
    run._element.append(instrText)
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "end")
    run._element.append(fldChar2)
    run2 = para.add_run(" 页 / 共 ")
    _set_font(run2, 8, color=RGBColor(0x88, 0x88, 0x88))
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "begin")
    run2._element.append(fldChar3)
    instrText2 = OxmlElement("w:instrText")
    instrText2.text = " NUMPAGES "
    run2._element.append(instrText2)
    fldChar4 = OxmlElement("w:fldChar")
    fldChar4.set(qn("w:fldCharType"), "end")
    run2._element.append(fldChar4)
    run3 = para.add_run(" 页")
    _set_font(run3, 8, color=RGBColor(0x88, 0x88, 0x88))


# ─────────────────────────────────────────────
# Document-level builders
# ─────────────────────────────────────────────

def add_section_heading(doc, text, level=1):
    """Add a styled section heading with colored bottom border."""
    para = doc.add_paragraph()
    run = para.add_run(text)
    if level == 1:
        _set_font(run, 13, bold=True, color=ACCENT)
        _para_border_bottom(para, color="2E75B6", size=12)
        para.paragraph_format.space_before = Pt(14)
        para.paragraph_format.space_after = Pt(6)
    else:
        _set_font(run, 11, bold=True, color=PRIMARY)
        para.paragraph_format.space_before = Pt(8)
        para.paragraph_format.space_after = Pt(4)
    return para


def add_patient_info_block(doc, patient):
    """Top block: patient demographics in a shaded info box."""
    # Outer table (1 row, 1 col) as a shaded box
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    _cell_shading(cell, INFO_BG)
    _set_cell_borders(cell, color="2E75B6", size=8)
    cell.width = Cm(15.92)

    p_title = cell.add_paragraph()
    r = p_title.add_run("病例总结报告")
    _set_font(r, 18, bold=True, color=PRIMARY)
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(8)
    p_title.paragraph_format.space_after = Pt(4)

    # Divider line
    p_div = cell.add_paragraph()
    _para_border_bottom(p_div, color="2E75B6", size=8)
    p_div.paragraph_format.space_after = Pt(4)

    # Info grid (2-col inner table)
    inner = cell.add_table(rows=4, cols=4)
    fields = [
        ("患者姓名", patient.get("name", "—"), "就诊医院", patient.get("hospital", "—")),
        ("年龄 / 性别", f"{patient.get('age','—')} / {patient.get('sex','—')}",
         "临床诊断", patient.get("diagnosis", "—")),
        ("采样 / 报告日期", patient.get("report_date", "—"),
         "ECOG 评分", patient.get("ecog", "待医生评估")),
        ("病员号", patient.get("patient_id", "—"),
         "病历编号", patient.get("patient_code", "—")),
    ]
    col_widths_dxa = [2200, 3300, 2200, 3300]
    for row_idx, (k1, v1, k2, v2) in enumerate(fields):
        cells = inner.rows[row_idx].cells
        for ci, (txt, is_label) in enumerate([(k1, True), (v1, False), (k2, True), (v2, False)]):
            c = cells[ci]
            c.width = Cm(col_widths_dxa[ci] / 567)  # approx
            _set_cell_borders(c, color="BFD0E0", size=4)
            if is_label:
                _cell_shading(c, "D6E4F0")
            p = c.paragraphs[0]
            r = p.add_run(txt)
            _set_font(r, 9.5, bold=is_label, color=PRIMARY if is_label else RGBColor(0x1A, 0x1A, 0x1A))
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)

    p_end = cell.add_paragraph()
    p_end.paragraph_format.space_after = Pt(6)
    doc.add_paragraph()


def add_key_value_para(doc, label, value, value_color=None, abnormal=False):
    """Single label: value line."""
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(1)
    para.paragraph_format.space_after = Pt(1)
    r_label = para.add_run(f"{label}：")
    _set_font(r_label, 10, bold=True, color=RGBColor(0x44, 0x44, 0x44))
    r_val = para.add_run(str(value))
    color = value_color if value_color else (ALERT_T if abnormal else RGBColor(0x1A, 0x1A, 0x1A))
    _set_font(r_val, 10, color=color)
    return para


def add_labs_table(doc, labs):
    """Lab results table. labs = list of dicts with keys: date, category, item, value, unit, reference, flag, note."""
    if not labs:
        p = doc.add_paragraph("暂无检验数据。")
        _set_font(p.runs[0], 10, color=RGBColor(0x88, 0x88, 0x88))
        return

    headers = ["日期", "类别", "检验项目", "结果", "参考值", "临床意义"]
    col_widths = [1400, 1400, 2200, 1600, 1600, 2200]  # DXA, sum=10400≈A4 content
    total_w = sum(col_widths)

    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Set total table width via XML
    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr")) or OxmlElement("w:tblPr")
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(total_w))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)

    # Header row
    hdr = table.rows[0]
    hdr.height = Cm(0.7)
    for i, (h, w) in enumerate(zip(headers, col_widths)):
        c = hdr.cells[i]
        c.width = Emu(w * 635)  # DXA → EMU (1 DXA = 635 EMU)
        _cell_shading(c, HDR_BG)
        _set_cell_borders(c)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h)
        _set_font(r, 9.5, bold=True, color=PRIMARY)

    # Data rows
    prev_category = None
    for row_data in labs:
        flag = row_data.get("flag", "normal")  # "high" | "low" | "normal" | "pending"
        is_abnormal = flag in ("high", "low")
        is_batch = row_data.get("batch", False)  # multiple items merged

        row = table.add_row()
        row_values = [
            row_data.get("date", "—"),
            row_data.get("category", "—"),
            row_data.get("item", "—"),
            row_data.get("value", "—"),
            row_data.get("reference", "—"),
            row_data.get("note", "—"),
        ]
        for i, (val, w) in enumerate(zip(row_values, col_widths)):
            c = row.cells[i]
            c.width = Emu(w * 635)
            _set_cell_borders(c)
            if is_abnormal:
                _cell_shading(c, ALERT_BG)
            p = c.paragraphs[0]
            if i == 3 and is_abnormal:  # value column
                arrow = " ↑" if flag == "high" else " ↓"
                r = p.add_run(str(val) + arrow)
                _set_font(r, 9.5, bold=True, color=ALERT_T)
            else:
                r = p.add_run(str(val))
                color = ALERT_T if (is_abnormal and i == 5) else RGBColor(0x1A, 0x1A, 0x1A)
                _set_font(r, 9.5, color=color)

    doc.add_paragraph()


def add_molecular_table(doc, molecular):
    """Molecular testing section table."""
    if not molecular:
        p = doc.add_paragraph("暂无分子检测数据。")
        _set_font(p.runs[0], 10, color=RGBColor(0x88, 0x88, 0x88))
        return

    headers = ["检测项目", "结果 / 状态", "优先级", "临床意义"]
    col_widths = [2800, 2800, 1100, 3700]
    total_w = sum(col_widths)

    table = doc.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr")) or OxmlElement("w:tblPr")
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(total_w))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)

    hdr = table.rows[0]
    for i, (h, w) in enumerate(zip(headers, col_widths)):
        c = hdr.cells[i]
        c.width = Emu(w * 635)
        _cell_shading(c, HDR_BG)
        _set_cell_borders(c)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h)
        _set_font(r, 9.5, bold=True, color=PRIMARY)

    PRIORITY_COLORS = {"high": (ALERT_BG, ALERT_T, "[关键]"), "medium": (WARN_BG, WARN_T, "[建议]"), "low": ("", OK_T, "[参考]")}

    for item in molecular:
        priority = item.get("priority", "medium")
        bg, tc, label = PRIORITY_COLORS.get(priority, (WARN_BG, WARN_T, "[建议]"))
        status = item.get("status", "—")
        is_missing = any(kw in status for kw in ["未检测", "未取得", "Pending", "待回报"])

        row = table.add_row()
        vals = [item.get("item", "—"), status, label, item.get("note", "—")]
        for i, (val, w) in enumerate(zip(vals, col_widths)):
            c = row.cells[i]
            c.width = Emu(w * 635)
            _set_cell_borders(c)
            if bg:
                _cell_shading(c, bg)
            p = c.paragraphs[0]
            r = p.add_run(str(val))
            if i == 1 and is_missing:
                _set_font(r, 9.5, color=RGBColor(0x88, 0x88, 0x88))
            elif i == 2:
                _set_font(r, 9.5, bold=True, color=tc)
            else:
                _set_font(r, 9.5, color=RGBColor(0x1A, 0x1A, 0x1A))

    doc.add_paragraph()


def add_gaps_section(doc, gaps):
    """建议补充记录 section（三层：紧急 / 建议 / 已覆盖）."""
    critical = gaps.get("critical", [])
    recommended = gaps.get("recommended", [])
    covered = gaps.get("covered", [])

    def add_gap_item(item_name, reason, text_color):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        r1 = p.add_run(f"▸  {item_name}")
        _set_font(r1, 10, bold=True, color=text_color)
        if reason:
            r2 = p.add_run(f"  —  {reason}")
            _set_font(r2, 9.5, color=RGBColor(0x55, 0x55, 0x55))

    if critical:
        p = doc.add_paragraph()
        r = p.add_run("【紧急】对后续分析至关重要（建议尽快补充）")
        _set_font(r, 10, bold=True, color=ALERT_T)
        p.paragraph_format.space_before = Pt(6)
        for g in critical:
            add_gap_item(g.get("item", ""), g.get("reason", ""), ALERT_T)

    if recommended:
        p = doc.add_paragraph()
        r = p.add_run("【建议】有助于提升分析精准度")
        _set_font(r, 10, bold=True, color=WARN_T)
        p.paragraph_format.space_before = Pt(8)
        for g in recommended:
            add_gap_item(g.get("item", ""), g.get("reason", ""), WARN_T)

    if covered:
        p = doc.add_paragraph()
        r = p.add_run("【已覆盖】已充分覆盖")
        _set_font(r, 10, bold=True, color=OK_T)
        p.paragraph_format.space_before = Pt(8)
        for g in covered:
            add_gap_item(g.get("item", ""), g.get("reason", ""), OK_T)

    doc.add_paragraph()


def add_review_flags_section(doc, flags):
    """review_flags 展示（只展示用户需要确认的项）."""
    if not flags:
        p = doc.add_paragraph("所有提取字段已通过可疑值检查，无待确认项。")
        _set_font(p.runs[0], 10, color=OK_T)
        return

    red = [f for f in flags if f.get("severity") == "red"]
    yellow = [f for f in flags if f.get("severity") == "yellow"]

    if red:
        p = doc.add_paragraph()
        r = p.add_run(f"【待确认】以下 {len(red)} 项需要在使用本报告做决策前确认：")
        _set_font(r, 10, bold=True, color=ALERT_T)
        p.paragraph_format.space_before = Pt(4)
        for flag in red:
            p2 = doc.add_paragraph()
            p2.paragraph_format.left_indent = Cm(0.5)
            p2.paragraph_format.space_before = Pt(1)
            r2 = p2.add_run(f"[{flag.get('id','RF')}]  {flag.get('issue','')}")
            _set_font(r2, 9.5, color=ALERT_T)
            if flag.get("suggested_action"):
                p3 = doc.add_paragraph()
                p3.paragraph_format.left_indent = Cm(1.2)
                r3 = p3.add_run(f"建议：{flag['suggested_action']}")
                _set_font(r3, 9, color=RGBColor(0x55, 0x55, 0x55))

    if yellow:
        p = doc.add_paragraph()
        r = p.add_run(f"【建议核对】以下 {len(yellow)} 项建议核对（不影响报告生成）：")
        _set_font(r, 10, bold=True, color=WARN_T)
        p.paragraph_format.space_before = Pt(6)
        for flag in yellow:
            p2 = doc.add_paragraph()
            p2.paragraph_format.left_indent = Cm(0.5)
            p2.paragraph_format.space_before = Pt(1)
            r2 = p2.add_run(f"[{flag.get('id','RF')}]  {flag.get('issue','')}")
            _set_font(r2, 9.5, color=WARN_T)

    doc.add_paragraph()


def add_treatment_history(doc, treatment):
    """治疗史 section."""
    lines = treatment.get("lines", [])
    current = treatment.get("current", "")
    note = treatment.get("note", "")

    if note:
        p = doc.add_paragraph(note)
        _set_font(p.runs[0], 10, color=RGBColor(0x88, 0x88, 0x88))
        return

    if current:
        add_key_value_para(doc, "当前治疗", current)

    if not lines:
        p = doc.add_paragraph("暂无既往治疗记录。")
        _set_font(p.runs[0], 10, color=RGBColor(0x88, 0x88, 0x88))
        return

    for line in lines:
        p = doc.add_paragraph()
        r = p.add_run(f"第 {line.get('line','?')} 线  ·  {line.get('period','')}  ·  {line.get('regimen','')}")
        _set_font(r, 10, bold=True, color=PRIMARY)
        p.paragraph_format.space_before = Pt(6)
        for key, label in [("efficacy", "疗效"), ("stop_reason", "停药原因"), ("toxicity", "主要毒副反应")]:
            if line.get(key):
                add_key_value_para(doc, label, line[key])

    doc.add_paragraph()


def add_disclaimer(doc, data):
    """Document footer disclaimer paragraph."""
    doc.add_paragraph()
    p = doc.add_paragraph()
    _para_border_bottom(p, color="CCCCCC", size=6)
    p.paragraph_format.space_after = Pt(4)

    p2 = doc.add_paragraph()
    generated_at = data.get("generated_at", datetime.now().isoformat())
    files_n = data.get("files_analyzed", 0)
    flags_r = data.get("review_flags_red", 0)
    flags_y = data.get("review_flags_yellow", 0)
    flags_g = data.get("review_flags_green", 0)
    txt = (f"本报告由 Cancer Buddy 自动生成 | 生成时间：{generated_at[:19]} | "
           f"分析文件数：{files_n} | 待确认 {flags_r} · 建议核对 {flags_y} · 已通过 {flags_g} | "
           f"本报告不替代主诊医生的临床判断，所有治疗决策须与医生确认。")
    r = p2.add_run(txt)
    _set_font(r, 8, color=RGBColor(0x88, 0x88, 0x88))
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER


# ─────────────────────────────────────────────
# Document builders
# ─────────────────────────────────────────────

def build_brief(data, output_path):
    """简要总结：患者信息 + 诊断概要 + 实验室 + 分子（概要）+ 建议补充 + review_flags."""
    doc = Document()

    # Page setup — A4, 2cm margins
    for section in doc.sections:
        section.page_width = Cm(21)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)

    # Default paragraph spacing
    doc.styles["Normal"].paragraph_format.space_before = Pt(0)
    doc.styles["Normal"].paragraph_format.space_after = Pt(4)

    _page_number_footer(doc)

    # ── 1. Patient info block ──────────────────
    add_patient_info_block(doc, data["patient"])

    # ── 2. 诊断概要 ────────────────────────────
    add_section_heading(doc, "诊断概要")
    dx = data.get("diagnosis", {})
    fields_dx = [
        ("原发部位", dx.get("primary_site", "—")),
        ("病理类型", dx.get("histology", "—")),
        ("临床分期", dx.get("stage", "—")),
        ("转移部位", dx.get("metastasis", "—")),
        ("初诊 / 复发", dx.get("initial_or_recurrence", "—")),
        ("目前治疗状态", dx.get("current_status", "—")),
    ]
    for label, val in fields_dx:
        is_pending = any(kw in str(val) for kw in ["未检测", "未取得", "Pending", "待"])
        add_key_value_para(doc, label, val,
                           value_color=RGBColor(0x88, 0x88, 0x88) if is_pending else None)

    doc.add_paragraph()

    # ── 3. 实验室指标摘要 ──────────────────────
    add_section_heading(doc, "实验室指标摘要")
    add_labs_table(doc, data.get("labs", []))

    # ── 4. 分子检测（仅关键项）─────────────────
    molecular = data.get("molecular", [])
    key_mol = [m for m in molecular if m.get("priority") == "high"]
    if key_mol:
        add_section_heading(doc, "分子检测（关键项）")
        add_molecular_table(doc, key_mol)

    # ── 5. 当前治疗 ────────────────────────────
    treatment = data.get("treatment", {})
    if treatment.get("current") or treatment.get("note"):
        add_section_heading(doc, "当前治疗状态")
        add_treatment_history(doc, treatment)

    # ── 6. 建议补充记录 ────────────────────────
    add_section_heading(doc, "建议补充记录")
    add_gaps_section(doc, data.get("gaps", {}))

    # ── 7. 待确认项 ────────────────────────────
    flags = data.get("review_flags", [])
    relevant = [f for f in flags if not f.get("user_confirmed", False)]
    if relevant:
        add_section_heading(doc, "待确认项")
        add_review_flags_section(doc, relevant)

    # ── Disclaimer ─────────────────────────────
    add_disclaimer(doc, data)

    doc.save(output_path)
    print(f"[brief] Saved: {output_path}")


def build_detailed(data, output_path):
    """详细总结：全7个模块 + 附录。"""
    doc = Document()

    for section in doc.sections:
        section.page_width = Cm(21)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)

    doc.styles["Normal"].paragraph_format.space_before = Pt(0)
    doc.styles["Normal"].paragraph_format.space_after = Pt(4)

    _page_number_footer(doc)

    # ── Cover block ────────────────────────────
    add_patient_info_block(doc, data["patient"])

    # ── 模块 1: 基本信息 ───────────────────────
    add_section_heading(doc, "模块 1　基本信息")
    patient = data["patient"]
    basic_fields = [
        ("姓名", patient.get("name", "—")),
        ("年龄", patient.get("age", "—")),
        ("性别", patient.get("sex", "—")),
        ("ECOG 评分", patient.get("ecog", "待医生评估")),
        ("就诊医院", patient.get("hospital", "—")),
        ("主管医生", patient.get("doctor", "—")),
        ("住院号", patient.get("admission_no", "—")),
        ("病员号", patient.get("patient_id", "—")),
    ]
    for label, val in basic_fields:
        is_pending = "待" in str(val) or "—" == val
        add_key_value_para(doc, label, val,
                           value_color=RGBColor(0x88, 0x88, 0x88) if is_pending else None)
    doc.add_paragraph()

    # ── 模块 2: 病情概要 ───────────────────────
    add_section_heading(doc, "模块 2　病情概要")
    dx = data.get("diagnosis", {})
    dx_fields = [
        ("确诊时间", dx.get("date", "—")),
        ("原发部位", dx.get("primary_site", "—")),
        ("病理类型", dx.get("histology", "—")),
        ("分化程度", dx.get("differentiation", "—")),
        ("临床分期", dx.get("stage", "—")),
        ("初诊 / 复发", dx.get("initial_or_recurrence", "—")),
        ("转移部位", dx.get("metastasis", "—")),
        ("目前治疗状态", dx.get("current_status", "—")),
    ]
    for label, val in dx_fields:
        is_pending = any(kw in str(val) for kw in ["未检测", "未取得", "Pending", "待", "—"])
        add_key_value_para(doc, label, val,
                           value_color=RGBColor(0x88, 0x88, 0x88) if is_pending else None)
    doc.add_paragraph()

    # ── 模块 3: 分子检测与标志物 ───────────────
    add_section_heading(doc, "模块 3　分子检测与标志物")
    add_molecular_table(doc, data.get("molecular", []))

    # ── 模块 4: 影像学 ─────────────────────────
    add_section_heading(doc, "模块 4　影像学评估")
    imaging = data.get("imaging", {})
    if imaging.get("note"):
        p = doc.add_paragraph(imaging["note"])
        _set_font(p.runs[0], 10, color=RGBColor(0x88, 0x88, 0x88))
    elif imaging.get("items"):
        for item in imaging["items"]:
            add_key_value_para(doc, item.get("date_type", "影像"), item.get("summary", "—"))
    doc.add_paragraph()

    # ── 模块 5: 实验室指标 ─────────────────────
    add_section_heading(doc, "模块 5　实验室指标摘要")
    add_labs_table(doc, data.get("labs", []))

    # ── 模块 6: 治疗史 ─────────────────────────
    add_section_heading(doc, "模块 6　治疗史")
    add_treatment_history(doc, data.get("treatment", {}))

    # ── 模块 7: 治疗路径总结 ───────────────────
    add_section_heading(doc, "模块 7　治疗路径总结")
    pathway = data.get("pathway", {})
    pending_issues = pathway.get("pending_issues", [])
    if pending_issues:
        p = doc.add_paragraph()
        r = p.add_run("待解决问题")
        _set_font(r, 11, bold=True, color=PRIMARY)
        for issue in pending_issues:
            p2 = doc.add_paragraph()
            p2.paragraph_format.left_indent = Cm(0.5)
            r2 = p2.add_run(f"☐  {issue}")
            _set_font(r2, 10)

    next_steps = pathway.get("next_steps", "")
    if next_steps:
        p = doc.add_paragraph()
        r = p.add_run("下一步可探索方向（非推荐，需医生评估）")
        _set_font(r, 10, bold=True, color=RGBColor(0x44, 0x44, 0x44))
        p.paragraph_format.space_before = Pt(8)
        p2 = doc.add_paragraph(next_steps)
        _set_font(p2.runs[0] if p2.runs else p2.add_run(""), 10)
    doc.add_paragraph()

    # ── 附录 A: 建议补充记录 ───────────────────
    add_section_heading(doc, "附录 A　建议补充记录")
    add_gaps_section(doc, data.get("gaps", {}))

    # ── 附录 B: 待确认项 ───────────────────────
    flags = data.get("review_flags", [])
    relevant = [f for f in flags if not f.get("user_confirmed", False)]
    add_section_heading(doc, "附录 B　待确认项")
    add_review_flags_section(doc, relevant)

    # ── 附录 C: 来源索引 ───────────────────────
    sources = data.get("sources", [])
    if sources:
        add_section_heading(doc, "附录 C　信息来源索引")
        headers = ["模块", "数据点", "来源文件"]
        col_widths = [1800, 3600, 4800]
        total_w = sum(col_widths)
        table = doc.add_table(rows=1, cols=3)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl = table._tbl
        tblPr = tbl.find(qn("w:tblPr")) or OxmlElement("w:tblPr")
        tblW = OxmlElement("w:tblW")
        tblW.set(qn("w:w"), str(total_w))
        tblW.set(qn("w:type"), "dxa")
        tblPr.append(tblW)
        for i, (h, w) in enumerate(zip(headers, col_widths)):
            c = table.rows[0].cells[i]
            c.width = Emu(w * 635)
            _cell_shading(c, HDR_BG)
            _set_cell_borders(c)
            p = c.paragraphs[0]
            r = p.add_run(h)
            _set_font(r, 9.5, bold=True, color=PRIMARY)
        for s in sources:
            row = table.add_row()
            for i, (val, w) in enumerate(zip([s.get("module",""), s.get("field",""), s.get("file","")], col_widths)):
                c = row.cells[i]
                c.width = Emu(w * 635)
                _set_cell_borders(c)
                p = c.paragraphs[0]
                r = p.add_run(str(val))
                _set_font(r, 9)
        doc.add_paragraph()

    # ── Disclaimer ─────────────────────────────
    add_disclaimer(doc, data)

    doc.save(output_path)
    print(f"[detailed] Saved: {output_path}")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Cancer Buddy Report Template")
    parser.add_argument("data_json", help="Path to report_data.json")
    parser.add_argument("output_docx", help="Output .docx path")
    parser.add_argument("--type", choices=["brief", "detailed"], default="brief")
    args = parser.parse_args()

    with open(args.data_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    if args.type == "brief":
        build_brief(data, args.output_docx)
    else:
        build_detailed(data, args.output_docx)


if __name__ == "__main__":
    main()
