# v2 架构一览

```
患者 / 家属（对话）
        │
宿主模型（编排者）：只派活、只给用户看结果，不手写档案文件
  cancer-buddy 总入口：判断任务 → 路由到最小必要的子 skill
  子 skill：organize · visit-prep · charts · education · nutrition · caregiver · disclosure
            find-care · case-precedent · second-opinion · vault · web-access（第三方联网）
        │ 派子代理                  │ 调脚本                         │ 实时核验
        ▼                           ▼                                ▼
模型 worker                   scripts/cb.py（Python 3.9 标准库）    网页 / PubMed / 指南
 transcribe.md 逐页看图→转写稿   organize prepare|next|place|finish|check|note|move|discard
 synthesize.md 只读转写稿→JSON   render summary|visit-prep · chart · export · patients
        │ 写文件                 cblib/ common · prepare · organize · check · render · chart · export
        ▼                           │ 读 / 写
patient_dir  PT-XXXXXXXXXX/  （对外接口，smtb-skill 等直接读）
  raw/                原件（只进不改）+ _FILENAME_MAPPING.md + _identity/*.json（真实身份，仅供脚本复扫）
  .work/              页图、任务文件、summary_narrative.json、synth_done.json（可随时重建）
  01_…14_/<子类>/     转写稿 .md（front matter + 全文，{?X|Y} = 看不清）   ← 底层真相
  15_其他资料/         规则外材料照样全文入库     99_无关文件/  删除须逐项确认
     │ 汇总（source_refs: "路径.md#Lx-Ly"）
  结构化 JSON：profile · patient_summary · acute_findings · labs · molecular · treatment_lines ·
               timeline · comorbidities · longitudinal_observations · readiness · missing_items ·
               source_inventory · update_log · organize_meta
  叙事：case_text.md · timeline.md（[[src:…]]）· review_summary.md · INDEX.md · AGENTS.md
     │ 确定性渲染（html.escape）
  病情简要总结.html · case_summary_versions/ · 就诊准备包.html · charts/ · reports/ · share_log.json
```

organize 的进度只看磁盘：

```
prepare ─► next ─► transcribe（并行，每任务 ≤12 张图）─► place ─► next ─► synthesize（1 个子代理）
                ▲                                                            │
                └──── 转写稿集合变了 / 检查有错（最多修一轮）◄──── finish（检查→遮蔽→渲染→INDEX/AGENTS）
                                                                             │
                                                        review：急性发现 → 一句话病情 → 抽检摘要 →
                                                                待核对字段 → 无关文件 → HTML 路径
```
