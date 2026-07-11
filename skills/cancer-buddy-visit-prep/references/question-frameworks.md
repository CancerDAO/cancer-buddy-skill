# Question frameworks — visit-type scaffolds

Three skeletons of **questions a patient asks their own doctor**, one per `visit_type`. The subagent (see `visit-prep-html-prompt.md` §4) takes the matching set, lightly personalizes each skeleton by slotting in the patient's verbatim fields, and renders them into Block 2 Group D.

These are **questions only** — patient-facing, never clinical advice, never a treatment recommendation, never a ranking of options. The patient asks the doctor what the options/plan are; the framework never states them. Render in `profile.json.locale`; keep clinical entities verbatim (`../../cancer-buddy/references/i18n.md` §4). The skeletons below are `zh` samples — output the same questions in the patient's locale.

Slot tokens like `<诊断>` / `<当前方案>` / `<驱动基因>` are filled verbatim from the patient's structured fields. Drop any skeleton whose slot has no data rather than inventing content.

## 初诊 (`first`) — 第一次见这位医生 / 刚确诊

1. 我现在确切的诊断和分期是什么？（`<诊断>` / `<分期>`）有没有还没定下来、需要再确认的部分？
2. 要把分期/治疗方向定清楚，还需要补哪些检查（病理、影像、分子检测）？
3. 我的分子检测（`<驱动基因>` / 免疫指标）齐了吗？还差哪些、要不要补做？
4. 针对我这个情况，目前都有哪些治疗方向可以讨论？各自大概是怎么安排的？
5. 接下来的治疗大概节奏是怎样的（先做什么、多久评估一次效果）？
6. 治疗期间我自己要重点留意哪些症状？出现什么情况需要马上联系你们/去急诊？
7. 我这边的合并症 / 在吃的其他药，会不会影响治疗选择？需要先处理什么吗？
8. 要不要考虑多学科会诊（MDT/MTB）？怎么安排？
9. 复诊和检查的时间点怎么定？下次我该带什么来？

### 按癌种补场景专属追问（示例：卵巢癌初诊）

通用骨架之上，若已知具体癌种，再补几条对得上号的追问，患者才不会问得太泛。以卵巢癌初诊为例（其它癌种同理，按病情替换）：

- 我这个情况是先手术、还是先做几程化疗再手术（新辅助）？各自的考虑是什么？
- 手术能做到什么程度（有没有可能满意减瘤 / R0）？要不要术前评估腹水、腹膜情况？
- 我的 CA125 现在多少、之后怎么跟着看？多久复查一次、降到什么程度算有反应？
- 腹水/腹胀这块，接下来怎么处理和观察？出现什么情况要提前联系你们？
- 要不要做 BRCA / HRD 等分子检测？结果会不会影响后续维持治疗的选择？

（这些是**要问医生的问题**，不是答案；骨架永远只帮患者把问题问清楚，不替医生下判断。）

## 复诊 (`followup`) — 治疗中 / 定期复查

1. 我现在用的方案（`<当前方案>`）这一阶段效果怎么样？影像/指标怎么看？
2. 自从上次以来我有这些变化（新症状 / 指标趋势 / 新检查），这些需要处理吗？
3. 当前的副作用 / 不适，是预期内的吗？有什么能缓解的办法，需不需要调整？
4. 现在的方案是继续维持，还是到了要重新评估的节点？依据是什么？
5. 下一次评估疗效是什么时候？要做哪些检查？
6. 在两次复诊之间，出现哪些情况我要提前联系你们、哪些要直接去急诊？
7. 生活方式 / 饮食 / 运动这块，针对我现在的阶段有什么要注意的？

## 换线决策 (`switch`) — 进展了 / 在讨论换方案

1. 现在判断是疾病进展（`<当前方案>` 之后）吗？是依据影像、指标还是症状？
2. 进展之后，接下来有哪些可选的方向？分别是基于什么考虑？
3. 要做这个决定，还需要补哪些信息（重新活检、再次分子检测、新影像）吗？
4. 我之前的分子检测结果，对下一步选择还适用吗，要不要重测？
5. 换方案之后，疗效大概多久能评估出来？怎么判断有没有效？
6. 换方案在副作用 / 对我合并症的影响上，和现在比有什么不同？
7. 我适不适合考虑临床试验？哪里可以了解正在招募的试验？（找试验本身请走 find-care / 配套试验匹配 skill）
8. 如果这一步效果不好，再下一步通常会怎么考虑？让我心里有个大致预期。
9. 这个决定需不需要多学科会诊（MDT/MTB）一起定？
