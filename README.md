# Skill Spec Midtraining (SSM)

把 Anthropic **MSM**（Model Spec Midtraining，"先懂规范、再学行为"）的配方迁移到
skill/tool 域：对每个 skill 先生成五要素 **Skill Spec**，再合成多体裁"讨论该
spec 的文档"语料，midtrain 基座模型，之后接标准 tool-use SFT（Stage 2，另行）。

母文档：`proposal.html`（方案）、`survey.html`（综述）。MSM 官方配方参考：`refs/msm/`。

## 五要素 Skill Spec

| 要素 | 含义 |
|---|---|
| S1 capability_scope | 能做什么、边界在哪 |
| S2 when_not_to_use | 何时不该用 |
| S3 contrastive_disambiguation | 与相似 skill 怎么选（TF-IDF 近邻注入） |
| S4 failure_modes | 典型失败方式 |
| S5 post_call_verification | 调用后如何验证 |

## 流水线

```
configs/sources.yaml ──01──▶ data/raw/            (129 repos + 网站收割 + Seal-Tools)
                      ──02──▶ data/skills.jsonl    (16,983 skills: 12,907 skill_md + 4,076 api_tool)
                      ──03──▶ data/specs/specs.jsonl        (Stage A: skill → Spec)
                      ──04──▶ data/docs/docs_clean.jsonl    (Stage B: Spec → 多体裁文档 → 质量闸)
                      ──05──▶ data/corpus/{train,val}.bin → checkpoints/  (打包 + midtrain)
```

```sh
scripts/01_download.sh                 # 下载源（已跑完）
scripts/02_parse.sh                    # 解析入库（已跑完）
scripts/03_specs.sh  --limit 100       # Spec 生成（OPENROUTER_API_KEY 自动从 ~/.bashrc 解析）
scripts/04_docs.sh                     # 文档合成 + quality.py 过闸
scripts/05_train.sh  --smoke           # 打包 + 单卡 4 步冒烟
NGPU=8 scripts/05_train.sh             # 8 卡正式 midtrain（512k tok/step）
```

Python 环境：`/raid/longhorn/yuhao/envs/living-lm/bin/python`（torch 2.7 + flash-attn 2.8 + transformers 5.8）。

## 关键设计

- **合成模型**：`deepseek/deepseek-v4-pro`（OpenRouter）。reasoning 模型思考 token
  烧 max_tokens —— client 默认 `reasoning effort=low`，截断/空回 → 不缓存、
  `max_tokens×1.5` 重试（`src/synth/client.py`，磁盘缓存 + 成本核算）。
- **防泄漏**：midtraining 语料严禁 SFT 轨迹格式（`<tool_call>`、`"arguments":`、
  `User:/Assistant:`、`Action:/Observation:` 等），prompt 端禁 + `quality.py` 正则闸双保险。
- **防术语回声**（v2 prompt 核心修复，见 `prompts/DEBUG_LOG.md`）：写作 prompt 用
  无标签 digest（不出现 S1–S5），spec 提及按体裁条件化（formal/informal rule），
  目标是自然语言多样重述而非引用规范。
- **体裁目录**：`prompts/doc_genres.yaml` 16 种（tutorial、slack debate、postmortem、
  audit report …），带权重采样与要素偏置。
- **训练**：Qwen3.5-4B-Base 续训；uint32 memmap 打包（seq 4096，文档间 EOS）；
  lr 2e-5 cosine；`--replay` 可混回放语料（正式跑建议 10%）。注意 Qwen3.5 为
  混合线性注意力架构——未装 `flash-linear-attention`+`causal-conv1d` 时回退
  torch 实现（smoke 已验证可跑）；正式 8 卡跑建议先装这两个包提速。

## 目录

```
configs/        sources.yaml, train_qwen3p5_4b.yaml
prompts/        skill2spec_v1.md, doc_ideas_v2.md, doc_writer_v2.md, doc_genres.yaml, DEBUG_LOG.md
src/collect/    download.py, parse_skills.py
src/synth/      client.py, gen_specs.py, gen_docs.py, quality.py
src/train/      build_corpus.py, train_midtrain.py
data/debug/     试点产物（5 skills 的 spec 与 v1/v2 docs）
logs/           api_calls.jsonl（每次 API 调用的成本/用量）
```
