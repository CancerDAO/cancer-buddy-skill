---
name: cancer-buddy-vault
description: 抗癌搭子·保险箱——看看档案里有什么、谁被授权看、按目的导出一部分病历给医生或家人、撤回授权。触发词：导出病历、分享病历、发给医生、给家人看、授权、撤回、谁能看、隐私、打包资料、删除分享。English: export records, share with doctor, authorize, revoke access, privacy, who can see. Requires the cancer-buddy skill.
---

# 保险箱：清单、授权、导出、撤回

帮患者掌控自己的病历：有什么、给了谁、为什么给、给到什么时候。

## 读什么

整个档案的清单（`INDEX.md`、`source_inventory.json`），按 [archive.md](../cancer-buddy/references/archive.md)。

## 能做什么

- **清单**：按类别列出档案里有哪些资料、日期范围、有没有已知缺页。
- **授权记录**：每条写清 给谁（recipient）、看哪些（scope）、为什么（purpose）、到什么时候（expires）、是否已撤回（revoked）。每次导出由脚本自动追加到 `<patient_dir>/share_log.json`；撤回时在对应条目上记 `revoked` 和日期。
- **限目的导出**：只导出这次目的需要的文件。

```
python3 "<cancer-buddy 目录>/scripts/cb.py" export <patient_dir> --out <目录> \
  --include <相对路径> [--include <相对路径> …] \
  --recipient "<接收方>" --purpose "<用途>" --expires-at <YYYY-MM-DD> \
  [--authorization-ref "<授权记录，如患者本人确认的日期和原话>"]
```

  导出包里会有 `_SHARE_MANIFEST.json`，记录接收方、范围、目的、到期日。导出前把这四项和文件清单念给用户确认一遍。
- **撤回**：在授权记录里标记撤回，并说明：已经下载或转发出去的副本，技术上收不回来。

## 边界

- 导出永远不含 `raw/`（原件带真实身份信息）；要给原件，请用户自己从原始来源提供。
- 不承诺"匿名""完全去标识"或"合规"；只说转写稿里遮蔽了哪些类别的身份信息。
- 不代发：导出包交给用户，由用户自己发送。
- 给家人看（如"发给表哥"）：先确认是患者本人同意、范围和期限；亲属关系本身不等于授权（guardrails 第 6 节）。
- 患者本人查看自己的资料，不受家属"先别告诉"的设置限制。
- 涉及基因数据出境（人类遗传资源相关规定），先当场核验现行规定；核验不了就不导出基因原始数据，并说明原因。

## 语气

平实地讲清楚"给出去就收不回"，不吓人，也不省略。

规则：[guardrails](../cancer-buddy/references/guardrails.md) · [引用](../cancer-buddy/references/citations.md)
