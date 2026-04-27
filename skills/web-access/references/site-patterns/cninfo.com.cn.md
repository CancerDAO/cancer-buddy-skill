---
domain: cninfo.com.cn
aliases: [巨潮资讯网, cninfo]
updated: 2026-04-25
---
## 平台特征
- 巨潮资讯网（深交所指定的上市公司公告披露平台），所有 A 股公司公告均可公开下载，无需登录。
- 静态层（curl/WebFetch）足够，无需 CDP。
- 偶发 502 Bad Gateway，需要重试。

## 有效模式

### 1. 反查股票 orgId（必需，公告查询要用）
- 深市股票（含主板、创业板、中小板）：列表 JSON 一次性下载
  ```
  GET http://www.cninfo.com.cn/new/data/szse_stock.json
  ```
  返回 `[{code, orgId, zwjc(中文简称), pinyin, category}, ...]`，orgId 形如 `9900012530` 或 `gssz0XXXXXX`。
- 上市公司通用 topSearch（深沪都行）：
  ```
  POST http://www.cninfo.com.cn/new/information/topSearch/query
  Content-Type: application/x-www-form-urlencoded
  X-Requested-With: XMLHttpRequest
  body: keyWord=600718&maxNum=5
  ```
  返回 `[{code, orgId, type(shj/szj), zwjc, ...}]`。**没有 sse_stock.json**（404），上交所必须用 topSearch 反查。
- 上交所部分公司 orgId 是 `gssh0600718` 形式，部分是 `9900029594` 形式（按上市批次）。

### 2. 公告查询 API（按类别 + 时间范围）
```
POST http://www.cninfo.com.cn/new/hisAnnouncement/query
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest

stock=300253,9900012530       # 必须是 "代码,orgId"，缺一不可
tabName=fulltext
pageSize=30
pageNum=1
column=szse                   # 深市=szse，沪市=sse
category=category_ndbg_szsh   # 年报；其他类别见下
plate=sz                      # 深市=sz，沪市=sh
seDate=2022-01-01~2026-12-31  # ~ 分隔
searchkey=
secid=
sortName=
sortType=
isHLtitle=true
```
返回 `{announcements: [{announcementTitle, adjunctUrl, announcementTime, ...}]}`。

常用 category：
- `category_ndbg_szsh` 年度报告
- `category_bndbg_szsh` 半年度报告
- `category_yjdbg_szsh` 一季度报告
- `category_sjdbg_szsh` 三季度报告
- `category_yjkb_szsh` 业绩快报
- `category_yjygjxz_szsh` 业绩预告

### 3. PDF 下载
adjunctUrl 形如 `finalpage/2024-04-19/1219672048.PDF`，前缀拼接：
```
http://static.cninfo.com.cn/finalpage/2024-04-19/1219672048.PDF
```
公开下载，无需 Cookie，无需 Referer。但加 `Referer: http://www.cninfo.com.cn/` 更稳。

### 4. 标题筛选（年报场景）
- 深市公司年报标题通常是 `2024年年度报告`（无公司前缀）
- 沪市公司年报标题通常是 `公司全称 + 2024年年度报告`（有公司前缀，如 `苏州麦迪斯顿医疗科技股份有限公司2024年年度报告`）
- 用 `re.search(r"(\d{4})年年度报告", title)` 而不是 `re.match`，能同时匹配两种格式
- 排除关键词：`摘要`、`英文版`/`English`、`提示性公告`、`更正公告`、`审计报告`、`更名公告`
- 多版本（如「2022年年度报告（更新后）」「2021年年度报告（更正后）」）取 `announcementTime` 最大的版本

### 5. 礼貌速率
连续抓取多家公司时建议 0.6-1.0s 间隔，否则可能短暂 502。批量 PDF 下载用 0.8s 间隔无问题。

## 已知陷阱
- `stock` 参数只传代码（如 `300253`）会返回空结果，必须 `代码,orgId` 格式。(2026-04-25 验证)
- 上交所没有 `sse_stock.json` 文件，请求会返回 404 HTML 错误页（gb2312 编码）。(2026-04-25 验证)
- 5 月份前 2025 年报可能尚未披露（法定截止日 4 月 30 日）。(2026-04-25 现状)
- 公司可能更名：如「思创医惠 → 思创智联」、「易联众 → ST易联众」，按代码查询不影响，但展示名应跟随最新名称。
