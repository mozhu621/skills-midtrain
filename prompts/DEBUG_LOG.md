# Prompt 调试日志（SSM 数据合成）

模型：`deepseek/deepseek-v4-pro`（OpenRouter，reasoning effort=low）。
试点技能集（5 个，覆盖两种 kind）：

| skill_id | name | kind |
|---|---|---|
| `07243c481db28d33` | docx | skill_md |
| `72c3fda4371a8642` | frontend-design | skill_md |
| `72ebc3cfe7ac2f0e` | pdf | skill_md |
| `55bb430763edbe85` | calculateNursingHours | api_tool |
| `621858afebf6d62b` | getHealthWorkforce | api_tool |

---

## Round 1 — skill2spec v1（Spec 生成）

### 问题 1：`parse_json_block` 数组优先 bug
4/5 spec 报 "missing elements"。原因：解析器先找 `[`，把对象内部第一个
`principles` 数组当成顶层 JSON。修复：按 `[` / `{` 在文本中**最早出现位置**
排序尝试（src/common.py）。

### 问题 2：deepseek-v4-pro 思考 token 烧 max_tokens
3 个请求 finish_reason=length、pdf spec 正文为空——reasoning token 计入
completion 预算。修复（src/synth/client.py）：
- 请求加 `reasoning: {"effort": "low"}`（可调 `--reasoning-effort`）；
- `finish_reason=length` 或空文本 → 视为可重试错误，**不写缓存**，重试时
  `max_tokens ×= 1.5`；
- spec 默认 max_tokens 3500 → 6000。

### 验收（v1 重跑：5/5 OK，$0.0296）
- pdf spec 的 S3 真实对比 TF-IDF 近邻（pdf-analyzer、pdftk-server 等），给
  出"何时选哪个"的判据而非空泛描述；
- S4 抓到 SKILL.md 里真实的 reportlab Unicode 警告；
- api_tool spec 的 S4 有具体判例（London/Ontario 城市歧义、货币单位臆断）。
结论：spec prompt v1 验收通过，未再迭代。

---

## Round 2 — doc_ideas / doc_writer v1 → v2（讨论语料）

### v1 试点（20 docs，$0.0629）症状
| 指标 | v1 结果 | 危害 |
|---|---|---|
| 文档含 S1–S5 编号 | **19/20** | 模型学会内部术语，不是学推理 |
| 文档提及 "spec/guideline 文档" | **20/20** | 世界观穿帮：所有体裁都假装存在一份规范文件 |
| code_fence_heavy 被质量闸拒 | 2/20 | 训练语料应 prose 为主 |
| 误杀："lorem ipsum" placeholder 规则 | 1 篇 | frontend-design 文档合法出现该词 |

根因：digest 注入时带 `S1 capability & scope` 等标签头，写作模型自然
照搬；prompt 又无明确禁令。这违背 MSM 的核心——多样的自然语言重述，
而非术语回声。

### v2 修复（prompts/doc_ideas_v2.md、doc_writer_v2.md + 代码侧）
1. **digest 去标签**：`spec_digest(labeled=False)` 用普通标题（"When not
   to use it" 等），principles 无 `[S2]` 前缀（gen_specs.py）。
2. **明令禁 S 码**：writer 的 Voice constraints 写明 NEVER use "S1"…"S5"；
   ideas prompt 要求 idea 文本用平实措辞，S 码只进 `elements` 元数据。
3. **spec 提及体裁条件化**（gen_docs.py）：
   - `formal_spec_reference: true` 的体裁（audit report / best-practices
     memo / design doc review notes）走 FORMAL_RULE——团队确有成文
     guideline，可以引用；
   - 其余体裁走 INFORMAL_RULE——绝不提"spec/文档"，原则须化作作者
     经验、团队规矩、社区 lore。
4. **focus_elements 用平实短语**（PLAIN_FOCUS）替代 "S2, S3" 直拼。
5. **prose-first 指令** + 质量闸移除 lorem-ipsum 规则。

### v2 试点复测（20 docs，$0.0692，零失败；审计脚本 src/synth/audit_docs.py）

| 指标 | v1 | v2 |
|---|---|---|
| S1–S5 编号出现 | 19/20 | **0/20** |
| "spec/guideline" 提及 | 20/20 | **2/20**，且仅出现在 `formal_spec_reference: true` 的 audit report 体裁（设计内） |
| code_fence_heavy | 2/20 | 0/20 |
| 质量闸通过 | 17/20 | **20/20** |

抽检文风：原则以工程师口吻自然论辩（如 docx 表格 DXA vs 百分比宽度的
渲染分歧、pdfplumber vs pdf-analyzer 的合并单元格判据），无规范腔。
**v2 验收通过，定为生产版本。**

### 附带修复：`<content>` 标签残留
1/20 文档开头混入 `.<content>` 字面量——模型偶发重复开标签，非贪婪
regex 把第二个标签捕进正文。修复：`extract_tag` 剥离残留标签字面量
（src/common.py）；`quality.py` 增加 `</?(content|scratchpad)>` 泄漏
规则兜底。重提取后 0/20。

---

## Round 3 — doc_ideas / doc_writer v2 → v3（去"编故事"）

### v2 症状（用户复审指出）
v2 虽然消了术语回声，但 **skill 应用逻辑在"编故事"**：两段式 `idea→genre-doc`
里，`doc_ideas_v2` 第 22 行命令"anchor each idea in a specific realistic task or
**incident**"——逼模型虚构事件。对 Seal-Tools 合成 API（现实不存在）模型只能
瞎编（"Casey 工程师""London/Ontario""salary 75000""6 failures"全是幻觉当事实写），
一篇 ~90% 是虚构叙事支架，真正应用逻辑被淹没。

根因：偏离了母方法 **WRAP（arXiv 2401.16380）**——WRAP 的改写=保留信息只变
风格，从不虚构新场景；SSM 把"多样改写"做成了"多样虚构"。合成数据综述
（arXiv 2406.15126）亦印证：未接地生成 → "completely fictitious"。

### v3 修复（doc_ideas_v3.md、doc_writer_v3.md，代码无改动，复用占位符）
1. **ideas 切面化**：从"虚构一个 incident"改为"列举 usage reasoning 的不同
   *angle/facet*"（一条边界、一个判据、一个失败模式+预防原则、一个验证实践），
   显式禁止"a user once…/last quarter…"式情节。
2. **writer 接地诚实（核心）**：genre 降为"语气/格式外壳"，强制——绝不把虚构
   具体当真实发生（禁命名人物、虚构团队/公司、具体日期、"返回 75000"式实测数）；
   所有举例必须显式假设句（suppose / imagine / consider a case）；API skill 按
   契约+假设例推理，不臆造现实数值/货币/单位。
3. **原则密度下限**：多数句子须承载 skill 应用推理，叙事支架压到体裁所需最小。

### v3 调试复测（2 skill 靶点：getHealthWorkforce 合成API + frontend-design 真实skill_md；
###   2×4 genre×2 idea = 16 docs，$0.0488，零失败；audit_grounding.py 新增）

| 指标 | v2(同2skill,8) | v3(16) |
|---|---|---|
| S 码回声 | 0/8 | 0/16 |
| spec 提及 | 2/8（仅 audit 体裁，设计内） | 2/16（同前，设计内） |
| **含虚构-当事实的文档** | **4/8 (50%)** | **1/16 (6%)** |
| 虚构信号/篇 | 0.75 | **0.06** |
| 实测数虚构（"returned 75000"） | 3 | **0** |
| 计数虚构（"6 failures"） | 2 | **0** |
| 假设性框架/篇（hypo frames） | 0.4 | **1.6** |

抽检（getHealthWorkforce / case study）：通篇"Imagine an agent…/Consider what
would happen if…/Suppose the return payload is…"，脊梁是 occupation 强制律的
推理链（前置条件→输出语义未定义→验证不可行→可迁移判据），无任何编造事实。
v3 仅剩 1 例残留是 forum Q&A 提问者第一人称"Yesterday I asked…"（体裁自然，
正则假阳性）。**v3 候选生产版，待全量前可再压 prose-first（消除散文内 JSON 式
字段转储）。**

## Round 4 — doc_writer v3 → v4（补回 MSM 断言定向 + 接地规则对齐 + 中文支持）

### v3 的两个 MSM 偏离（复审定位）
1. **过度对冲**：v3 强制每个举例都用 "suppose/imagine"，比 MSM 更僵。MSM 母版
   （spec2doc_template.txt）只禁"可验证的虚构"（虚构人名/具体日期/引用/链接/
   实测数当真），允许自然具体的场景"存在于原则成立的世界里"，不必逐句对冲。
2. **丢了断言定向**：MSM 每篇文档定向一个 assertion 子集（"make SP2, SP3
   concrete"）。v3 只把 S 码映射成平实短语（focus_elements="when not to use it"），
   没把**具体原则句**喂给写作模型，密度和针对性都弱。

### v4 修复（doc_writer_v4.md、doc_ideas_v4.md、gen_docs.py）
1. **断言定向**：新增 `build_focus_principles()`——按 idea 选中的 S 码，从 Spec 里
   取出**真实 principle 句**，作为 "# Assertions to teach in this document" 注入
   writer（占位符 `{focus_principles}`）。focus_elements 保留向后兼容。
2. **接地规则对齐 MSM**："Realistic and non-fabricated" 段——禁可验证虚构具体
   （人名/日期/引用/URL/产品现实声明）+ 禁把虚构工具输出/实测数当真实观测，但
   明确"自然具体场景欢迎，不必逐句对冲"。比 v3 更接近母方法。
3. **密度律**："Skill-specific and dense"，多数段落须论 skill 用法及其理由。
4. **中文支持**：gen_docs 加 `--lang {en,zh}` → `LANG_RULES` 注入 `{language_rule}`；
   zh 要求全文简体中文，但 skill 名/API 参数名保留原文。

### v4 调试复测（getHealthWorkforce，--lang zh，2 genre×2 idea=4 docs，$0.0110，零失败）
- audit report（S2+S4 / S5+S2）：六类违规分条目，密度高、推理引导，principle 自然
  复述（occupation 缺失→输出语义未定义→零值是参数错非事实；伦敦歧义先澄清；
  doctor↔physician 术语映射；薪酬不臆断币种；零解释；重试一次仍异常即停报）。
  formal 体裁内引《使用指南》系设计内。无虚构人名/日期/实测数。
- case study（S4+S5）：原则以"团队内部一条铁律/一直有共识"入文（INFORMAL_RULE
  生效，未提 spec），推理链完整。轻微残留：开头"有一次"叙事框 + 行内 `occupation=
  "physician"` 字段写法（prose-first 边界）。中文 n_words 用 split() 失真（中文少空格），
  字符数 1.7k–2.2k 属正常长度。
**v4 候选生产版**：断言定向 + MSM 接地规则齐备，中文链路通。

## Round 5 — v4 体裁打磨（去"指南"机械引用 + 去清单感，并修一个连带回归）

### 症状（用户复审 audit report 体裁指出）
1. **"指南"被反复引用**：formal_spec_reference 体裁的 `FORMAL_RULE` 原文允许
   "may refer to and quote 'the usage guidelines'"，模型把它当拐杖，每条发现都
   "指南明确/指南规定/依照指南"（单篇 7–8 次），机械。
2. **清单感**：audit 体裁产出"6 条编号发现 + 6 条 bullet 建议"，全语料里最不像
   流动散文的一种。

### 修复
1. `FORMAL_RULE`（gen_docs.py）改为"**至多引用一两次**、变换措辞，其余用作者自己的
   分析口吻陈述，绝不逐条引规范"。
2. doc_writer_v4.md 加 "**Prose over checklist**" 律：让推理而非骨架承载文档，短列表
   可有但禁止"长编号发现 + 长 bullet 建议"叠成清单，列表项须是"判断+理由"的连贯分析。

### 连带回归（务必记）：去清单后模型改用"自然审计统计"→ **虚构数字**
v4b 复测：指南 8→0、编号/bullet→0，但一篇 audit 冒出"随机抽取 80 次""占 22%"
"3 例跨域""约 10%"——把**虚构的样本量/计数/百分比当真实审计发现**写，正是接地律
要禁的 measured-num 类幻觉。根因：把行文改"自然"诱导模型给具体统计；audit 体裁
style 里原写 "findings with counts described in prose"，"counts" 主动招数字。
- 修复 A：doc_writer_v4 接地段显式补"**audit/survey 统计同样适用**——不得虚构样本量/
  计数/百分比/频率当真实测量，改用定性量级（最常见/少量/偶尔/少数样本）"。
- 修复 B：doc_genres.yaml audit 体裁 style 把 "counts" 改为 "qualitative magnitude
  (never invented exact counts or percentages)"。

### v4c 终测（getHealthWorkforce zh，audit 体裁 2 篇）
| 指标 | v4 初版 | v4b | v4c |
|---|---|---|---|
| 指南提及/篇 | 7–8 | 0 | **0** |
| 数字列表项 | 0–5 | 0 | 0–4（建议区，判断+理由，合规） |
| bullet 堆 | 0–6 | 0 | **0** |
| 虚构统计 | 0 | **4** | **0** |
抽检 "Missing Occupation Misinterpretation"：纯散文三段发现+散文建议+结语，开篇自带
"所有发现基于定性分析，不涉及统计抽样或量化比率"的免责，无指南腔、无清单、无虚构数。
**经验沉淀：体裁"自然化"与"接地禁虚构"是一对张力——把 audit 写自然会诱发统计幻觉，
须在接地律里专门点名 audit 统计。** 注：审计脚本 FAB_NUM/MEASURED_NUM 仅英文正则，
对中文"80 次/22%"盲，复测时用临时中文正则手查（见会话）；全量前应给 audit_grounding
补中文统计模式。另：本轮 case study 偶发 1 例 `<content>` 未闭合（已知 tag 泄漏，sporadic）。

## 端到端冒烟（代码链路验证）

- `build_corpus.py`：v2 clean 20 docs → Qwen3.5-4B tokenizer，seq 1024
  打包（data/debug/corpus_v2）。
- `train_midtrain.py --smoke`：Qwen3.5-4B-Base 单卡 4 步，loss ~1.9–2.5，
  exit 0。注意：Qwen3.5 混合线性注意力架构，未装 `flash-linear-attention`
  + `causal-conv1d` 时回退 torch 实现（可跑）；正式 8 卡建议先装。
