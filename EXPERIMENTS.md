# 实验设计（参照 MSM）

本文件把 [MSM 论文](https://arxiv.org/abs/2605.02087) 的实验范式迁移到 SSM 的 skill/tool 域，给出可执行的详细设置。
凡标 **[MSM]** 的是论文/官方 repo 里有据可循的事实，**[SSM]** 的是我们针对工具域做的适配设计。

---

## 1. 核心假设

> **[SSM]** 在工具调用 SFT（Stage 2）**之前**，先用 SSM 语料 midtrain 基座模型，
> 能让对齐训练更好地**泛化到训练分布之外**——尤其是「何时**不该**调用」、
> 「在易混 skill 间怎么选」、以及「面对**没在 SFT 里见过的新 skill**」这三类情形。

对应 **[MSM]** 的主张：把讲解 Model Spec 的合成文档放在预训练与对齐微调之间训练，
能改善对齐的泛化；并且**「解释规则背后的价值」**和**「给具体而非笼统的指导」**两点都能进一步提升泛化。

---

## 2. SSM ↔ MSM 对应关系

| 维度 | **[MSM]** | **[SSM]** |
|---|---|---|
| 规范对象 | 一份 Model Spec（价值/行为） | 每个 skill 一份五要素 Skill Spec |
| 中训语料 | 讲解 Spec 的多体裁文档 | 讲解 skill 使用边界的多体裁文档 |
| 中训位置 | 预训练 → **MSM** → AFT | 预训练 → **SSM** → tool-use SFT |
| 对齐微调 | AFT：spec 对齐的 chat SFT（value/rule 两种风格） | Stage 2：function-calling / 工具调用 SFT |
| 主要 baseline | deliberative alignment、AFT-only | SFT-only（不中训）、in-context（spec 进 prompt 不训练） |
| 被测「行为」 | 安全/价值（是否做出 misaligned 动作） | 工具选择与使用判断（该不该调、调哪个、参数对不对） |
| 关键指标 | agentic misalignment **harmful 率** | 选择准确率、误触发/漏触发率、辨析准确率、调用合法率 |
| 关键发现 | 价值解释 + 具体性 → 更好泛化 | 消融 S2/S4/S5（理由）与 spec 具体性的贡献 |

---

## 3. 实验臂（训练条件 / baselines）

固定基座 **Qwen3.5-4B-Base**（与 `configs/train_qwen3p5_4b.yaml` 一致；**[MSM]** 主结果用 Qwen3-32B，见 §9，作为后续 scale-up）。

| 臂 | 流程 | 作用 |
|---|---|---|
| **B0 · SFT-only** | Base → 工具调用 SFT | 主 baseline（没有规范知识，纯轨迹模式） |
| **B1 · in-context** | Base + 把对应 Skill Spec 放进 system prompt，不训练 | 上界参照：规范在上下文里时能做到多好 |
| **A · SSM→SFT** | Base → **SSM midtrain** → 同一份工具调用 SFT | 主处理臂 |
| **C · deliberative**（可选） | Base → 在 SFT 里加「先依据规范推理再回答」的 CoT | 对标 **[MSM]** 的 deliberative alignment baseline |

A 与 B0 用**完全相同**的 SFT 数据与超参，唯一差别是 A 多了一段 SSM 中训——这样泛化差异才能归因到中训。

---

## 4. 数据切分（最关键）

**[SSM]** 为了测「分布外泛化」，必须留出训练中**从未出现**的 skill。从 16,983 个 skill 划分：

- **Seen 集**：参与 SSM 中训语料 + 工具调用 SFT 的 skill。
- **Held-out 集**：**既不进中训、也不进 SFT** 的 skill，只在评测时出现（测真正的 OOD 泛化）。
- **Confusable 对**：从 S3 的 TF-IDF 近邻里挑高相似 skill 对，部分留到 held-out，专测辨析。

建议比例：seen ≈ 85%、held-out ≈ 15%；held-out 内按 `kind`（skill_md / api_tool）与领域分层，避免某类被整段挖空。
切分脚本需固定 seed 并落盘 `data/splits/{seen,heldout}.txt`，保证三臂用同一切分。

---

## 5. 评测套件

分**分布内（ID）**与**分布外（OOD）**两层，OOD 是检验 SSM 价值的主战场。沿用 **[MSM]** 的「ID 看是否学会、OOD 看是否泛化」思路。

### 5.1 ID — 学没学会（seen skills）
- **E1 选择 QA**：给一个任务 + 候选 skill 列表，问该不该调、调哪个。指标：**选择准确率**。

### 5.2 OOD — 泛不泛化（held-out skills / 新场景）
- **E2 held-out 选择**：E1 同形式，但 skill 在训练中从未出现。指标：选择准确率（**主指标**）。
- **E3 该不该调（abstention）**：一半场景本应「不调用、用自身知识或澄清」（对应 S2）。
  指标：**误触发率**（不该调却调了）+ **漏触发率**（该调却没调）。这是工具域最易塌的方向。
- **E4 易混辨析**：confusable 对中二选一（对应 S3）。指标：**辨析准确率**。
- **E5 工具调用正确性**：真发起调用时，参数是否合法、是否幻觉参数、是否违反顺序/状态假设（对应 S1/S4）。
  指标：**调用合法率**、**幻觉参数率**。
- **E6 调用后验证（行为型）**：注入一个失败/异常返回，看模型是否自检、重试或如实报告而非硬扛（对应 S5）。

### 5.3 评测执行（对齐 [MSM] 方法）
- **[MSM]** 用 [inspect-ai](https://github.com/UKGovernmentBEIS/inspect_evals) 跑 agentic 行为评测，LLM-judge 打分（`harmful` 0/1 + accuracy/stderr），
  `--epochs 300 --temperature 0.7`，grader 用 `claude-sonnet`。
- **[SSM]** E2–E6 同样用 inspect + LLM-judge：每题多 epoch 重采样求均值与 stderr，judge 用强模型（如 `claude-sonnet-4-6`），
  judge 与被测严格分离。E1/E2/E4 也可用可判定的标准答案直接算准确率，省 judge 成本。
- **回归护栏**：跑一份通用能力 eval（如 MMLU 子集 + 通用工具调用 benchmark），确认 SSM 中训没损伤基础能力。

---

## 6. 消融（复现 [MSM] 的两个发现）

**[MSM]** 发现「解释价值」与「具体指导」改善泛化。**[SSM]** 对应消融，控制中训语料、SFT 与评测不变，只改 spec/语料：

- **A1 要素消融**：只用 S1（能力描述，≈ bare rule）的语料 vs 全五要素（含 S2/S4/S5 的**理由**）。
  预期：含理由的泛化更好 → 对应「解释价值 > 光列规则」。
- **A2 具体性消融**：笼统 principles vs 具体（带迷你案例、判据）的 principles。预期具体的更好。
- **A3 体裁多样性**：单一体裁（如只教程）vs 16 体裁混合。测多样性对泛化的贡献。
- **A4 assertion-targeting**：每篇聚焦少数要素（现设计）vs 每篇塞全部要素。测聚焦+整体覆盖是否更优。
- **A5 回放比例**：0% / 10% / 30% replay，测遗忘与泛化的权衡。

---

## 7. 训练超参

### 7.1 SSM 中训（已定，`configs/train_qwen3p5_4b.yaml`）
- Qwen3.5-4B-Base 续训；lr **2e-5**、cosine、warmup 50、weight_decay 0.1、grad_clip 1.0、1 epoch。
- 8×GPU × per_device 2 × grad_accum 8 × seq 4096 ≈ **512k tok/step**。
- replay **10%**（`build_corpus.py --replay ... --replay-ratio 0.10`，正式跑必开）。

### 7.2 工具调用 SFT（B0/A 共用，待定）
- 数据：从 seen skills 的真实/合成工具调用轨迹构造（function-calling 格式）。
- 关键：**B0 与 A 用同一份 SFT 数据与超参**，确保差异只来自中训。
- 风格：参照 **[MSM]** AFT 的 `value`（内化价值）vs `rule`（合规）两种 response 风格各跑一版，看交互效应。
  **[MSM]** AFT 默认 ~5000 样本、CoT 版 + `<think>` 剥离版各一份、问题去重阈值 0.91。

---

## 8. 主指标与成功判据

- **主结论指标**：E2（held-out 选择准确率）与 E3（误触发/漏触发率）上，**A 显著优于 B0**，且向 B1（in-context 上界）靠拢。
- **对标 [MSM]**：MSM 把 agentic misalignment 从 **54% 压到 7%**、并超过 deliberative baseline 的 **14%**（见 §9）。
  SSM 的对应叙事：在「该不该调」「易混辨析」这类 OOD 行为上，A 把错误率显著拉低，并优于 deliberative 臂 C。
- **无回归**：通用能力 eval 上 A 不低于 B0 超过约定阈值。
- 每个指标报 **mean ± stderr**（多 epoch），并跑显著性检验。

---

## 9. [MSM] 锚点数字（引用，供对标）

> 来自论文摘要（arXiv:2605.02087）：
> - 基座示例 **Qwen3-32B**；MSM 把 agentic misalignment 率从 **54% → 7%**；
> - 超过 deliberative alignment baseline 的 **14%**；
> - 「**解释规则背后的价值**」改善泛化；「**给具体而非笼统的指导**」改善泛化。

> 来自官方 repo：
> - MSM 数据生成用 `claude-opus-4-6`、temperature 1.0、每子域 20 doc_types × 25 doc_ideas；
> - AFT chat 默认 5000 样本、value/rule 两风格、CoT + 剥离两版、dedup 0.91；
> - agentic misalignment 评测：inspect-ai，exfiltration/leaking/murder 三场景，
>   `urgency_type=replacement`，`prod=true` 去思维草稿，epochs 300、temp 0.7、LLM-judge。

> ⚠️ 论文正文的完整训练超参（SFT recipe、全部模型尺寸、完整 eval 清单）不在官方 repo 内；
> 上面 §3–§8 中未标 [MSM] 的部分是 SSM 针对工具域的适配设计，正式开跑前应再核对论文正文。
