# 打电话 / 在线咨询要问的问题

每家都问同一组问题，方便比较。记下日期、接电话的部门。

## 通用

1. 这项服务现在还开放吗？接收哪些病人，怎么转诊或预约？
2. 需要带什么：病理切片或蜡块、影像原片（光盘）、正式报告、翻译件？
3. 资料由患者本人带去/寄去，还是由原医院发送？
4. 大概费用多少？能不能用医保或商业保险？异地就医需要先备案吗？取消或改期怎么处理？
5. 谁来做初步审核，多久能答复是否接诊？

## 临床试验另问

6. 这个试验在你们这里还在招募吗？（报注册号）
7. 联系谁做预筛？需要先提供哪些资料？
8. 参加试验的检查、药物、交通住宿费用怎么安排？

## 检索用的查询词（生成搜索，不直接给用户）

- `<城市> <癌种> 多学科会诊 MDT 门诊 site:<医院官网域名>`
- `<城市> 病理会诊 预约`
- `<癌种> <基因变异> recruiting site:clinicaltrials.gov`
- `<癌种> 临床试验 招募 site:chictr.org.cn`

候选记录的字段形状：`official_name`、`location`、`requested_service`、`service_status`（confirmed/unconfirmed）、`official_source_url`、`verified_at`、`appointment_route`、`materials_requested_by_center`、`questions_to_confirm`。
