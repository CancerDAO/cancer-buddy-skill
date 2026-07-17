# 中国 MTB/复杂病例服务候选种子政策

本仓库不内置“强、成熟、顶级”中心名单。机构名称、服务和团队变化快，静态名单也容易把品牌声誉误当成个体质量。

运行时根据用户地区和所需服务，从以下入口建立候选：

- 卫生行政部门/监管机构的执业信息；
- 医院官方专科、MDT、病理/分子会诊和预约页面；
- 当前试验注册记录中的研究地点；
- 用户主诊团队提供的转诊网络。

种子记录只能包含查询词和官方入口，不能包含等级或临床适合性：

```yaml
query_name: ""
official_domain: ""
discovery_source: ""
last_verified: null
patient_facing_allowed: false
```

只有完成 `data-sources.md` 的 answer-time 核验后，机构才可进入 `output-template.md` 的未排序候选清单。
