# yzz `sra` 模块设计：类群 SRA 资源盘点（2026-10-27）

## 1. 目的与背景

用户是分类学与系统演化学者。需要**快速知道某类群在 NCBI SRA 现有哪些原始测序资源**——浅层 WGS（genome skimming）、深度全基因组、长读长、转录组、Hi-C、RAD、扩增子等——以便选材做研究（如系统基因组、线粒体组装）。

做法（用户定）：**以 NCBI SRA RunInfo 总表为底**（信息最全、metadata 最多），原样保留，再在其上加工出派生列与汇总表。NCBI 没有"浅层"这一字段，浅层/深度是后加工推断。

现有资源：用户 2023–2025 写的约 63 个脚本（已整理在 `/mnt/p/多鳞虫科-张燕杰-20261009/SRA脚本整理_20261027/`，见其 `README_SRA流程.md`）。本模块把这些脚本的思路收拢为一个 yzz 模块，修掉已知问题；老脚本只作参考，不再维护。

## 2. 实测依据（2026-10-27，驱动设计的事实）

| 事实 | 证据 |
|---|---|
| 直接 `txid<id>[Organism:exp]` 检索不缺目标类群 run；BioProject 绕路补回 0 条目标 run | Polynoidae：直接 525 run，绕路多 434 条全为非目标；Nereididae：直接 1553，绕路多 3649 全非目标 |
| 用户 2025-03 的 BioProject 绕路数据：272,516 run，多出的 267,330 条中 Annelida = 0（SARS-CoV-2 72,658、Salmonella 37,943、Homo sapiens 33,861…） | `/mnt/n/Onedrive/Annelida_Lab/NCBI_data/Annelida-summary/anne1/combined_project_metadata.csv` vs `anne/sra_annelida_metadata.csv` |
| 自由文本 `-query "annelida"` 混入非目标：12,422 run 中 982 条非 Annelida | 同上 `anne/` 文件 |
| BioProject 绕路反而会漏：Polynoidae 51 条 2026 年 DRR run 的 BioProject 字段为空 | runinfo 实测 |
| E-utilities history server 分页（每页 500）可取全：Annelida 14,641 run / 2 分 42 秒（无 API key） | 实测 |
| ENA 与 NCBI 不一致：ENA 缺新分类单元（Polynoidae 218 run，PRJNA1044042），但偶有 NCBI 无的 ERR（Nereididae 6 条） | ENA portal `tax_tree()` 实测 |
| 标为 WGS 但实为 PCR 扩增：PRJNA551036 2304 run，单物种，LibrarySelection=PCR，中位 0.08 Gb | Annelida runinfo |
| Annelida Illumina WGS 每 BioSample 总量分布：1–3 Gb 有 251 个样本（明显峰）；5–10 Gb 184；10–50 Gb 248；>50 Gb 107 | Annelida runinfo |
| Annelida LibraryStrategy：RNA-Seq 5095、WGS 3849、AMPLICON 2461、RAD-Seq 2134、OTHER 263、Hi-C 222、ATAC-seq 214、WGA 184… | Annelida runinfo |

结论：**不再用 BioProject 绕路，也不用自由文本检索**；按 taxid 子树直接检索 + 分页 + 条数校验。

## 3. 目标 / 非目标 / 反目标

**目标**
- 一条命令：`python3 yzz.py sra all <Taxon>` 产出该类群 SRA 资源 Excel 总表。
- 保留 NCBI RunInfo 全部原始列，原值不改。
- 补 BioSample 属性（采集地、经纬度、日期、组织、凭证号、isolate 等）——分类学最需要的 metadata。
- 补分类阶元（门/纲/目/科/属/种）。
- 派生数据类别（浅层 / 深度 / 长读长 / 数据过少 / WGS-PCR 等），每行可追溯规则。
- 物种级汇总：每物种每类别的样本数、run 数、Gb。
- 按用户旧规则筛选出下载清单；可选调用 kingfisher 下载。

**非目标（本期不做）**
- 组装、注释、BUSCO（归全基因组工作流）。
- WoRMS 有效名匹配（已有 `python3 yzz.py match`，可在输出上另跑；Excel 留 `ScientificName` 原值）。
- GUI。

**反目标（即使能跑也算失败）**
- 修改或"纠正" NCBI 原值。
- 静默丢数据：检索条数与取回条数不符、批次失败、BioSample 取不到，必须在终端摘要和 QC 表中报告。
- 把推断类别写得像 NCBI 原生字段（派生列必须带 `_derived` 后缀并有规则列）。
- 硬编码 API key / 邮箱 / 个人路径。

## 4. 放在哪、怎么组织（遵循 yzz 约定）

- 位置：`/mnt/p/yzz-分类工作流/modules/sra/`，遵循仓库 README "新增模块的约定"：`NN_step.py <Taxon>`；只读上一步 TSV、只写自己的 TSV；`common.data_dir(taxon,"sra")` / `report_dir(...)`；结束 `common.summary()` ≤5 行。
- 文档：`modules/sra/README.md`（步骤表）、`modules/sra/REQUIREMENTS.md`（需求+状态）、skill `~/.claude/skills/yzz-sra/SKILL.md`。
- NCBI 身份：与 genbank 模块相同，`config/ncbi.json` 或 `NCBI_EMAIL` / `NCBI_API_KEY`；有 key 10 次/秒，无 key 3 次/秒。
- 网络：只用 HTTP E-utilities（本机无 edirect），指数退避重试。
- 回归测试：`modules/sra/tests/`，离线单元测试用固定小样本（仓库内 fixture）；联网检查用 Polynoidae（runinfo ≥525 run、0 条 BioProject 绕路差异不需复测）。

## 5. 步骤

| 步骤 | 输入 → 输出 | 说明 |
|---|---|---|
| 01_runinfo | 类群名 → `runinfo.tsv`、`manifest.json` | 类群名 → taxid（taxonomy esearch；多个/零个命中时报错列出候选）；`txid<id>[Organism:exp]` esearch usehistory → efetch rettype=runinfo 分页；去掉重复表头行；按 Run 去重；校验不变式：**去重后 Experiment 数 = esearch Count**（db=sra 的 Count 与分页均按 experiment 计；Annelida 实测 Count 13,799 = 唯一 Experiment 13,799，对应 14,641 run），run 数 ≥ 该数；不符写 manifest、进 QC、非零退出。`--query` 追加 Entrez 子句；`--since auto` 增量（可选，见 §7）。`--ena` 可选：ENA `tax_tree()` 对比，差异写 `ena_diff.tsv`（只报告，不并入）。 |
| 02_details | runinfo.tsv → `experiment.tsv`、`bioproject.tsv` | RunInfo 无标题/摘要（旧流程靠 kingfisher annotate 取得）。用 esummary db=sra（ExpXml：experiment title、study title、library name 等）分批 ≈500 UID；esummary db=bioproject 取项目 title/description。原值。用于识别 skimming / 线粒体 / 转录组项目。 |
| 03_biosample | runinfo.tsv → `biosample.tsv` | 去重 BioSample 号，efetch db=biosample XML 分批（≈200/批），解析全部 `<Attribute>` 为宽表（列名用 `harmonized_name`，无则 `attribute_name`），原值。取不到的 BioSample 列入 QC。 |
| 04_taxonomy | runinfo.tsv → `taxonomy.tsv` | 去重 TaxID，efetch db=taxonomy 取 LineageEx → phylum/class/order/family/genus/species 列（缺失留空）。不依赖 ete3 本地库（本机 ete3 在 Python 3.13 下因 `cgi` 模块缺失无法导入）。 |
| 05_classify | 01–04 → `runs_annotated.tsv`、`samples.tsv`、`species_summary.tsv` | 合并原始列 + BioSample + 阶元；派生列（§6）；样本级聚合（按 BioSample + 类别）；物种级汇总。 |
| 06_export | 05 → `04_处理数据/sra/<Taxon>_SRA_<date>.xlsx` | 工作表见 §8。 |
| 07_select | samples/runs → `selected_runs.tsv`、`run_list_<tag>.txt` | 用户旧 filter 规则：`--category`（默认 shallow_WGS,deep_WGS,RNA-Seq 可多选）、`--platform`、`--layout`（默认 PAIRED）、`--top`（默认每 TaxID×BioProject×类别 取数据量最大的 3 个样本；选中样本带上其全部 run；单位改为样本而非 run，见 §7）。`--platform` 默认：short 类别取全部 short 平台、long 类别取全部 long 平台（不再限 ILLUMINA/PACBIO_SMRT）。清单写出预计总 Gb，摘要中报告。 |
| 08_download | run_list → fastq.gz | 调 kingfisher get（`-m` 方法列表、`--check-md5sums`、`-f fastq.gz`、并行数可设）；已存在且完整则跳过；失败列表写 `download_failed.txt`，终端明确报告。kingfisher 不存在时提示安装（`doctor` 子命令检查 kingfisher/fasterq-dump）。 |

## 6. 派生列规则（初版，阈值放 `modules/sra/rules.json` 可改）

原值列不动。新增：

- `sample_total_Gb_derived`：同 BioSample、同 LibraryStrategy、同平台类型的 run `bases` 之和 /1e9；**先按 run 判规则 1–2，命中的 run 不计入总量**，阈值用的 Gb 与 Samples 表报告的 Gb 一致。BioSample 为空时以 Run 自身为样本键（Annelida 实测 BioSample 空值 0，但须防御）。
- `platform_type_derived`：short（ILLUMINA/BGISEQ/DNBSEQ/ION_TORRENT/ABI_SOLID/LS454）/ long（PACBIO_SMRT/OXFORD_NANOPORE）/ other（CAPILLARY 等）。
- `category_derived`，按顺序首个命中：
  1. `LibraryStrategy==WGS` 且 `LibrarySelection` ∈ {PCR, RT-PCR}（大小写不敏感）→ `WGS_PCR_suspect`
  2. `LibraryStrategy==WGS` 且 `LibrarySource` ∈ {METAGENOMIC, METATRANSCRIPTOMIC} → `WGS_metagenomic`
  3. `LibraryStrategy==WGS` 且 long → `long_read_WGS`
  4. `LibraryStrategy==WGS` 且 short 且 `sample_total_Gb` < 0.5 → `low_data_WGS`
  5. `LibraryStrategy==WGS` 且 short 且 0.5 ≤ Gb < 10 → `shallow_WGS`
  6. `LibraryStrategy==WGS` 且 short 且 Gb ≥ 10 → `deep_WGS`
  7. `LibraryStrategy==RNA-Seq` 且 long → `long_read_RNA`（Iso-Seq 等）
  8. 其余 → `LibraryStrategy` 原值（RNA-Seq、Hi-C、RAD-Seq、AMPLICON、WGA、ATAC-seq…）
- `category_rule_derived`：命中规则的可读说明，含实际数值，如 `WGS & RANDOM & short & 1.84 Gb in [0.5,10) -> shallow_WGS`。
- 阈值 0.5 / 10 Gb 是**设计方（Claude）定的初值**，依据 Annelida 样本量分布（1–3 Gb 峰）及 genome skimming 常见 1–5× 覆盖度（未逐篇核对文献）；用户可在 rules.json 改。
- 可选（`--coverage`，非默认）：若同种或同属有 NCBI 基因组组装，取其大小算 `est_coverage_derived`。

## 6b. 物种键

分组键 = `TaxID` + `ScientificName`（NCBI 原值），另附 `rank_derived`（species / genus / subspecies / no rank…）。未定种（sp.）、亚种各自成组，不塌成一组，不被 `--top` 丢掉。Summary 的"一行一物种"即一行一个 TaxID。（设计方决定）

## 7. 对用户旧脚本问题的处理（优化点）

| 旧问题 | 新做法 |
|---|---|
| BioProject 绕路 / 自由文本检索混入大量非目标、漏 BioProject 为空的 run | taxid 子树直接检索 + 条数校验（§2） |
| `--max_projects` 默认 50 静默截断 | 无截断；全部分页 |
| API key 硬编码并打印（14 个脚本） | config/env；日志不打印 key |
| `executor.map` 结果不消费，失败被吞；空文件当成功 | 每批校验行数；失败重试；仍失败写 QC 并非零退出 |
| `one_step_organize_sra.py` concat(axis=1) 按行号拼表错位 | 一律按键（Run / BioSample / TaxID）merge，merge 后断言行数不变 |
| ete3 依赖、taxid 读成浮点（6340.0）后整列空 | E-utilities taxonomy；TaxID 统一按字符串整数处理 |
| filter 按 run 取前 3，同一样本多 run 会挤占名额 | 默认按样本（BioSample）取前 N，`--per run` 可切回旧行为 |
| kingfisher 多版本参数不一致（`-m` 写法、`--run-identifiers-file`） | 单一封装，参数以本机 `kingfisher get -h` 为准（实现时核对） |
| 版本 v1…v5.6 并存 | 一个模块，git 管理 |

## 8. Excel 输出（06_export）

- `Summary`：一行一个物种 × 列为各 `category_derived`（样本数 / Gb），加阶元列；用户可筛选"有浅层的物种"等。
- `Samples`：一行一个 BioSample × 类别（挑样本下载用），含 BioSample 关键属性（geo_loc_name、lat_lon、collection_date、tissue、specimen_voucher、isolate）。
- 每个主要类别一张表：`shallow_WGS`、`deep_WGS`、`long_read_WGS`、`RNA-Seq`、`Hi-C`、`RAD-Seq`、`AMPLICON`、`Other`（样本行）。
- `Runs`：全部 run，NCBI 原始列 + 派生列（派生列表头标色区分）。
- `BioSample`：属性宽表原值。
- `QC`：WGS_PCR_suspect、WGS_metagenomic、low_data_WGS、BioProject 为空、BioSample 取不到、TaxID 不在目标子树（理论上应为 0）、条数校验、ENA 差异（若 `--ena`）。
- `Query`：检索式、taxid、日期、条数、rules.json 内容。
- Excel 表头英文（yzz 规则：分类学内容一律英文）；README/摘要中文。

## 9. 已由设计方决定、实现者可调整的事项

- 一行一物种与一行一样本**都输出**（Summary + Samples），因用户未选择。
- 08_download 不在 `all` 中默认运行（下载量可能数 TB），需显式 `python3 yzz.py sra 08 <Taxon>`。
- 07_select 在 `all` 中运行，默认参数产出清单但不下载。
- 增量 `--since auto`：可放第二期；第一期每次全量重取（Annelida 约 3 分钟）。
- 缓存：01–04 的原始响应可缓存到 `cache/sra/`，按需。

- `yzz.py` 可做最小改动：模块可声明 `all` 排除的步骤（08_download）及 `doctor` 入口；单步参数在 `all` 时只转给认识它的步骤（或各步 `parse_known_args` 忽略未知参数，与 genbank 现做法一致）。（设计方决定）
- kingfisher 本机未装：08 用假 kingfisher（stub 脚本）测试。

## 10. 验收

- `python3 yzz.py sra all Polynoidae` 跑通；唯一 Experiment 数 = esearch Count（2026-10-27 实测 495 / 525 run，随时间增长）；Excel 各表非空；QC 中 BioProject 为空 ≥51（2026-10-27 实测值）。
- `python3 yzz.py sra all Annelida` 跑通，<15 分钟（无 key）；PRJNA551036 的 2304 run 全部归 `WGS_PCR_suspect`。
- 离线单元测试：派生规则逐条、merge 行数守恒、重复表头去除、TaxID 浮点字符串处理。
- 中文 README 通过 `python3 yzz.py zh check`。
