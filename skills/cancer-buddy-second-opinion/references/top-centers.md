# 主要癌症中心信息速查

> **i18n note** — this is a static reference catalogue, not a patient-visible output, so its body is not localized. It IS the source for **`reviewer_locale`** (see `SKILL.md` → Locale): US/UK/SG/HK English-intake centers → `en`; 日本国立癌研究中心 / 癌研有明 → `ja`; domestic 三甲 / 养和繁中 → `zh`. Center names, addresses and contacts stay verbatim wherever they are quoted into a packet.

> **⚠️ Freshness contract — this catalogue is a routing hint, NOT a current source of intake/contact truth.** International-patient offices rename, move, change emails/portals, pause or close their second-opinion programs, and shift eligibility rules with no notice. A stale `intake / contact / program-status` line copied into a packet sends a patient's irreplaceable pathology blocks to a dead address and burns a scarce one-shot cross-border consultation slot. Therefore:
> - Every center below carries a `freshness` line: `last_verified` (date this catalogue entry was last hand-checked) · `verify_before_send` (true/false) · `source_url` (the center's own official international-patient page — the only authoritative source).
> - When `verify_before_send: true` (the default for every center with contact/intake/program detail), the SKILL.md **Verify-before-send** step requires a live web check of that center's contact / intake / program status against its `source_url` before any of it is quoted into a packet. Do not silently fall back to the values printed here.
> - If the live check disagrees with this catalogue, the live result wins; if the live check can't reach the source or can't confirm, the packet must say *"contact/intake to be confirmed by patient directly with the center"* — never present a stale line as current.
> - `last_verified` dates here are catalogue maintenance metadata; they do **not** substitute for the live check.

## 国内三甲

> `freshness` — `last_verified: 2026-06-08` · `verify_before_send: true` · `source_url:` 各院官网门诊/国际部页面。这里只列了院名与专长（无 intake/联系方式），名称相对稳定，但去某院做第二意见前仍须实时核当前的**专家门诊/会诊预约入口、所需材料、是否仍接收外院病例**——这些经常调整。

### 北京

- 中国医学科学院肿瘤医院（CAMS/PUMC 肿瘤医院）— 国内综合实力天花板之一
- 北京大学肿瘤医院 — 胸部、消化道强
- 解放军总医院（301）— 全面，尤其老年/多系统共病
- 首都医科大学附属北京友谊医院 — 消化

### 上海

- 复旦大学附属肿瘤医院 — 乳腺、妇科、消化道、胸部都强
- 上海交通大学医学院附属瑞金医院 — 血液肿瘤突出
- 上海中山医院 — 肝脏肿瘤
- 复旦大学附属华山医院 — 神经肿瘤

### 广州

- 中山大学肿瘤防治中心 — 鼻咽、肝癌强
- 广州医科大学附属第一医院 — 呼吸系统

### 其他

- 天津肿瘤医院
- 浙大一院/浙大二院（杭州）— 消化、胸部
- 华西医院（成都）— 综合性顶尖
- 哈尔滨医科大学附属肿瘤医院
- 湖南省肿瘤医院
- 山东省肿瘤医院

## 国际

### 美国

| 中心 | 位置 | 特长 | 第二意见方式 | freshness (`last_verified` · `verify_before_send` · `source_url`) |
|---|---|---|---|---|
| Memorial Sloan Kettering (MSK) | NY | 多癌种，基因组学、试验多 | 有 international office + 可支付远程咨询 | 2026-06-08 · true · mskcc.org/cancer-care/international |
| MD Anderson | Houston, TX | 多癌种，尤其 GI/血液 | International Center, 有远程服务 | 2026-06-08 · true · mdanderson.org/patients-family/becoming-a-patient/international-center.html |
| Mayo Clinic | Rochester, MN | 罕见癌、综合评估 | 有 online 2nd opinion 平台 | 2026-06-08 · true · mayoclinic.org/departments-centers/international |
| Dana-Farber | Boston, MA | 血液、儿科、乳腺 | Online Second Opinion Program | 2026-06-08 · true · dana-farber.org/for-patients-and-families/becoming-a-patient/get-a-second-opinion |
| Johns Hopkins | Baltimore, MD | 脑肿瘤、泌尿、神经 | International program | 2026-06-08 · true · hopkinsmedicine.org/international |
| UCLA / UCSF | CA | 多癌种、试验 | 有 international service | 2026-06-08 · true · uclahealth.org/international-services · ucsfhealth.org/international-services |

### 欧洲

| 中心 | 国家 | 特长 | freshness (`last_verified` · `verify_before_send` · `source_url`) |
|---|---|---|---|
| Bad Berka (Zentralklinik Bad Berka) | Germany | Lu-177 FAPI 放射治疗（全球少数几家）| 2026-06-08 · true · zentralklinik.de |
| Heidelberg University | Germany | 质子治疗、综合 | 2026-06-08 · true · heidelberg-university-hospital.com |
| Karolinska (Stockholm) | Sweden | 综合、临床试验多 | 2026-06-08 · true · karolinska.se/en |
| Royal Marsden | UK | 综合 | 2026-06-08 · true · royalmarsden.nhs.uk/private-care/international-patients |
| Institut Curie | France | 乳腺、眼肿瘤 | 2026-06-08 · true · curie.fr/en |
| Gustave Roussy | France | 综合、肉瘤 | 2026-06-08 · true · gustaveroussy.fr/en |

### 亚洲

| 中心 | 位置 | 特长 | 优势 | freshness (`last_verified` · `verify_before_send` · `source_url`) |
|---|---|---|---|---|
| 日本国立癌研究中心 | 东京 | 全癌种，质子治疗 | 质量高，中日医疗协作多年 | 2026-06-08 · true · ncc.go.jp/en |
| 癌研有明医院 | 东京 | 外科精湛，临床试验 | 同上 | 2026-06-08 · true · jfcr.or.jp/english |
| 新加坡国立大学癌症中心 (NCIS) | 新加坡 | 多癌种，英文接受 | 距离近，英文门槛 | 2026-06-08 · true · ncis.com.sg |
| 香港养和医院 | 香港 | 综合，中文接受 | 距离近，繁体中文 | 2026-06-08 · true · hksh.com |
| 韩国三星医疗中心 | 首尔 | 胃癌、肝癌强 | 亚洲人群数据 | 2026-06-08 · true · samsunghospital.com/gb/language/english |
| 台湾和信治癌中心 | 台北 | 综合 | 繁体中文 | 2026-06-08 · true · kfsyscc.org |

## 如何选目标中心

优先考虑:
1. **癌种专长匹配**（比如鼻咽癌 → 中山肿瘤；Lu-177 FAPI → Bad Berka）
2. **语言**（你能承担翻译吗？）
3. **距离 + 费用**
4. **可及性**（有些中心只接特定医保/身份）
5. **第二意见 vs 治疗**（你只要意见 还是 想过去治疗？）

## 不推荐

- 搜索引擎排名靠前的"网络第二意见"公司
- 社媒上推荐的"神医"
- 任何要求先预付高额"推荐费"的中介
- 未经实名认证的"国外名医合作"平台

如不确定某个中介是否靠谱，去该中心的官方网站查 **international patient office** 的直接联系方式，直接和中心确认。
