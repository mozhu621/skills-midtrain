# Roadmap / TODO

SSM 后续工作清单。当前状态：采集+解析已完成、试点闭环已通、提示词迭代到 v4；
**全量规模生成与正式训练尚未启动**。下面按优先级分四个阶段。

图例：`[ ]` 待办 · `[~]` 进行中 · `[x]` 已完成 · 🔴 阻塞项 / 关键路径 · 💸 有 API/算力成本

---

## P0 — 接线与小修（低成本，先做）

- [ ] **把 `scripts/04_docs.sh` 切到 v4 提示词** —— 当前写死 `--prompt-version v2`，
      最新经验证的是 v4（assertion-targeting + 去虚构统计 + 中文）。改默认 + 决定中英文（`--lang`）。
- [ ] **加 `requirements.txt` / `pyproject.toml`** —— 仓库目前无依赖清单，复现只能靠 `living-lm` 环境。
      至少固定 torch / transformers / numpy / pyyaml / tqdm / requests 版本。
- [ ] **小批量抽检 Stage A 质量** —— 跑 `03_specs.sh --limit 50`，人读 `data/specs/md/`，
      确认五要素接地、S3 近邻有意义、principles 可独立引用，再放量。
- [ ] （可选）**统一 git 作者邮箱** —— 历史里是占位邮箱，需要的话 rebase 改 author 后强推。

## P1 — 全量数据生成 💸

- [ ] 🔴 **全量 Stage A**：`03_specs.sh`（16,983 skills）。
  - [ ] 先估成本/时间（试点单份成本 × 规模），决定是否分 kind / 分批跑。
  - [ ] 监控 `specs_failed.jsonl` 失败率，对失败项重试（截断→提高 max-tokens）。
- [ ] 🔴 **全量 Stage B**：`04_docs.sh`（spec → 多体裁文档 + 质量闸）。
  - [ ] 跑后看 `quality.py` 统计：泄漏命中率、精确/近似去重率、长度分布。
  - [ ] 审计**体裁分布**与**要素覆盖**（S1–S5 是否被语料整体覆盖均衡）。
  - [ ] 抽样人读，确认无术语回声、无虚构统计、无 SFT 轨迹格式残留。
- [ ] **准备回放语料** —— `build_corpus.py --replay` 需要一份通用语料 jsonl。
      选源（如 FineWeb / Dolma 子集），目标混入比例 ~10%，避免 midtrain 灾难性遗忘。

## P2 — 训练 + 评测（核心假设验证）🔴💸

> 完整实验协议见 **[`EXPERIMENTS.md`](EXPERIMENTS.md)**（参照 MSM 范式设计：实验臂、数据切分、ID/OOD 评测、消融、超参、成功判据）。

- [ ] 🔴 **数据切分** —— 划出 seen / held-out skill 集（held-out 既不进中训也不进 SFT），固定 seed 落 `data/splits/`。这是测 OOD 泛化的前提。
- [ ] **环境**：装 `flash-linear-attention` + `causal-conv1d`（Qwen3.5 混合线性注意力，提速正式跑）。
- [ ] **正式 midtrain**：`NGPU=8 scripts/05_train.sh`（512k tok/step，lr 2e-5 cosine，1 epoch）。
- [ ] 🔴 **构造工具调用 SFT 数据** —— B0/A 两臂共用同一份，确保泛化差异只来自中训。
- [ ] 🔴 **跑实验臂**：B0(SFT-only) / B1(in-context) / A(SSM→SFT) / C(deliberative，可选)。
- [ ] 🔴 **skill-selection 评测** —— 目前**完全没有 eval**，最大缺口。按 EXPERIMENTS.md 的 E1–E6
      （选择 / 该不该调 / 易混辨析 / 调用正确性 / 调用后验证）用 inspect + LLM-judge 跑，对标 MSM 的 54%→7% 叙事。
- [ ] **消融** A1–A5（要素 / 具体性 / 体裁多样性 / assertion-targeting / 回放比例）复现 MSM 的两个泛化发现。

## P3 — 完善与扩展（可延后）

- [ ] **中文虚构检测** —— `audit_grounding.py` 现仅英文正则，`--lang zh` 产出的虚构（编造数字/案例）查不到。
- [ ] **spec grounding 审计** —— 量化每份 spec 的 principle 有多少能追溯到原始 skill 文档
      vs 模型推断补全（SSM 与 MSM 的最大结构差异：MSM 的 spec 是人写的、不准发明）。
- [ ] **消融** —— 体裁多样性、assertion-targeting、回放比例、spec 质量各自对下游泛化的贡献。
- [ ] **扩规模 / 换基座** —— 更多 skill 源、其他 base model 复现结论。
- [ ] **项目页上线** —— 把 `docs/index.html` 用 GitHub Pages 发布（Settings → Pages → main /docs）。

---

## 已完成

- [x] 采集 128 个 repo + 工具池 → 解析入库 `data/skills.jsonl`（16,983 skills）。
- [x] 五要素 Skill Spec 设计 + S3 TF-IDF 近邻注入（`gen_specs.py`）。
- [x] 两段式多体裁文档合成（16 种体裁，正式/非正式 spec 引用区分）。
- [x] 质量闸：SFT 轨迹泄漏过滤 + 去重（`quality.py`）。
- [x] 试点闭环：5-skill spec / v1·v2 文档 / 打包 / 单卡 4 步 smoke 训练。
- [x] 提示词迭代 v1→v4（防术语回声 → assertion-targeting → 去虚构 → 中文）。
- [x] 改写示例报告 `skill_rewrite_report_zh.html` + 完整 README。
