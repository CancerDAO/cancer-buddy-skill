# 医疗资源候选清单模板

## 查询条件

- 用户提出的服务、地区、语言、支付和出行要求；
- 未核实或不应由 skill 判断的临床条件；
- 查询日期和数据来源。

## 未排序候选

每家机构使用相同字段：

```yaml
official_name: ""
location: ""
requested_service: ""
service_status: confirmed|unconfirmed
official_source_url: ""
verified_at: YYYY-MM-DD|null
appointment_route: ""
materials_requested_by_center: []
questions_to_confirm: []
```

不得出现 fit 分数、星级、推荐理由、最佳匹配或“适合/不适合你的治疗”。可以写“满足你提出的地理/语言条件”或“官方页面确认提供该服务”。

## 统一电话/在线核对问题

- 该服务目前是否开放，接诊对象和转诊流程是什么？
- 是否需要病理玻片/蜡块、影像原片、正式报告或翻译？
- 资料由患者本人还是原医疗机构发送？
- 费用、医保/保险和退改规则是什么？
- 谁负责临床预筛，多久会给出是否接诊的正式答复？

页脚：候选清单是导航信息，不代表医疗质量、入组资格或临床推荐；以机构实时确认和主诊团队讨论为准。
