# Skill Spec Midtraining (SSM)

把 Anthropic **MSM**（*Model Spec Midtraining*，"先懂规范、再学行为"，[arXiv:2605.02087](https://arxiv.org/abs/2605.02087)）
的配方迁移到 **skill / tool 域**：

> 对每个 skill 先合成一份五要素 **Skill Spec**（讲清这个 skill *做什么、何时不该用、与谁易混、怎么失败、用完怎么验*），
> 再把这份 spec 写成多种体裁的"讨论文档"语料，用它 **midtrain** 一个基座模型，
> 让模型在做标准 tool-use SFT（Stage 2，另行）**之前**就已经内化了"何时调用、何时不调用"的判断。

核心假设：直接在工具调用轨迹上做 SFT，模型学到的是"看到这种请求就发这个调用"的模式匹配；
而先用自然语言把 skill 的**使用边界与判断依据**讲透，能让对齐更好地泛化到训练分布外的新情况。

文档导航：[`ROADMAP.md`](ROADMAP.md)（下一步清单）· [`EXPERIMENTS.md`](EXPERIMENTS.md)（实验协议）·
[`proposal.html`](proposal.html)（方案）· [`survey.html`](survey.html)（背景综述）。论文 LaTeX 源（同步 Overleaf）在工作区 `../latex/skill-midtrain/`，独立 git 仓库。
官方 MSM 配方参考放在 `refs/msm/`（**未纳入本仓库**，见 `.gitignore`；如需对照请自行 clone 原仓库）。

---

## 1. 五要素 Skill Spec

每个 skill 被结构化成五个要素；每个要素含一段 80–200 词的 `text` 和 2–5 条可独立引用的原子 `principles`（≈ MSM 的 *character assertions*）：

| 要素 | 含义 | 关键来源 |
|---|---|---|
| **S1** capability_scope | 能做什么、输入/输出契约、**边界**（明确说不能做什么） | 严格来自 skill 文档 |
| **S2** when_not_to_use | 何时**不该**调用：能用自身知识/更简单手段解决、前置条件未满足（应澄清）、超出范围（应直说） | 文档 + 工程判断 |
| **S3** contrastive_disambiguation | 与库内相似 skill（及"直接做不调用"）怎么二选一，给可迁移的**判据**而非硬规则 | TF-IDF 近邻注入 |
| **S4** failure_modes | 典型出错方式（幻觉参数、违反顺序/状态假设、误读输出、部分失败），每条带迷你案例 + 根因 | 文档 + 工程判断 |
| **S5** post_call_verification | 用完怎么自检结果，以及重试 / 换方案 / 如实报告失败的策略 | 工程判断 |

S3 的"相似 skill"由 `gen_specs.py` 内的 `NeighborIndex` 提供：在 name+description 上做 TF-IDF 余弦，
**同 kind 内**取 top-4 近邻注入 prompt，让对比锚定在真实存在的兄弟 skill 上（而非模型臆造）。

---

## 2. 流水线总览

```
configs/sources.yaml
   │  01 download        src/collect/download.py
   ▼
data/raw/                128 个 repo 克隆 + 市场站点收割 + Seal-Tools / xLAM 工具池
   │  02 parse           src/collect/parse_skills.py
   ▼
data/skills.jsonl        16,983 skills  =  12,907 skill_md  +  4,076 api_tool（统一 schema）
   │  03 specs (Stage A) src/synth/gen_specs.py        skill → 五要素 Spec
   ▼
data/specs/specs.jsonl   每行一份 Skill Spec（+ data/specs/md/ 人读版）
   │  04 docs (Stage B)  src/synth/gen_docs.py → src/synth/quality.py
   ▼
data/docs/docs_clean.jsonl   多体裁讨论文档，过完泄漏/去重质量闸
   │  05 train (Stage C) src/train/build_corpus.py → src/train/train_midtrain.py
   ▼
data/corpus/{train,val}.bin  →  checkpoints/ssm_*   （打包 + midtrain Qwen3.5-4B-Base）

—— 实验闭环（Stage D，验证核心假设；设计见 EXPERIMENTS.md）——

data/skills.jsonl
   │  06 split           src/exp/split.py             seen 85% / held-out 15% + 易混对
   ▼
data/splits/{seen,heldout}.txt + confusable.jsonl
   │  07 build_sft       src/exp/build_sft.py         seen skill → 工具调用 SFT 数据
   ▼
data/sft/sft_{train,val}.jsonl
   │  08 sft             src/exp/sft_train.py         B0=Base / A=midtrained，同一份 SFT
   ▼
checkpoints/sft_{b0,a}/final
   │  09 build_evals     src/exp/build_evals.py       spec → E1–E6 评测题（seen=E1, held-out=E2–E6）
   ▼
data/evals/evals.jsonl
   │  10 eval            src/exp/run_eval.py          跑模型 + 打分（exact-match + LLM-judge），mean±stderr
   ▼
data/evals/results/{tag}_summary.json
```

**Stage B 是两段式**（沿用 MSM 的 *doc_idea → doc* 拆分）：
先按 `(skill, 体裁)` 让模型头脑风暴 `n_ideas` 条文档点子，再对每条点子各写一篇完整文档。

---

## 3. 快速开始

### 环境

```sh
# 仓库内统一用这个解释器（torch 2.7 + flash-attn 2.8 + transformers 5.8）
PY=/raid/longhorn/yuhao/envs/living-lm/bin/python
# 依赖见 requirements.txt（pip install -r requirements.txt）：
#   合成阶段只需 requests/pyyaml/tqdm/numpy；训练/评测阶段加 torch/transformers/accelerate。
```

合成阶段需要 **OpenRouter** key，按优先级解析：环境变量 `OPENROUTER_API_KEY` → `~/.bashrc` 里的 `export OPENROUTER_API_KEY=...`。
key 不写进仓库（`src/common.py:load_openrouter_key`）。

### 跑通全流程

```sh
scripts/01_download.sh                       # 下载源（已跑完，产物在 data/raw/）
scripts/02_parse.sh                          # 解析入库（已跑完 → data/skills.jsonl）

scripts/03_specs.sh  --limit 100             # Stage A：先小批量生成 100 份 Spec
scripts/04_docs.sh   --limit 100             # Stage B：合成文档 + 过质量闸
scripts/05_train.sh  --smoke                 # 单卡 4 步冒烟（用 data/debug/corpus_v1）

NGPU=8 scripts/05_train.sh                    # 8 卡正式 midtrain（512k tok/step）

# —— 实验闭环（Stage D，详见 EXPERIMENTS.md）——
scripts/06_split.sh                          # 冻结 seen/held-out 切分 + 易混对（seed 1234）
scripts/07_build_sft.sh                      # seen skill → 工具调用 SFT 数据（B0/A 共用）
scripts/08_sft.sh  --model Qwen/Qwen3.5-4B-Base       --output-dir checkpoints/sft_b0   # 臂 B0
NGPU=8 scripts/08_sft.sh --model checkpoints/ssm_qwen3p5_4b/final --output-dir checkpoints/sft_a  # 臂 A
scripts/09_build_evals.sh                    # spec → E1–E6 评测题
scripts/10_eval.sh --model checkpoints/sft_b0/final --tag B0       # 跑分（B0）
scripts/10_eval.sh --model checkpoints/sft_a/final  --tag A        # 跑分（A）
scripts/10_eval.sh --model Qwen/Qwen3.5-4B-Base --in-context --tag B1   # 上界参照（spec 进 prompt）
```

每个 `scripts/0X_*.sh` 只是 `. scripts/00_env.sh` 后调对应的 `src/` 脚本，**多余参数会透传**给底层脚本，
所以上面的 `--limit / --smoke` 等都能直接加在脚本名后面。

---

## 4. 各阶段细节

### Stage A — `src/synth/gen_specs.py`（`03_specs.sh`）

skill → 五要素 Spec（JSON），过 `validate_spec`（每要素 text ≥ 30 词、principles 1–8 条、含 skill_summary），失败的进 `specs_failed.jsonl`。

常用参数（默认值）：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--limit N` | 0(全部) | 只取前 N 个 skill |
| `--kind` | "" | 过滤 `skill_md` / `api_tool` |
| `--ids a,b` | "" | 指定 skill id |
| `--neighbors` | 4 | S3 注入的近邻数 |
| `--model` | `deepseek/deepseek-v4-pro` | 合成模型 |
| `--temperature` | 0.6 | |
| `--max-tokens` | 6000 | reasoning 模型要留足思考预算 |
| `--reasoning-effort` | low | |
| `--concurrency` | 8 | |
| `--prompt-version` | v1 | 用 `prompts/skill2spec_<v>.md` |
| `--render-md` | off | 额外输出 `data/specs/md/*.md` 人读版 |

`03_specs.sh` 已默认带 `--prompt-version v1 --render-md`。

### Stage B — `src/synth/gen_docs.py` + `src/synth/quality.py`（`04_docs.sh`）

**生成**（两段式，见 §2）。每篇文档会被分配一个 spec 要素子集（`elements`，如 `["S2","S3"]`），
prompt 里只塞这几个要素对应的 `principles`（**MSM 式 assertion-targeting**：单篇聚焦、语料整体覆盖）。

体裁来自 `prompts/doc_genres.yaml`（**16 种**，带采样权重与 `elements_bias`），按权重无放回采 `n_genres` 种。
体裁分两类，由 `formal_spec_reference` 标志切换 spec 引用口径：

- **正式体裁**（design doc review notes / best-practices memo / agent behavior audit report）：允许"轻点一下规范"，但不得逐条引用规则。
- **非正式体裁**（其余 13 种）：**绝不提**任何"规范/指南文档"，原则要化作作者经验、团队惯例或社区共识。

常用参数（默认值）：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--n-genres` | 4 | 每个 skill 采几种体裁 |
| `--n-ideas` | 3 | 每个 (skill,体裁) 几个点子 → 几篇文档 |
| `--max-doc-tokens` | 2600 | 单篇上限 |
| `--temperature` | 0.8 | |
| `--prompt-version` | v1 | 用 `prompts/doc_ideas_<v>.md` + `doc_writer_<v>.md` |
| `--lang` | en | `zh` = 全文简体中文（保留 skill 名与 API 字段原文） |
| `--seed` | 17 | 体裁采样可复现 |

> ⚠️ **当前接线缺口**：`04_docs.sh` 写死的是 `--prompt-version v2`，而最新经验证的提示词是 **v4**
> （assertion-targeting + 去虚构统计 + 中文支持）。要用 v4 / 中文，请显式传 `--prompt-version v4 [--lang zh]`，
> 或改 `scripts/04_docs.sh`。提示词演进见 `prompts/DEBUG_LOG.md`。

**质量闸**（`quality.py`，`04_docs.sh` 会自动接着跑）逐条过滤后写 `docs_clean.jsonl`：

- **泄漏过滤**：语料严禁出现 Stage-2 SFT 轨迹格式 —— `<tool_call>`、`"arguments":`、`"tool_calls":`、
  `User:/Assistant:/System:`、`Action:/Observation:/Thought:`、以及合成残留标签 `<content>/<scratchpad>`。
- 占位符（`[Name]`/`[Link]`/`TODO` 等）、代码围栏过多、重复行过多 → 丢弃。
- 长度 200–1600 词；精确去重 + near-dup（6-gram shingle，Jaccard > 0.55）。

### Stage C — `src/train/build_corpus.py` + `train_midtrain.py`（`05_train.sh`）

**打包**：用 `Qwen/Qwen3.5-4B-Base` tokenizer 编码、文档间插 EOS、按 `--seq-len 4096` 切块、`uint32` memmap 落
`data/corpus/{train,val}.bin` + `meta.json`。`--replay general.jsonl --replay-ratio 0.10` 可混入回放语料
（**正式跑务必混回放**，纯 SSM 语料只适合冒烟，脚本会告警）。

**训练**：midtrain 低强度续训 —— lr 2e-5、cosine、warmup 50、1 epoch；
8×GPU × per_device 2 × grad_accum 8 × 4096 ≈ **512k tok/step**（`configs/train_qwen3p5_4b.yaml`）。
Qwen3.5 是混合线性注意力架构，未装 `flash-linear-attention` + `causal-conv1d` 时回退 torch 实现（smoke 已验证可跑），正式 8 卡跑建议先装这两个包提速。

---

## 5. 关键设计

- **合成模型**：`deepseek/deepseek-v4-pro`（OpenRouter）。reasoning 模型的思考 token 会吃 `max_tokens`，
  `client.py` 默认 `reasoning effort=low`；截断/空回 → 不缓存并以 `max_tokens×1.5` 重试。
  带**磁盘缓存**（prompt 变了自动失效）和**成本核算**（每次调用记进 `logs/api_calls.jsonl`）。
- **防术语回声**（v2 提示词核心修复）：写文档时喂给模型的是**无标签 digest**（不出现 S1–S5 字样），
  目标是"用自然语言多样重述"而非"复读规范条文"。
- **assertion-targeting**（v4，对齐 MSM）：每篇文档只聚焦少数要素的 principles，整套语料在 skill×体裁×要素上交叉覆盖。
- **防虚构**（v4）：禁止编造日期/作者名/引用/链接，禁止把臆造的工具输出或"测得的数字/百分比/样本量"当真实事实写
  （审计体裁尤其只能用定性量级，不能编精确计数）。
- **grounded spec**：S1/S4 关于行为/参数的断言必须来自 skill 文档，不得发明参数或能力；S2/S3/S5 允许通用工程判断补全文档没写的部分。

---

## 6. 数据 schema

**`data/skills.jsonl`**（解析产物，每行一个 skill）
`{id, name, description, kind: skill_md|api_tool, source, path, body, files}`

**`data/specs/specs.jsonl`**（Stage A）
`{skill_id, skill_name, kind, source, skill_summary, elements:{S1_..S5_: {text, principles[]}}, model, prompt_version, cost}`

**`data/docs/docs.jsonl`**（Stage B，未过闸）/ `docs_clean.jsonl`（过闸后）
`{doc_id, text, skill_id, skill_name, kind, genre, idea_name, idea, elements[], model, prompt_version, cost, n_words}`

**`data/corpus/`**（Stage C）`train.bin` / `val.bin`（uint32，shape `[n_blocks, seq_len]`）+ `meta.json`（token 统计）。

**`data/splits/`**（Stage D）`seen.txt` / `heldout.txt`（skill_id 列表）+ `confusable.jsonl`（易混对）+ `summary.json`。

**`data/sft/sft_{train,val}.jsonl`**（Stage D）`{messages:[system,user,assistant], skill_id, type: call|abstain, split}`（completion-only 训练，assistant 为工具调用或拒答，不含 spec 文本）。

**`data/evals/evals.jsonl`**（Stage D）`{id, etype: E1..E6, split, skill_id, messages, candidates, answer|should_call|required_args|tool_result, spec_digest}`。

---

## 7. 仓库结构

```
configs/        sources.yaml, train_qwen3p5_4b.yaml（8卡）, train_smoke.yaml, sft_qwen3p5_4b.yaml（SFT）
prompts/        skill2spec_v1.md, doc_ideas_v1..v4.md, doc_writer_v1..v4.md, doc_genres.yaml,
                sft_synth_v1.md, eval_gen_v1.md, eval_judge_v1.md, DEBUG_LOG.md
scripts/        00_env.sh ~ 10_eval.sh（薄封装，透传参数）
src/common.py   路径/IO/JSON 解析/标签抽取/OpenRouter key 加载
src/collect/    download.py（采集）, parse_skills.py（统一入库）
src/synth/      client.py（OpenRouter+缓存+核算）, gen_specs.py, gen_docs.py,
                quality.py（质量闸）, audit_docs.py / audit_grounding.py（接地审计）
src/train/      build_corpus.py（打包）, train_midtrain.py（续训）
src/exp/        split.py（切分）, build_sft.py（SFT数据）, sft_train.py（completion-only SFT）,
                build_evals.py（E1–E6 生成）, run_eval.py（跑分+判分）,
                tool_catalog.py / chat_format.py（SFT与评测共用的工具菜单/对话格式）
docs/           index.html（项目落地页，可发 GitHub Pages）
requirements.txt   运行依赖清单（版本锚定 living-lm）
ROADMAP.md EXPERIMENTS.md   下一步清单 / 实验协议
proposal.* survey.* STATUS_REPORT.* skill_rewrite_report_zh.*   方案/综述/状态/改写示例报告
```

**未纳入仓库**（`.gitignore`）：`data/`（4.4G 原始与中间产物）、`checkpoints/`（24G 权重）、`logs/`、`refs/`（第三方 MSM）。

---

## 8. 当前进度

- ✅ 采集 + 解析跑完：16,983 skills 已入 `data/skills.jsonl`。
- ✅ **试点闭环已通**：5-skill 的 spec、v1/v2 试点文档、debug 语料打包、Qwen3.5-4B 单卡 4 步 smoke 训练（`checkpoints/smoke/`）。
- ✅ 提示词迭代到 v4（assertion-targeting + 去虚构统计 + 中文），并产出改写示例报告 `skill_rewrite_report_zh.html`。
- ✅ **实验闭环代码已就绪**（Stage D，`src/exp/` + `scripts/06`~`10`，pilot 数据端到端跑通，已推 GitHub）。
- ⬜ **全量规模生成未跑**（`data/specs`、`data/docs`、`data/corpus` 仍为空）。
- ⬜ `04_docs.sh` 仍默认 v2，未切到 v4。
- ⬜ 8 卡正式 midtrain 未启动；Stage-2 tool-use SFT 另行；Stage D 各臂训练/评测待全量执行。

> 完整下一步清单见 [`ROADMAP.md`](ROADMAP.md)；实验执行协议（实验臂 / 切分 / E1–E6 / 消融 / 成功判据）见 [`EXPERIMENTS.md`](EXPERIMENTS.md)。

---

## 参考

Li, Price, Marks, Kutasov. *Model Spec Midtraining: Improving How Alignment Training Generalizes.*
[arXiv:2605.02087](https://arxiv.org/abs/2605.02087).
