# 对话增量归档

对话信息可以进入患者自述层，但不能改写正式报告层。

## 先处理安全

若对话出现发热、呼吸困难、咯血/大出血、意识改变、抽搐、严重腹泻/脱水、无法保留液体或快速恶化，先按根目录安全护栏提示立即联系肿瘤团队/急诊。归档不能延误升级。

## 可归档内容

- 患者/照护者描述的症状、功能、用药实际执行、偏好和事件日期；
- 新收到文件的存在与位置；
- 患者对人口学信息的更正。

所有对话事实必须包含：

```yaml
provenance_layer: patient_reported|caregiver_reported
speaker_role: patient|caregiver|family
reported_at: ISO-8601
source_ref: conversation:<ISO-8601>
verification_status: unverified
```

## 不可直接更新

分期、ECOG、实验室值、分子结果、治疗线、诊断、疗效/进展和医生计划不能通过一次用户确认写入 `source_reported` 或 `clinician_verified`。可以保存患者自述的原话，但正式字段保持原值/null；冲突标 `disputed`。

## 确认卡

确认卡只询问“是否把这段话作为你的自述加入档案”，不询问“哪个临床值是真的”。沉默不写入，不删除。确认后追加事件，不覆盖原事件；更正用 `supersedes_event_id` 建立版本链。

如用户提供正式更正报告，走上传复核流程；如无正式来源，提示由出具机构或主诊医生核对。
