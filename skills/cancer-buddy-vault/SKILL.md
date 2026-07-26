---
name: cancer-buddy-vault
description: "为患者的本地肿瘤资料建立清单、访问政策、导出与审计流程。分享必须依赖宿主鉴权和患者的明确、可撤销、限目的授权；不把 patient_code 或亲属关系当权限。Triggers on 数据保险箱, 健康档案, 数据分享, 导出病历, 撤销授权."
---

# cancer-buddy-vault

这是数据治理工作流，不是云存储、身份系统或法律授权替代品。详细规则见 [references/data-vault.md](references/data-vault.md)。

## Preconditions

- 宿主必须完成身份认证、授权校验和接收方确认；skill 不能自行发放 signed URL、密钥或访问权。
- 患者是默认控制者。照护者/家属访问需要可验证的权限范围、目的、期限和撤销状态。
- `patient_code` 只是目录定位符；知道它不代表可访问。

## Workflow

1. 盘点资料类型、PII、临床敏感性、来源和现有访问策略。
2. 所有对象默认 `private`。为每个授权记录 subject、recipient、scope、purpose、created_at、expires_at、revoked_at、legal/consent basis 和 host authorization reference。
3. 分享前生成清单：具体文件、接收方、目的、期限、是否含原始影像/病理/遗传信息、撤销与留存方式。患者/授权代表逐项确认。
4. 导出使用宿主提供的加密和密钥管理；密码/密钥通过独立安全通道传递。skill 不宣称本地 zip 等同合规传输。
5. 每次查看、导出、修改和撤销写入不可追加修改的审计事件；并发更新使用版本检查。
6. 撤销阻止未来访问，但诚实说明不能远程收回接收方已下载的副本；按机构政策请求删除并记录结果。

## De-identification

“去掉姓名”不等于匿名。导出前评估日期、罕见病、机构、地理、自由文本、影像 DICOM、基因组和文件元数据的重识别风险。研究/跨境用途需要适用法域下的伦理、数据保护和人类遗传资源审查；skill 不自行判定合规。

保留原始临床字符串；翻译/规范化是带 provenance 的附加层。脱敏不得改写剂量、单位、病理或分子结论。原件与派生件分别标识。

## Role behavior

- **Role = patient**：在宿主认证后管理自己的授权。
- **Role = caregiver**：仅限有效授权 scope；不能因曾被标为 caregiver 获得永久权限。
- **Role = family**：无授权时只能获得一般流程说明，不能查看患者记录或匿名化视图。

披露偏好不能阻止一个有能力的患者在认证后访问自己的信息。涉及能力、法定代理或争议时，停止分享并交由医疗机构隐私/伦理/法律流程处理。

## Disclosure

共享范围由当前 viewer 权限决定。family suppression 不能阻止有能力患者访问或导出自己的资料；也不能授权家属查看患者资料。每次导出独立确认 scope 和 recipient。

## Outputs

- `vault-manifest.md`
- `sharing-settings.json`
- `access.log`
- 经明确确认生成的导出包与 manifest

所有患者可见内容按 resolved locale 输出，同时保留源临床字符串与来源。遵循 `../../references/roles.md`、`../../references/i18n.md` 和 `../../references/clinical-content-governance.md`。

另见 `../../references/safety-guardrails.md` 与 `../../references/disclosure-behavior.md`。

## Charting an indicator the user asked about

When the user asks about a **specific named lab value or observation** (CEA, 白蛋白, 体重…),
check `longitudinal_observations.json` / `labs.json` for that analyte BEFORE answering in prose:

- **≥2 comparable points** → answer in text **and attach a chart**:
  `python3 ../cancer-buddy-charts/scripts/render_chart.py --chart trend --from-longitudinal <patient_dir>/longitudinal_observations.json --metric <analyte> --out-html <patient_dir>/charts/<analyte>_趋势.html`
- **fewer than 2, or not comparable** → answer in text and say in one line why there is no chart

Volunteering a chart covers only the analyte the user named. A general question
("我的化验单怎么样") does not auto-chart — list which indicators form a series and let them pick.
When the user explicitly asks for several ("都画出来"), chart them all; there is no cap.

**Answer the question, do not wall it off.** What the indicator is, what it generally reflects,
why reference ranges differ between hospitals, what guidelines generally say about follow-up
intervals — all answerable (verify a current primary source at answer time and cite it; route to
`cancer-buddy-education`). Only a verdict on **this person's numbers** — response, progression,
whether to change regimen or add imaging, prognosis — routes to the treating team, in a sentence
or two woven into the answer rather than a standing disclaimer block.

Keep implementation detail out of the reply: no script names, exit codes, rule numbers, or your
own verification steps.
