# Data sources for find-care

按调研类型列出权威源。subagent 调度时优先派到这些源，**而不是**通用搜索引擎。一手 > 二手；机构官方 > 第三方汇编。

## 中国 — 医院/科室排名

| 源 | URL 模式 | 适合查 | 抓取注意 |
|---|---|---|---|
| 国家癌症中心 | `www.chinancc.org.cn` | 国家级癌种中心列表、专科诊疗能力 | 主要是机构资讯，需进二级页面 |
| 复旦版中国医院专科声誉排行 | `rank.cn-healthcare.com` | 各专科年度声誉排名（含肿瘤学、肿瘤外科、放疗等） | 年版本号要选最新，付费墙之外的免费榜单覆盖前 10–20 名 |
| 中国医学科学院科技量值（STEM） | `top100.imicams.ac.cn` | 医院学科科研量值排名 | 偏科研而非临床能力，参考用 |
| CSCO / CACA 年度学术大会专委会名单 | csco.org.cn / caca.org.cn | 反查某癌种谁是行业 KOL | 名单页常有反爬，建议 CDP |

## 中国 — 医生

| 源 | URL 模式 | 适合查 | 抓取注意 |
|---|---|---|---|
| 好大夫在线 | `www.haodf.com` | 患者评价 + 出诊医院 + 在线问诊门槛 | 反爬严格，**用 CDP**；提取时拿 DOM 里的 JSON-LD |
| 微医 / 春雨医生 | weiyi.com / chunyuyisheng.com | 出诊安排、互联网医院开方权限 | 需登录态才能看号源 |
| 院官网医生介绍页 | 医院域名/expert/、/doctor/ | 简介、亚专科方向、出诊时间 | URL 模式各院不同，先 WebSearch 定位 |
| Pubmed / Google Scholar | ncbi.nlm.nih.gov / scholar.google.com | 该医生近 5 年发表是否对口（如 EGFR 肺癌、CAR-T 等） | Pubmed 公开 API；Scholar 反爬严格 |
| 学会理事/委员名单 | csco.org.cn / cma.org.cn | 行业 standing 反查 | 静态页，curl 即可 |

## 中国 — 临床试验

| 源 | URL 模式 | 适合查 | 抓取注意 |
|---|---|---|---|
| ChiCTR | `www.chictr.org.cn` | 中国注册的临床试验全集 | 反爬中等；优先用 mcp__chictr__* MCP（如可用），否则 CDP |
| 国家药监局药物临床试验登记 | `www.chinadrugtrials.org.cn` | 药物试验登记（含尚未在 ChiCTR 注册的） | 必须登录态可能更全 |
| 中国临床试验联盟 | clinicaltrials.org.cn | 多中心合作信息 | 信息分散，参考用 |
| 各药企试验门户 | 各 sponsor 自有页 | 大厂赞助试验直查 | 各家 UI 不同 |

## 国际 — 用于跨境/参考

| 源 | URL 模式 | 适合查 |
|---|---|---|
| ClinicalTrials.gov | `clinicaltrials.gov` | 全球试验登记，可按 country=China filter | 公开 API，优先用 |
| US News Best Hospitals — Cancer | health.usnews.com/best-hospitals/rankings/cancer | 美国癌症医院排名 |
| QS World University Rankings — Medicine | topuniversities.com | 国际声誉参考 |
| ESMO / ASCO Annual Meeting 报告人 | esmo.org / asco.org | 国际同癌种 KOL 反查 |

## NGS 检测机构（需要时）

| 类别 | 代表 | 备注 |
|---|---|---|
| 三甲医院院内 NGS | 华西、复旦肿瘤、北肿、中山六院等 | 院内做样本不外送、报告解读直接和主诊对接 |
| 头部第三方检测 | 燃石、世和、泛生子、迪安诊断等 | 速度快但解读需额外配合医生 |
| 国际平台 | Foundation Medicine、Caris | 跨境样本运输复杂，慎选 |

## MTB / MDT 项目页

各院 MTB/MDT 项目通常在：
- 院新闻栏目（搜"分子肿瘤委员会成立 / 召开 / 病例"）
- 科室自主页（"多学科诊疗"、"MDT 门诊"）
- 微信公众号（搜该院公号 + 关键词）

**典型 query（给 subagent）**：
```
查 [院名] 是否设有针对 [癌种] 的 MTB（分子肿瘤委员会）或 MDT（多学科诊疗），获取：
- 是否有固定团队（病理/影像/外科/内科/放疗/分子）
- 召开频率（周/月/按需）
- 准入方式（院内转诊/外院申请/患者直接预约）
- 收费形式
来源限定：院官网、院公众号、新华网/健康报等权威媒体的院方报道
```

## 已知抓取陷阱

- **好大夫在线**：医生主页 URL 常含会话参数，CDP 内点击进入比手动构造 URL 可靠
- **微信公众号**：搜索引擎的索引常滞后，CDP 直登可能更新更快
- **ChiCTR**：搜索结果列表的链接可能丢参数；从详情页拿到的 trial registration number 才是稳定主键
- **复旦版排名**：页面有 PDF 下载，比 HTML 表格更结构化
- **院官网**：很多三甲的"专家介绍"页面是 SPA，curl 抓不到，必须 CDP

## 子 agent prompt 引用此文档

派发 subagent 时，**不要把整个 data-sources.md 塞 prompt**。挑出本次任务相关的 1–3 行（"查 X，源是 Y/Z"），让 subagent 自己加载 web-access skill 处理具体抓取。
