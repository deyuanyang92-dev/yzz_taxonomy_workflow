# yzz `sra` 模块设计：类群 SRA metadata 总表（2026-10-27，修订 2）

## 1. 需求（用户原话归纳）

用户是分类学与系统演化学者，要快速知道某类群在 NCBI SRA 现有哪些资源（浅层 WGS、全基因组、转录组、Hi-C 等），减少手动打开文件、在 Excel 里整理的过程。

用户旧做法：
1. NCBI 网页搜类群 → 下载 SraRunInfo.csv（或 SRR 列表）；
2. `kingfisher annotate` 取 metadata；
3. 表里只有 TaxID，没有分类信息 → 自己整合 metadata + 分类阶元成系统总表（旧脚本 `one_step_organize_sra*`）；
4. 再筛选（旧脚本 `filter_sra_data*`）；
5. `kingfisher get` 下载。

新工具自动完成 1–4，输出可直接交给 kingfisher（或其他下载工具）的 run 清单。**不做下载**（用户决定：下载用现成工具）。

## 2. 输入

- 类群名：`python3 yzz.py sra all Polynoidae`（自动取 RunInfo，等同网页 Send to → RunInfo）
- SRR/ERR/DRR 列表：`python3 yzz.py sra all <项目名> --runs list.txt`
- 网页下载的 RunInfo：`python3 yzz.py sra all <项目名> --runinfo SraRunInfo.csv`

## 3. 步骤

| 步骤 | 做什么 | 对应旧做法 |
|---|---|---|
| 01_runinfo | 得到 NCBI RunInfo 表（原列名、原值）。类群名 → `txid<id>[Organism:exp]` 检索 + 分页取全；`--runs` → 按 `[accn]` 分批检索；`--runinfo` → 读入用户文件 | 网页下载 SraRunInfo.csv |
| 02_annotate | 照 kingfisher annotate 做法：efetch db=sra 完整 XML（EXPERIMENT_PACKAGE），取实验/研究标题、研究摘要、设计描述、提交单位、文献链接、**样本全部属性**（采集地、经纬度、日期、组织、凭证号…） | `kingfisher annotate --all-columns` |
| 03_taxonomy | TaxID → 门/纲/目/科/属/种（NCBI Taxonomy） | 旧 taxid→species_rank 脚本 |
| 04_table | 按 Run 合并 01–03；派生数据类型；输出 Excel 总表 | `one_step_organize_sra` + 手动 Excel |
| 05_select | 按参数筛选 → `run_list_<tag>.txt`（一行一个 run，直接给 `kingfisher get --run-identifiers-list`）+ 筛选表 | `filter_sra_data*` |

`all` 跑 01–05。每步只读上一步 TSV、只写自己的 TSV（yzz 约定），失败可单独重跑。

## 4. 数据原则

- RunInfo 原列名、原值不改；02 新增列用 kingfisher 同名字段（`experiment_title`、`study_title`、`study_abstract`…），样本属性用 XML 原 TAG 名。
- 派生列一律 `_derived` 后缀，并有 `category_rule_derived` 说明命中规则与数值。
- 不静默丢数据：检索条数与取回条数核对（db=sra 的 Count = 唯一 Experiment 数；Annelida 实测 13,799 = 13,799，对应 14,641 run）；NCBI 返回 `<ERROR>`/错误页 → 重试，仍失败报错非零退出；`--runs` 中查不到的 run 列出。
- 不硬编码 API key/邮箱：`config/ncbi.json` 或 `NCBI_EMAIL`/`NCBI_API_KEY`。

## 5. 数据类型（04_table 派生，阈值在 `modules/sra/rules.json`）

NCBI 没有"浅层"字段，按样本数据量推断。按顺序首个命中：

1. ~~WGS 且 LibrarySelection ∈ {PCR, RT-PCR} → `WGS_PCR_suspect`~~ **实施时撤销**（2026-10-27 Annelida 实测：1642 条 WGS+PCR run 多为 genome skimming / 基因组数据，PRJNA551036 是单样本医蛭基因组而非扩增子）。改为照常分类、QC 标 `WGS_selection_PCR`。
2. WGS 且 LibrarySource ∈ {METAGENOMIC, METATRANSCRIPTOMIC} → `WGS_metagenomic`
3. WGS 且 PacBio/Nanopore → `long_read_WGS`
4. WGS 短读长，样本总量 < 0.5 Gb → `low_data_WGS`
5. WGS 短读长，0.5–10 Gb → `shallow_WGS`
6. WGS 短读长，≥ 10 Gb → `deep_WGS`
7. RNA-Seq 且长读长 → `long_read_RNA`
8. 其余 → LibraryStrategy 原值（RNA-Seq、Hi-C、RAD-Seq、AMPLICON…）

样本总量 = 同一 BioSample（空则用 Run）、同 LibraryStrategy、同平台类型的 run 碱基数之和，不含宏基因组 run。0.5/10 Gb 为设计方初值（依据 Annelida 每样本 1–3 Gb 峰 251 个样本），可改。

## 6. Excel（`04_处理数据/sra/<Taxon>_SRA_<date>.xlsx`）

- `Summary`：一行一个 TaxID（含门–种），每个数据类型的样本数与 Gb。
- `Samples`：一行一个样本×数据类型，含标题、采集地、经纬度、凭证号、run 列表（挑选用）。
- 每类一张：`shallow_WGS`、`deep_WGS`、`long_read_WGS`、`RNA-Seq`、`Hi-C`、`Other`。
- `Runs`：全部列（RunInfo + annotate + 阶元 + 派生）。
- `QC`：WGS+PCR 标记、宏基因组、数据过少、BioProject 为空、查不到的 run、条数核对。
- `Query`：检索式、日期、条数、阈值。

## 7. 05_select 参数

`--type shallow_WGS,deep_WGS,RNA-Seq`（默认这三类）、`--platform`（默认不限）、`--layout PAIRED|SINGLE|ALL`（默认 PAIRED）、`--top 3`（每 TaxID×BioProject×类型取数据量最大的 3 个样本，带上样本全部 run）、`--per sample|run`（run = 旧脚本行为）、`--tag`。

## 8. 旧脚本问题的处理

| 旧问题 | 新做法 |
|---|---|
| 自由文本检索混入非目标（2025 数据 12,422 中 982 非 Annelida）；BioProject 绕路多出 26.7 万非目标、补回 0 条 | taxid 子树检索 |
| `--max_projects` 默认 50 静默截断 | 无截断 |
| API key 硬编码并打印（14 个脚本） | config/环境变量 |
| 失败被吞、空文件当成功 | 条数核对 + 重试 + 非零退出 |
| `concat(axis=1)` 按行号拼表错位 | 按 Run/TaxID merge，断言行数不变 |
| ete3 依赖、TaxID 浮点化 | NCBI Taxonomy 接口；TaxID 统一整数字符串 |
| 每组取前 3 个 run，同一样本多 run 挤占名额 | 默认按样本取 |

## 9. 不做

下载 fastq/sra；组装注释；WoRMS 有效名（另有 `yzz.py match`）；GUI。

## 10. 验收

- `python3 yzz.py sra all Polynoidae`：唯一 Experiment = 检索 Count（2026-10-27：495 / 525 run）；Excel 各表生成；`run_list_default.txt` 非空。
- `--runs <10 个 SRR>`、`--runinfo <网页 csv>` 两种输入跑通。
- `python3 yzz.py sra all Annelida` < 15 分钟；PRJNA1075478（Annelida Genome Skimming）归 `shallow_WGS`；WGS+PCR 均在 QC 标出。
- 离线单元测试全部 PASS。
