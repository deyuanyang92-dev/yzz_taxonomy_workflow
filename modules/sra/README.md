# sra 模块

一条命令得到某类群在 NCBI SRA 的**系统总表**：RunInfo（原样）+ 实验/研究标题与样本属性（仿 `kingfisher annotate`）+ 门–种 + 数据类型（浅层 WGS、深度 WGS、长读长、转录组、Hi-C…），输出 Excel 和可直接交给 kingfisher 的 run 清单。**本模块不下载 fastq/sra**，下载用 kingfisher 等现成工具。需求见 [REQUIREMENTS.md](REQUIREMENTS.md)，设计见 `docs/superpowers/specs/2026-10-27-sra-module-design.md`。

```bash
python3 yzz.py sra all Polynoidae                              # 类群名: 自动取 RunInfo (= 网页 Send to → RunInfo)
python3 yzz.py sra all Polynoidae --query 'WGS[Strategy]'      # 追加 Entrez 子句
python3 yzz.py sra all 我的项目 --runs list.txt                 # SRR/ERR/DRR 列表, 一行一个
python3 yzz.py sra all 我的项目 --runinfo SraRunInfo.csv        # 网页下载的 RunInfo
python3 yzz.py sra 05 Polynoidae --type RNA-Seq --top 1 --tag rna   # 换条件重新筛选 (不必重跑 01–04)
kingfisher get --run-identifiers-list projects/Polynoidae/02_原始数据/sra/run_list_default.txt -m ena-ftp aws-http prefetch -f fastq.gz
```

| 步骤 | 输入 → 输出 | 说明 |
|---|---|---|
| 01_runinfo | 类群名 / `--runs` / `--runinfo` → `runinfo.tsv`、`manifest.json`、`runs_not_found.txt` | 类群 = `txid<id>[Organism:exp]`（含全部下级），history 分页取全；核对 唯一 Experiment 数 = 检索条数，不符退出码 1；同名类群列出候选，用 `--taxid` 指定；超过 `--max-experiments`（默认 200000）先停 |
| 02_annotate | runinfo → `annotate.tsv`、`annotate_missing.txt` | efetch db=sra 完整 XML：experiment_title、design_description、study_title、study_abstract、study_links、提交单位、样本全部属性（geo_loc_name、lat_lon、collection_date、specimen_voucher、tissue…，列名 = XML 原 TAG）；不取联系人姓名/邮箱 |
| 03_taxonomy | runinfo → `taxonomy.tsv` | TaxID → phylum/class/order/family/genus/species（NCBI Taxonomy，含已合并旧 taxid） |
| 04_table | 01–03 → `table.tsv`、`samples.tsv`、`species_summary.tsv`、`04_处理数据/sra/<Taxon>_SRA_<date>.xlsx` | 按 Run / TaxID 合并（行数不变）；派生数据类型；Excel：Summary（一行一个 TaxID）/ Samples（一行一个样本×类型）/ shallow_WGS / deep_WGS / long_read_WGS / RNA-Seq / Hi-C / Other / Runs（全部列）/ QC / Query |
| 05_select | samples → `selected_<tag>.tsv`、`run_list_<tag>.txt` | 每 TaxID×BioProject×类型 取数据量最大的 `--top` 个样本，带上样本全部 run；`--type`、`--platform`、`--layout PAIRED\|SINGLE\|ALL`、`--per run`（旧脚本行为） |

## 数据类型（`category_derived`，阈值在 `rules.json`）

NCBI 没有"浅层"字段，按样本数据量推断；原列不改，派生列都带 `_derived`，`category_rule_derived` 写明命中规则和数值。按顺序首个命中：

1. WGS + LibrarySource METAGENOMIC/METATRANSCRIPTOMIC → `WGS_metagenomic`
2. WGS + PacBio/Nanopore → `long_read_WGS`
3. WGS 短读长，样本总量 < 0.5 Gb → `low_data_WGS`；0.5–10 Gb → `shallow_WGS`；≥ 10 Gb → `deep_WGS`
4. RNA-Seq + 长读长 → `long_read_RNA`
5. 其余 = LibraryStrategy 原值（RNA-Seq、Hi-C、RAD-Seq、AMPLICON…）

样本 = BioSample（空则 Run）；样本总量 = 同样本、同策略、同平台类型的 run 碱基和，不含宏基因组 run。

LibrarySelection=PCR 的 WGS **不排除**，照常按数据量分类，只在 QC 表标 `WGS_selection_PCR`：Annelida 实测 1642 条这类 run 多为 genome skimming / 基因组数据（PRJNA1075478 "Annelida Genome Skimming"、PRJNA551036 医蛭基因组 2304 run 单样本等）。

## 为什么不按 BioProject 绕路（2026-10-27 实测）

- Polynoidae / Nereididae：按 taxid 直接检索不缺目标 run；BioProject 绕路补回 0 条，多出 434 / 3649 条全是非目标物种。
- 用户 2025-03 的绕路数据 272,516 run，多出的 267,330 条中环节动物 0 条（新冠病毒、沙门氏菌、人类…）；自由文本 `annelida` 检索 12,422 条中 982 条非环节动物。
- 绕路反而会漏：Polynoidae 有 51 条 2026 年 DRR run 的 BioProject 为空。

## 其他

- NCBI 身份（可选，有 key 快 3 倍）：`config/ncbi.json` 或 `NCBI_EMAIL` / `NCBI_API_KEY`。
- 测试：`python3 -m pytest -q modules/sra/tests`（离线）；`python3 yzz.py sra all Polynoidae && python3 modules/sra/tests/check_polynoidae.py`（联网）。
- 用时（无 key）：Polynoidae 525 run 约 1 分钟；Annelida 14,641 run 约 11.5 分钟。
