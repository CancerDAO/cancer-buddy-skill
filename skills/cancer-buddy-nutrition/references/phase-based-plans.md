# Treatment-phase nutrition support

Use this as a symptom-support menu, not a prescription. Render patient-visible prose in the resolved locale and keep clinical entities verbatim.

## Safety intake comes first

Before personalizing, ask about recent unintentional weight change, current intake and fluids, swallowing/chewing, vomiting/diarrhea/constipation, allergies, diabetes, kidney/liver/heart or fluid restrictions, ostomy/short-bowel/major GI surgery, treatment phase, and all medicines/herbs/supplements.

Do not generate a numeric calorie, protein, electrolyte or fluid target. Such targets depend on current weight/body composition, organ function, treatment, wounds, losses and goals; use only a target documented by the treating team or oncology dietitian.

Escalate to the oncology team/oncology dietitian for substantial weight loss, intake under roughly half of usual for several days, repeated dehydration, inability to swallow safely, tube/IV feeding, complex GI surgery, severe organ dysfunction, or mutually conflicting restrictions. The emergency gate overrides this workflow.

## Act-tonight defaults (give first, don't gate behind the intake)

Even before the full intake — and even while recommending escalation for weight loss — hand 2–3 concrete, generally-safe high-protein soft-food combos the patient can make **tonight** with ordinary kitchen ingredients. These are soft, easy to swallow, and add protein without any numeric target. Offer them, then ask the two load-bearing intake questions (weight change / swallowing + how much they're eating). Say "答得动多少算多少" so the questions don't read as a gate.

Default soft, high-protein combos (pick 2–3, in the user's locale):
- **鸡蛋羹 + 嫩豆腐**（蒸蛋里拌一点碾碎的嫩豆腐，滑软好咽）
- **鱼肉粥 / 鸡肉末粥**（粥里加去刺鱼肉或剁碎的鸡肉，温热不烫）
- **牛奶冲蛋白粉 / 牛奶燕麦糊**（若不耐乳糖可用无乳糖奶或豆奶）
- **肉末蔬菜软面 / 烂面条卧蛋**
- **酸奶 + 软香蕉 / 蒸南瓜泥**（当加餐，两餐之间垫一口）

Simple honest caveats to attach (not a full workup):
- 小口、多次，别硬撑一大碗；温的比烫的好咽。
- 只在这几条与用户已说的情况冲突时才收回：**吞咽呛咳/不能安全吞咽**（先别喂稠糊、找团队评估）、**明确的过敏**（如鸡蛋/牛奶过敏就换掉那一条）、**医生给过书面忌口/限液/限蛋白**（以书面为准）、**乳糖不耐/腹泻加重**（换无乳糖或先别上奶）。
- 不给克数、不给热量/蛋白目标、不给补剂剂量——那些要团队或营养师定。

If the intake later surfaces a contraindication, adjust or pull the specific item and explain why — but the patient should never be left with "先做检查再说" and nothing to eat.

## When family push back on 忌口 ("医生真这么说？")

Families often enforce heavy "忌口"（发物、不能吃鸡/鸡蛋/海鲜/豆制品之类）out of love, and it can starve a patient who most needs protein. When a relative pushes back on eating more, respond warmly and concretely, in the user's locale — don't lecture, don't override a real clinical instruction:

> "看得出你们是真心疼 Ta、怕吃错东西。有件事想跟你确认一下：这些不能吃的，是**主诊医生或营养师白纸黑字写下来的**，还是老家/网上传的说法？如果是医生写的，我们照着来，我帮你们看怎么在限制里把蛋白补够；如果是没写明的『发物』忌口，眼下 Ta 正需要多点蛋白和热量长力气、扛治疗——把鸡蛋、鱼、豆腐、奶这些软和好咽的加回来，往往比忌口更帮得上。拿不准的，下次门诊问一句医生『我这情况有没有真的要忌的口』最稳。"

- 只有团队**书面**忌口才算数；模型不替医生下"能吃/不能吃"的定论，也不否定真实医嘱。
- 把话题落到"怎么在允许范围内把蛋白补够"，并可路由到 `cancer-buddy-visit-prep` 帮他们把这句问题带去门诊。

## Universal supportive pattern

- Ask which foods are currently tolerable, affordable and culturally familiar.
- Prefer small, frequent opportunities to eat when appetite is poor.
- Include an ordinary protein-containing food when tolerated, without prescribing grams.
- Use pasteurized products and thoroughly cooked high-risk foods; wash hands and separate raw from cooked foods.
- Keep a short symptom/intake log if it helps the clinical team understand a persistent problem.
- Follow written fasting, texture, fluid, electrolyte and medication instructions exactly; do not generate replacements.

## Surgery

- Pre-operative fasting is determined by the surgical/anesthesia instructions. Never substitute a generic fasting interval.
- After surgery, diet advancement and texture depend on the operation and return of gut function. For GI, head/neck or swallowing surgery, use only the team's staged plan.
- New abdominal distension with persistent vomiting, inability to pass stool/gas, wound deterioration, or inability to drink needs clinical assessment.

## Chemotherapy or radiotherapy

- Nausea: bland or low-odor foods, cool/room-temperature foods, and small portions may be easier; persistent vomiting or poor fluids needs the treatment team.
- Mouth/throat pain: soft, moist, non-irritating foods may help. Inability to drink or swallow safely needs urgent assessment.
- Diarrhea: prioritize hydration only within any fluid/electrolyte plan and contact the team for persistent, severe, bloody, dizzying or treatment-related diarrhea. Do not prescribe a restrictive diet for prolonged use.
- Constipation: ask about obstruction red flags and the medication plan before suggesting more fiber; fiber can be inappropriate in some GI conditions.
- Food safety: do not assign restrictions from an ANC threshold alone. Follow the oncology/transplant team's instructions and ordinary safe-handling practices.

## Immunotherapy

No special “immune-boosting” diet is established. New or worsening diarrhea, abdominal pain, blood in stool, jaundice, severe fatigue, breathing symptoms, confusion or marked thirst/urination can be treatment toxicity and should be reported promptly; do not manage it only with diet.

## Targeted or oral anticancer therapy

Food instructions are product-specific and can differ by formulation and jurisdiction. Copy the patient's current official label/prescriber instruction verbatim and verify questions with an oncology pharmacist. Never generalize “take fasting,” “take with low-fat food,” or “avoid grapefruit” to an entire drug class.

## Follow-up or survivorship

Support an overall varied dietary pattern that fits comorbidities, preferences and finances. Avoid promising recurrence prevention from a particular food or diet. Alcohol, weight change and exercise questions should be individualized with the clinical team when cancer type, treatment or comorbidity changes the risk.
