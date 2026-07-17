# 药物、食物与补充剂相互作用工作流

不得使用模型记忆或静态通用表判断相互作用，也不得因“未查到”而声称没有相互作用。

## 输入清单

分别列出并保留来源：

- 当前及近期处方药（通用名、商品名、剂型、给药途径、频次）；
- 非处方药；
- 维生素、矿物质、蛋白/营养补充剂；
- 草药、中成药、茶饮和特殊饮食；
- 酒精、葡萄柚等可能相关食物暴露。

患者/照护者口述与正式处方分层保存。无法确认是否仍在使用时标 `status: unknown`。

## 逐药实时核验

对每一种药：

1. 查当前法域监管机构批准的完整说明书；记录直接 URL、版本/日期和访问日期。
2. 查医院认可或权威的相互作用资源；记录资源名称和时间。
3. 只报告明确针对该药、剂型和给药方式的食物/补充剂信息。
4. 区分药物—食物、药物—补充剂、药物—药物和副作用管理；不要把冷敏感、NSAID/PPI 相互作用或食品安全混成“药食相互作用”。
5. 复制来源给出的临床动作，不自行发明“错开两小时”“少量安全”或严重度颜色。

## 失败关闭

如果标签、相互作用资源或具体产品成分无法确认：

```text
未确认：<药物/产品> 与 <食物/补充剂> 的相互作用。
原因：<缺少当前说明书/产品成分不明/来源冲突>。
下一步：在服用前向肿瘤药师或主诊团队核对。
```

不要默认 vitamin D、钙、益生菌、蛋白粉或任何草药“没有临床意义的相互作用”。

## 输出字段

```yaml
drug_source_name: 原文
normalized_drug: 已验证通用名或 null
coexposure: 食物/补充剂/药物
interaction_status: confirmed|possible|not_found_in_checked_sources|unconfirmed
clinical_action: 来源原文的动作或 null
source_url: 直接原始来源
source_version: 版本/日期
accessed_at: YYYY-MM-DD
pharmacist_review: pending|required|completed
```

任何潜在重大相互作用都应提示尽快联系肿瘤药师/主诊团队；skill 不指示患者自行停药、改剂量或改服药时间。

基线来源：NCI Cancer Therapy Interactions With Foods and Dietary Supplements：
https://www.cancer.gov/about-cancer/treatment/cam/hp/dietary-interactions-pdq
