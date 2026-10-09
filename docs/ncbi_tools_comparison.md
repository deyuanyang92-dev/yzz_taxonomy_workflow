# NCBI/GenBank 按类群下载与多基因整理工具对比（g2t v0.01 vs 同类工具）

> 调研日期：2026-10-08。所有"最后提交日期 / star 数"取自 GitHub API 当日返回值；"引用文献"仅写在仓库 README 或期刊/Crossref 页面实际看到的。
> 凡标 `[推测]` 为推断，标"未核实"为未能打开或确证。
> 结构：0 基线 / 1 wpwupingwp 仓库（OGU 等）/ 2 其他工具 / 3 对比总表 / 4 g2t 可借鉴做法 / 5 未核实项。

## 0. 我们的工具（g2t v0.01）基线

来源：本地 `vendor/gb2taxonomy/README.md`、`src/g2t/download.py`（仓库 https://github.com/deyuanyang92-dev/gb2taxonomy）。

- 下载：`txid{taxid}[Organism:exp]` + 默认排除 WGS / mRNA（`NOT biomol_mrna[PROP]`）/ RefSeq model（`NOT srcdb_refseq_model[PROP]`）；`--mito`、`--mitogenome`（`mitogenome[Title]` + 10000:30000[SLEN]）、`--gene`、`--minlen/--maxlen`、`--query`；esearch(usehistory) -> efetch rettype=acc 取 accession 列表（每页 5000）-> 每 200 个 accession 一批 `gbwithparts` 取 GenBank，逐批核对记录数、指数退避重试、重跑跳过已完成批次，写 `accessions.tsv` + `manifest.json`。
- 整理：按 DEFINITION 关键词归类 13 种基因类型 -> `organism + voucher` 建标本键 -> 基于证据（同文献/日期/坐标/采集人）合并凭证号变体（step 3b）-> 标本 x 基因矩阵（只给 accession，不切序列）。
- 已知限制（README "Limitations"）：基因类型按整条记录的 DEFINITION 判定；不切序列；仅 13 种基因类型；名称不校正；仅 nuccore。

---

## 1. wpwupingwp（Ping Wu）的仓库

### 1.1 仓库普查结果

GitHub API `https://api.github.com/users/wpwupingwp/repos?per_page=100` 返回 40 个公开仓库（与用户主页 `public_repos=40` 一致，故无遗漏）。逐个看过名称/描述/文件树后，与"NCBI/GenBank 下载、按基因提取、条形码、organelle"相关的如下：

| 仓库 | star | 最后推送 | 与本主题的关系 |
|---|---|---|---|
| **OGU**（https://github.com/wpwupingwp/OGU） | 25 | 2026-05-18 | 主力：GenBank 下载 + 按注释切段 + 评估 + 引物设计。**即旧 BarcodeFinder**（见下） |
| taxon_tools（https://github.com/wpwupingwp/taxon_tools） | 0 | 2026-03-07 | README 称"handle taxon name based on NCBI Taxonomy"；含 aa（Accurate Annotation，2016 起，叶绿体）旧代码、sqlite 序列库、GBIF 查询 |
| rename（https://github.com/wpwupingwp/rename） | 4 | 2026-02-21 | 早期脚本集：`gb2fasta.py`、`gene_rename.py`、`large_query_with_id_list.py`（带 `-redo` 续传）、`uniq.py` |
| OldBarcodeFinder（https://github.com/wpwupingwp/OldBarcodeFinder） | 2 | 2017-05-10 | 旧 BarcodeFinder 单文件版（BLAST 找单拷贝条形码），不含 NCBI 下载 |
| novowrap（https://github.com/wpwupingwp/novowrap） | 15 | 2024-05-21 | 叶绿体基因组组装与验证；README 提到可自动从 NCBI 取参考序列，但不是批量下载/整理工具（仅读了 README） |
| python / dissertation / divide / filter / tree / tree_crawler / treehub 等 | - | - | 与主题无关或仅为个人脚本（`dissertation` 内含 rename 同款 gb2fasta.py 副本） |

**"专门处理 NCBI 的仓库"的结论**：用户记得的 BarcodeFinder 现在叫 OGU。证据：`https://api.github.com/repos/wpwupingwp/BarcodeFinder` 返回 301 指向 `repositories/111626171`，而 `repositories/111626171` 的 full_name 是 `wpwupingwp/OGU`，OGU 创建于 2017-11-22。OGU 的 `old-README.md` 与 TODO 仍在仓库中。（OldBarcodeFinder 是 2016-17 年另一个更早的单文件原型。）

### 1.2 OGU（Organelle Genome Utilities，原 BarcodeFinder）

- **仓库**：https://github.com/wpwupingwp/OGU ；star 25，fork 1，open issues 2；许可 AGPL-3.0；最近提交 2026-05-18（"update db"、"now support python 3.14"）；最新 release v2.1.0（2026-05-18），v2.0.0（2025-01-13）；PyPI 包 `OGU`。
- **论文（README 中给出的 BibTeX；DOI 经 Crossref API 核实标题/卷期一致）**：Wu P, Xue N, Yang J, Zhang Q, Sun Y, Zhang W. *OGU: A Toolbox for Better Utilising Organelle Genomic Data.* Molecular Ecology Resources 25(3): e14044. doi:10.1111/1755-0998.14044。Crossref 记录的在线发表日期为 2024-11-11。
- **用途**：围绕细胞器基因组（叶绿体/线粒体）的四模块工具箱：数据收集（gb2fasta）、变异评估（evaluate）、通用引物设计（primer）、跨类群可视化（visualize）。与我们相关的是 **gb2fasta 模块**。
- **依赖**：Python >= 3.9；biopython、matplotlib、coloredlogs、numpy、primer3-py；MAFFT、IQ-TREE、BLAST（首次运行自动下载）。有 Tk GUI（`ui.py`/`ui.tcl`）、CLI 与便携包。

**核心机制（读 `src/OGU/gb2fasta.py`、`utils.py` 所见）**

1. **Entrez query 构造**（`get_query_string`）：把选项拼成 `AND` 连接的子句：`{taxon}[organism]`（纯数字则加 `txid` 前缀；代码中未显式写 `:exp`/`:noexp`）、`{gene}[gene]`、`mitochondrion[filter]` / `(plastid[filter] OR chloroplast[filter])`、`refseq[filter]` / `NOT refseq[filter]`、`("min"[SLEN] : "max"[SLEN])`（默认 100–10000 bp）、`biomol_genomic[PROP]`/`biomol_mrna[PROP]`、`[PDAT]` 日期范围、`-exclude` 以 `NOT (...)` 附加，另有 `-query` 自由文本。**没有"排除 WGS/mRNA"的默认**。
2. **下载与分批**（`download`）：`esearch(db=nuccore, usehistory='y')` -> 以 WebEnv 每页 1000 取 accession 列表（`rettype='acc'`）-> 再按每 100 个 accession 做 `efetch(rettype='gb')` 追加写入单个 `.gb` 文件。失败时 `sleep(1)` 重试，重试计数器是全局累计的，超 10 次即中止。**输出文件以 `'w'` 打开，无断点续传、无逐批校验记录数**；开关 `-count` 可限制总数。（`rename` 仓库里的旧脚本 `large_query_with_id_list.py` 有 `-redo <accession>` 手动续传，README 明说"不检查输出，需自行验证"。）
3. **基因识别/切序列**（`divide`、`get_feature_name`、`write_seq`）：**按 GenBank feature 坐标切序列**。只处理 feature 类型 `gene/CDS/tRNA/rRNA/misc_feature/misc_RNA/D-loop`，名称取 `/gene` -> `/product` -> `/locus_tag` -> `/note`，用 Biopython `feature.extract(whole_seq)` 取序列（自动处理 `join()` 与链向），写成 `{feature.type}-{name}.fasta`。**自动派生基因间区（IGS/spacer）和内含子序列**（`get_spacer`、`get_intron`；可选 `-allow_mosaic_spacer`、`-allow_repeat`、`-allow_invert_repeat`）；`-expand N` 向两侧延伸以便引物设计；`-max_gene_len`（默认 20000）跳过过长 feature。
4. **名称归一**（`-rename`，`utils.gene_rename`）：正则规则。tRNA 统一成 `trn{氨基酸}_{反密码子}`（用 Biopython 按密码子表翻译反密码子，叶绿体表 11、线粒体表 2）；rRNA 统一成 `rrn{数字}`；线粒体基因：`coi->COX1`、`cob->CYTB`、`nadh?N->nadN`、`atp(ase)?N->ATPN` 等；叶绿体其他基因按"字母+后缀大写"通用规则。**是启发式的（作者自己在 docstring 写"May be dangerous"）**。
5. **rRNA / ITS**：feature 类型含 `rRNA`，因此带注释的 18S/5.8S/28S 可各自切出；`misc_feature` 含 "internal transcribed spacer" 时意图命名为 `ITS`（并在 ID 里用 `ITS` 作文件名）。[推测] 读码时发现 `get_feature_name` 里 ITS 改名后紧接着被 `new_name = utils.safe_path(name)` 覆盖，实际效果需运行验证，未验证。**依赖提交者给了 feature 注释；无注释的记录不能切。**
6. **线粒体基因组**：`-og mt` 过滤 `mitochondrion[filter]`；若指定了 organelle 类型，整条记录按 `{og}_genome.fasta` 写出（整条基因组），同时 `divide` 把各基因/tRNA/rRNA 切出到 `Divide/` 目录。即**线粒体基因组被按注释拆分为各基因**。
7. **标本/凭证号**：ID 为 `name|kingdom|phylum|class|order|family|genus|species|accession|specimen|type`，其中 specimen = `/specimen_voucher` 与 `/isolate`（仅取第一个 feature 即 source）拼接。**只作标签，不做凭证号合并**。去冗余（`-unique first|longest|no`，默认 first）是**按物种**每基因保留一条（取 `species` 字段），不是按标本。
8. **分类信息/名称校正**：分类阶元来自 GenBank 记录自带的 lineage（`record.annotations['taxonomy']`），再用随包的 NCBI taxdump 导出的阶元名表（`data/*.csv`）判别 kingdom/phylum/class/order/family。**不校正物种名**（无 WoRMS/GBIF 对照）。
9. **输出**：按基因的 FASTA（`Divide/`、`Fasta/`、`Unique/`）、对齐、评估 CSV、`Primers.csv`、`Log.txt`；**没有"标本 x 基因"矩阵**。

**与 g2t 的异同**

| 项 | OGU | g2t |
|---|---|---|
| 目标 | 细胞器基因/IGS 的变异评估与引物设计 | 多基因系统发育/分类的标本 x 基因 accession 矩阵 |
| 核心单位 | 序列片段（locus） | 标本（voucher 键） |
| 取序列 | 按 feature 坐标切（含 spacer、intron） | 不切，只给 accession |
| 续传/校验 | 无（'w' 覆盖写；累计 10 次失败即中止） | 逐批记录数核对 + 重试 + 重跑续传 + manifest |
| 排除 WGS/mRNA | 否（需手动加 `-query`/`-molecular`） | 默认排除 |
| 凭证号合并 | 否 | 是（证据驱动） |

**优点**：唯一在开源工具里把"按 feature 切段 + IGS/intron 派生 + tRNA/rRNA 名称归一 + 线粒体/叶绿体过滤"做成一体化的；已发表（MER）；持续维护；有 GUI。
**缺点**：面向叶绿体/线粒体，**非细胞器位点（核 18S/28S/ITS、COI 之外的核基因）依赖作者标注的 feature，无 DEFINITION 级回退**；下载鲁棒性弱（无续传、无记录数校验）；无标本合并；无分类名校正；去冗余按物种而非标本；`get_query_string` 中 `-og no` 分支生成的字符串括号不配对（`'NOT mitochondrion[filter] NOT plastid[filter] NOT chloroplast[filter])'` 只有右括号；读码所见，未运行验证）。

### 1.3 其余 wpwupingwp 仓库的补充要点

- **rename**（旧脚本集，star 4，最后推送 2026-02-21）：`gene_rename.py` 是 OGU `-rename` 的前身（README 给出 `bad_name/suspicious_name/tRNA/rRNA/normal` 分类）；`large_query_with_id_list.py` 按 accession 列表分批（默认 500）下载，用 `-redo accession` 从指定 accession 续传，**README 明说不校验输出**；`batch_query.py` 对一份分类群列表逐个下载 `(plastid[filter] OR chloroplast[filter])` + SLEN 范围；ID 格式 `gene|kingdom|order|family|genus|species|accession|specimen_voucher`。
- **taxon_tools**（star 0，最后推送 2026-03-07）：依赖 aiosqlite、async-lru、biopython、requests；`taxon.py` 由 NCBI taxdump（names.dmp/nodes.dmp）建本地分类库；`gbif.py` 用 GBIF species API 查科/ID，跳过 synonym；`query.py` 查本地 sqlite 序列库并按上下游延伸取序列。属于**个人工具，README 仅 3 行，TODO 未完成项很多**，不是成熟的名称校正工具。


---

## 2. 其他同类工具

> 日期、star 取自 `gh api repos/<owner>/<repo>`（2026-10-08），"最后提交"为默认分支最近一次 commit 的作者日期。

### 2.1 SuperCRUNCH

- **仓库**：https://github.com/dportik/SuperCRUNCH ；star 45；LICENSE 文件为 GPL-3.0（README 文末写"GNU Lesser General Public License v3.0"，两处不一致）；**最后提交 2024-04-25**（README 编辑）；最新 release v1.3.2（2022-07-03）。
- **论文（README 所列）**：Portik DM, Wiens JJ (2020) SuperCRUNCH: A bioinformatics toolkit for creating and manipulating supermatrices and other large phylogenetic datasets. *Methods in Ecology and Evolution* 11: 763-772. https://doi.org/10.1111/2041-210X.13392
- **用途**：Python 脚本集（22 个独立模块，`supercrunch-scripts/`），把一个大 FASTA（GenBank 下载或自有序列）按"分类群名单 + 位点检索词"解析成各位点 FASTA，再做正交性过滤、选序列、比对、拼接，产出 supermatrix 或 phylogeographic 数据集（可检测 voucher）。依赖 Biopython、numpy，外部 BLAST+、CD-HIT-EST、MAFFT、Muscle、Clustal-O、MACSE、trimAl（conda env 提供）。
- **核心机制**
  - **不负责下载**：`docs/wiki-content/Starting_Materials.md` 明确写"在 NCBI nucleotide 网页上搜索分类群并下载 FASTA；类群太大就按目/科拆分后 `cat *.fasta` 合并"。**无 Entrez 脚本、无续传/校验**。FASTA 描述行不得含 `|`（不支持 gi| 格式）。`Remove_Long_Accessions.py` 用于去掉 >150 kb 的 WGS 记录。
  - **按描述行识别位点**（`Parse_Loci.py`）：位点检索词表 `locus<TAB>缩写<TAB>描述词1;描述词2<TAB>排除词`（例如 `AHR  AHR  aryl hydrocarbon;aryl hydrocarbon receptor  N/A`），对 FASTA 描述行（转大写）匹配；v1.3.0 起支持负向词（如 `pseudogene`）。**这与 g2t 的 "按 DEFINITION 关键词归类" 是同一思路**。
  - **分类名校正（半自动）**：`Taxa_Assessment.py` 把描述行中的二名法/三名法与用户给的分类群名单比对，输出 Matched/Unmatched 两个 FASTA 及 `Unmatched_Taxon_Names.log`；用户手工填两列表（旧名<TAB>新名），`Rename_Merge.py` 回填并并入匹配集。**需要人工提供名单与同物异名表，不联网查权威库**；仅支持二名法重命名。
  - **按坐标切序列（BLAST 驱动，非 feature 驱动）**：`Reference_Blast_Extract.py`（用参考序列建库，把"长 mtDNA 片段/整条细胞器基因组/不同引物的重叠片段"里的目标区段按 BLAST 坐标抽出）和 `Cluster_Blast_Extract.py`（CD-HIT-EST 取最大簇建库）；`-m span|nospan|all` 处理多段不连续坐标；文档提到可用于检测线粒体基因组中的基因重复。仓库 `data/reference-sequence-sets/` 提供 squamate/anuran 的 12S、16S、CO1、CYTB、ND1/2/4 参考集与 RAG1 参考集。**这是从整条线粒体基因组"抽取指定基因"的做法，不依赖提交者的 feature 注释**。
  - **凭证号**：`Parse_Loci.py` 从描述行里 `voucher`/`isolate`/`strain` 之后的词抽取，生成 `Voucher_<ID>` 标签；`Fasta_Relabel_Seqs.py --voucherize` 与 `Make_Acc_Table.py --voucherize` 把标签改成"物种_voucher"，使每行是"分类群+具体样本"。**按字符串相等对应，无证据合并**。（v1.3.1 修过 voucher 格式 bug。）
  - **选序列**：`Filter_Seqs_and_Species.py` 每分类群每位点选一条（`-f length` 最长；`-f translate` 先做阅读框翻译检验，支持 `--table`），也可保留全部序列做种群级数据集；v1.3.0 起有 `--accessions_include/--accessions_exclude`。
  - **输出矩阵**：`Make_Acc_Table.py` 生成"分类群（或分类群+voucher）x 位点"的 accession 表，缺失记为 `-`；`Concatenation.py` 生成拼接比对 + 分区文件。
- **与 g2t 异同**：同——按描述行关键词识别位点、产出 accession 表。异——SuperCRUNCH 不下载、不校验；有 BLAST 坐标切序列和翻译检验；有（人工驱动的）名称校正；voucher 仅做字符串标签，无冲突检测；以"分类群名单"驱动而非"类群下载"。
- **优点**：模块化、文档详尽；唯一明确提供"整条线粒体基因组 -> 单基因"的参考序列抽取方案和 accession table；有 oneseq 选择策略与 include/exclude accession 列表。
- **缺点**：不含下载器；依赖手工整理名单与 rename 表；最近一次 release 2022、最近提交 2024；Python 2.7/3.7 时代的脚本；FASTA 起点已丢失 GenBank 元数据（坐标、国家、日期、文献），故不可能做 g2t 式的"证据合并"。

### 2.2 PyPHLAWD

- **仓库**：https://github.com/FePhyFoFum/PyPHLAWD ；star 23；GPL-2.0；**最后提交 2024-10-27**；唯一 release v1.0（2018-08-20）。
- **引用（README 所列）**：Smith & Walker. *PyPHLAWD: a python tool for phylogenetic dataset construction.* Methods in Ecology and Evolution（README 给的链接 https://besjournals.onlinelibrary.wiley.com/doi/abs/10.1111/2041-210X.13096）。卷页码本次未在 README 上看到，未核实。
- **用途**：从**本地 sqlite 数据库**出发，按 NCBI 类群做"聚类运行"（BLAST + MCL）或"诱饵运行"（bait：按给定基因参考 FASTA 抓取同源区段），生成大规模对齐。
- **核心机制**（`docs/install.md`、`src/pyphlawd_db_maker.py`、`src/conf.py`）
  - **不使用 Entrez**。数据库由 `phlawd_db_maker`（https://github.com/blackrim/phlawd_db_maker ，本文未打开核实）或 `src/pyphlawd_db_maker.py` 建立：下载 NCBI taxdump.tar.gz（FTP/HTTPS）和 GenBank 分区 flat file（`read_gb_flat_file`），写入 sqlite 的 `taxonomy` / `sequence(ncbi_id, locus, accession_id, description, seqfile)` 表。
  - 以 NCBI taxon ID 为单位组织（`setup_clade.py <类群名> <db> <outdir> <log>`，可给 taxid 子集）。`conf.py` 里有长度/E 值/一致性阈值（如 `length_limit=0.65`、`smallest_size=450`、`filternamemismatch=True`），`exclude_patterns.py`/`exclude_desc_patterns.py`/`bad_seqs.py`/`bad_taxa.py` 排除已知问题记录（如描述含 `voucher DHJPLA`、`voucher WP1B0051` 的 BOLD 条码）。
  - **基因识别靠序列相似性，不靠名称**（bait/cluster）。
- **与 g2t 异同**：同——都以 NCBI 分类群为组织单元，都有"排除有问题记录"的清单。异——PyPHLAWD 用 flat file 批量库而非按类群在线下载；基因由 BLAST 聚类/诱饵确定而非 DEFINITION；以 taxon 为单位选序列，不处理标本/凭证号；输出对齐/树而非 accession 矩阵。
- **优点**：对"基因命名混乱"免疫；适合大类群/全 GenBank 规模。
- **缺点**：需要建/下载 GB 级本地数据库；文档里写"python : version 2"而 README 写"requires python3"（文档不一致）；仅一个 2018 年 release；对小类群、要保留标本信息的分类学任务过重。

### 2.3 phylotaR

- **仓库**：https://github.com/ropensci/phylotaR ；star 25；许可 MIT（DESCRIPTION）；**最后提交 2026-03-20**（修 R CMD check）；最新 release v1.3.0（2023-07-01）；DESCRIPTION 版本 1.3.0；维护者 Shixiang Wang。
- **论文（README 所列，DOI 链接）**：Bennett D, Hettling H, Silvestro D, Zizka A, Bacon C, Faurby S, et al. (2018) phylotaR: An Automated Pipeline for Retrieving Orthologous DNA Sequences from GenBank in R. *Life* 8(2): 20. https://doi.org/10.3390/life8020020 ；另列 Sanderson et al. 2008 PhyLoTa Browser, *Syst Biol* 57(3): 335-346, https://doi.org/10.1080/10635150802158688。
- **用途**：R 包，对一个 NCBI 类群（taxid）自动：`taxise`（取所有后代节点）-> `download`（逐节点下载序列）-> `cluster`（BLAST 聚类找直系同源簇）-> `cluster^2`（找姐妹簇）；再用 `get_*`/`drop_*`/`write_sqs` 导出簇。
- **核心机制**（`R/tools-entrez.R`、`R/stage2-tools.R`、`vignettes/phylotaR.Rmd`）
  - **Entrez query**：`(txid{ID}[Organism:exp] AND {mnsql}:{mxsql}[SLEN]) {srch_trm}`，默认 `mnsql=250, mxsql=2000`，**`srch_trm` 默认 `NOT predicted[TI] NOT "whole genome shotgun"[TI] NOT unverified[TI] NOT "synthetic construct"[Organism] NOT refseq[filter] NOT TSA[Keyword]`**——与 g2t 默认排除 WGS/RefSeq 的思路一致，但 phylotaR 用标题/关键词否定，g2t 用 `srcdb_refseq_model[PROP]` / `biomol_mrna[PROP]`。
  - **分层下载**（`hierarchic_download`）：递归 taxonomy 树，某节点的子树序列数超限（`mxsqs=50000`）时转为对该节点单独下载（`[Organism:noexp]`）并向下递归，避免一次拉取过大；`esearch(use_history)` + `entrez_fetch(rettype="acc")` 先取 accession ID（有 `sids_save` 缓存），再以 `btchsz=100` 分批取记录；重试等待序列 `wt_tms`，`mxrtry=100`。
  - **续传**：README："管道可在任意时点停止并重启而不丢数据"，有 `restart(wd)`；缓存在工作目录。
  - **基因识别**：不依赖基因名，仅靠 BLAST（`mxevl=1e-10`、`mncvrg=51`）；`mdlthrs=3000` 控制"模式生物"整基因组类大序列处理。
  - **不处理**凭证号/标本合并，不做名称校正（分类学信息来自 NCBI Taxonomy 自身）。
- **与 g2t 异同**：同——按 taxid 在线下载、默认排除 WGS/RefSeq/predicted、可重启。异——phylotaR 是"序列簇"导向（输出簇与序列，簇内不一定对应某命名基因），g2t 是"命名基因 x 标本"导向；phylotaR 无标本键。
- **优点**：被 rOpenSci 审查；分层下载是处理大类群的成熟做法；基因命名无关；保留重启能力。
- **缺点**：需要本地 BLAST+ 与 R 环境；簇到"COI/18S"等命名基因需要用户再映射；不输出标本矩阵。

### 2.4 PhyloSuite（GenBank 提取部分）

- **仓库**：https://github.com/dongzhang0725/PhyloSuite ；star 180；GPL-3.0；**最后提交 2026-02-16**（更新示例文件）；最新 release 标签 `v2`（2025-11-27）。
- **论文（README 所列）**：Zhang D, Gao F, Jakovlić I, Zou H, Zhang J, Li WX, Wang GT (2020) PhyloSuite: An integrated and scalable desktop platform for streamlined molecular sequence data management and evolutionary phylogenetics studies. *Molecular Ecology Resources* 20(1): 348-355. DOI 10.1111/1755-0998.13096。
- **用途**：PyQt 桌面平台，含"Search in NCBI / Download by IDs -> GenBank 文件管理 -> Extract GenBank file -> 比对 -> 拼接 -> 建树"。我们关心前三步。
- **核心机制**（文档页 https://dongzhang0725.github.io/dongzhang0725.github.io/documentation/ 、`PhyloSuite-demo/customize_extraction`、源码 `src/Lg_SerhNCBI.py`）
  - **下载**：GUI 里输入 Entrez 检索式（文档示例：`Monogenea[ORGN] AND (mitochondrion[TITL] OR mitochondrial[TITL]) AND 10000:50000[SLEN]`），`esearch(usehistory='y')` 后 `efetch` 以 `batch_size=20` 分批；也可粘贴 ID 清单下载。**无校验/断点续传机制（读码所见 `batch_size=20` 循环，未见逐批核对）**。
  - **按 feature 切序列**：Settings -> "GenBank File Extracting"：选要提取的 feature 类型（CDS、tRNA、rRNA、misc_feature…），为每类 feature 设置"取基因名的 qualifier 优先序"（默认 gene -> product -> note），提取为按基因/类型分文件夹的 FASTA（CDS_NUC、CDS_AA 等）；**同时提取重叠区和基因间区**；同一记录内重复基因编号为 `cox1`、`cox1_copy2`…；有 "Resolve gene duplicates"。
  - **名称统一**：首次提取自动生成 `StatFiles/name_for_unification.csv`，用户把同义名（COI/COX1/COXI）改为标准名后导入；可勾选"Only extract these genes"。预置 6 种 data-type：Mitogenome、chloroplast genome、general、cox1、16S、18S。**Single loc. mode** 则忽略注释，直接取整条序列（适合 18S、cox1、28S 单位点数据集）。
  - **rRNA / 线粒体基因组**：线粒体基因组由 Mitogenome 预设按 rRNA/CDS/tRNA 切开；rRNA 以 qualifier 名识别；ITS 无专门处理 [推测：需自行加 misc_feature]。
  - **分类信息**：谱系自动取自 GenBank 记录，可自定义阶元识别规则（通配符 `*dae`），也可经右键菜单"替换为 NCBI Taxonomy 或 WoRMS 的分类数据"（文档 4.4.1 原话）；`used_species.csv` 记录物种、谱系、AT/GC 含量。
  - **标本/凭证号**：`specimen_voucher`、`collection_date`、`country`、`collected_by` 等 source qualifier 可作为显示列，**无合并**。
- **与 g2t 异同**：同——都从 GenBank 记录读元数据、识别基因。异——PhyloSuite 以 feature 注释为准（依赖提交者注释）并实际切出序列；g2t 以 DEFINITION 归类、不切序列。PhyloSuite 无按类群批量下载与续传，无标本矩阵，GUI 为主。
- **优点**：同时覆盖下载/提取/比对/建树；name_for_unification 表是"可审计的人工名称统一"；对线粒体基因组、叶绿体基因组有预设。
- **缺点**：GUI 工作流不易脚本化/复现；下载无校验；依赖 feature 注释，无注释的 rRNA/ITS 记录提取不到；分类名更新（NCBI/WoRMS）需手动右键触发。

### 2.5 NCBI Datasets CLI（ncbi/datasets）

- **仓库**：https://github.com/ncbi/datasets ；star 561；**最后提交 2026-09-28**（release v18.38.0）；LICENSE.md（GitHub 标 NOASSERTION，未逐条核）。仓库只含 README、OpenAPI 规范、Go 客户端代码与教程；`datasets`/`dataformat` 二进制由 NCBI 发布。
- **论文（仓库 README 第 80 行列出；Crossref 核实标题/卷号一致）**：O'Leary NA, Cox E, Holmes JB, et al. (2024) Exploring and retrieving sequence and metadata for species across the tree of life with NCBI Datasets. *Scientific Data* 11(1): 732. doi:10.1038/s41597-024-03571-y。
- **用途**：按 genome（组装）/ gene（NCBI Gene）/ taxonomy / virus 取"数据包"（zip，含序列、注释、JSON Lines 元数据报告），`dataformat` 把元数据转 TSV/Excel。
- **核心机制**：REST API + CLI；大批量下载用 `--dehydrated` 先下骨架（元数据 + `fetch.txt` 文件清单），再 `datasets rehydrate` 取数据文件（README 与 OpenAPI 描述所见；是否可跨会话断点续取未核实）。OpenAPI 中有 `Organelle` 服务（`/organelle/download`），其 description 明确限定为"**RefSeq** 细胞器基因组"：可取基因、转录本、蛋白序列和元数据；`/gene/...` 服务基于 NCBI Gene 记录。
- **与 g2t 的关系**：**数据口径不同**。Datasets 面向"组装 / RefSeq 细胞器 / Gene 记录"，不提供"某类群下所有 GenBank 提交记录（含各研究者提交的 COI/18S/28S 片段）"的批量取回，也不含 voucher 合并。对于 g2t 的"标本 x 基因"目标，Datasets 只可作为补充来源（例如拿一个 RefSeq 线粒体基因组做参考，或核对某类群有无基因组组装）。
- **优点**：官方维护，速度快，元数据结构化（JSON Lines），分类学 summary 与 `taxonomy` 命令可查类群与 taxid；`--dehydrated/rehydrate` 是官方推荐的大批量下载方式。
- **缺点**：不覆盖散在的 GenBank 条形码/标记记录；基因/细胞器仅限 RefSeq；无标本概念。
- 说明：`datasets download` 的子命令清单我在 NCBI 文档参考页上看到 gene / genome / taxonomy / virus（genome、protein）/ rehydrate，**未在该下载子命令列表里见到 organelle**（`dataformat tsv` 的清单中有 organelle，OpenAPI 中有 /organelle 端点）；CLI 是否直接提供 organelle 下载命令未核实。

### 2.6 Entrez Direct（EDirect）

- **来源**：NCBI 官方，不在 GitHub 托管；分发于 https://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/ （目录索引显示 `edirect.tar.gz` 修改时间 2026-10-08、README 修改时间 2026-09-26）；conda 包名 `entrez-direct`（MitoFinder README 提到 `conda -c bioconda entrez-direct`）。
- **引用**：官方说明书在 NCBI Bookshelf（NBK179288）；本次访问 Bookshelf 页面被 reCAPTCHA 拦截，**推荐引用格式未核实**，故不写。
- **用途**：Unix 命令行管道：`esearch -> efilter -> elink -> efetch -> xtract`，所有步骤之间用结构化 XML 传递。
- **核心机制**（README 实读）
  - 内置"网络短暂故障重试、请求间延时、对大集合自动循环"（README 第 37 行："no need to ... write code to retry a query after a transient network or server failure, or add a time delay between requests"）。
  - **按 feature 取区段**：`efetch -db nuccore -id ... -format gb | xtract -insd CDS gene product feat_location sub_sequence`，即可输出每个 CDS 的坐标和**序列**；`-insd` 支持任意 feature+qualifier（如 `source` 的 `organism specimen_voucher country`）；还可 `-insdx` 存成 XML。
  - `xtract` 能直接读 GenBank flatfile（自动转 XML），`filter-genbank` 按 `-taxid/-organism/-accession/-exclude/-require/-min/-max` 过滤本地 GenBank 分区文件。
  - 示例检索式如 `esearch -db nuccore -query "insulin [PROT] AND rodents [ORGN]"`；线粒体基因组示例见 MitoFinder README：`esearch ... "mitochondrion[All Fields] AND (\"taxa\"[Organism]) AND (refseq[filter] AND mitochondrion[filter] AND (\"12000\"[SLEN] : \"20000\"[SLEN]))" | efetch -format gbwithparts`。
- **与 g2t 异同**：EDirect 是底层"瑞士军刀"，g2t 的 `download.py` 本质是在 Python 里重做了 `esearch | efetch` 并加上"按 accession 分批、记录数校验、可恢复、manifest"。EDirect 不提供基因归类、标本合并、矩阵。
- **优点**：官方、稳定、能直接从 GenBank 记录里按 feature 输出子序列；可与 g2t 并存（用 `xtract -insd` 做切序列的一步）。
- **缺点**：学习曲线；没有"标本"层；各步骤之间无逐批记录数校验和跨会话续传（README 只声明"重试和延时内置"，未见断点续传说明）；Windows 支持细节未核（FTP 目录中有 edirect.exe 与 CYGWIN_NT 构建）。

### 2.7 ncbi-acc-download

- **仓库**：https://github.com/kblin/ncbi-acc-download ；star 133；Apache-2.0；**最后提交 2024-08-05**；最新 release 0.2.9（2024-08-01）。仓库 README 未给论文引用（已 grep，无 cite/DOI）。
- **用途**：按 accession（可多个）经 Entrez efetch 下载 GenBank (`gbwithparts`) 或 FASTA。
- **核心机制**（`ncbi_acc_download/core.py`、`validate.py`）：遇 HTTP 429 读 `Retry-After` 后等待再重试；`--extended-validation none|loads|all|correct`：用 Biopython 把下载结果解析一遍确认可读；`correct` 会移除区间被截断（`<`/`>` 部分位置）的 feature（配合 `--range 1001:9000` 取子区间）；`--recursive` 把 WGS master 展开成各 contig；`--url` 仅输出下载 URL。
- **与 g2t 异同**：只管"已知 accession -> 文件"，不检索、不按类群、不整理；校验的是"能否被解析"，不是"记录数是否齐全"。g2t 的逐批记录数核对更贴近"完整性"。
- **优点**：小而专一；`--range` + `correct` 能取子区间并清理残缺 feature。
- **缺点**：无检索、无批量断点续传、无类群/基因概念。

### 2.8 MitoFinder 与 MitoZ（只看其 GenBank/注释提取部分）

**MitoFinder**
- **仓库**：https://github.com/RemiAllio/MitoFinder ；star 116；**最后提交 2025-09-02**；latest release v1.4.2（2024-04-11）；GitHub 未识别许可证（仓库有 `License` 目录，未逐文件核）。
- **论文（README 所列）**：Allio R, Schomaker-Bastos A, Romiguier J, Prosdocimi F, Nabholz B, Delsuc F (2020) MitoFinder: Efficient automated large-scale extraction of mitogenomic data in target enrichment phylogenomics. *Mol Ecol Resour* 20: 892-905. https://doi.org/10.1111/1755-0998.13160
- **GenBank 相关部分**：它**并不批量下载或整理 GenBank**；GenBank 仅作"参考线粒体基因组"输入（`-r reference.gb`）。README 的"HOW TO GET REFERENCE MITOCHONDRIAL GENOMES FROM NCBI"给出 EDirect 命令：`esearch -db nuccore -query "\"mitochondrion\"[All Fields] AND (\"${taxa}\"[Organism]) AND (refseq[filter] AND mitochondrion[filter] AND (\"12000\"[SLEN] : \"20000\"[SLEN]))" | efetch -format gbwithparts > reference.gb`。辅助脚本 `extract_genes.py`（Python 2.7，用旧版 `Bio.Alphabet`）逐 feature 读取 CDS 和 rRNA，名称取 `/gene` 否则 `/product`（去空白），用 `feature.extract(record)` 输出 `>ID@基因名` 的 FASTA。
- **借鉴价值**：线粒体检索式模板（RefSeq + mitochondrion[filter] + 12000:20000[SLEN]）与 g2t `--mitogenome`（`mitogenome[Title]` + 10000:30000）思路一致；其余是组装/注释，不相关。

**MitoZ + gbseqextractor**
- **MitoZ 仓库**：https://github.com/linzhi2013/MitoZ ；star 150；GPL-3.0；**最后提交 2024-11-06**（更新 README）；latest release 3.6（2023-04-14）。默认分支（master）当前仅含 README、LICENSE、`test/` 与 `.github/`（我读到的树如此），**MitoZ 本体源码未在默认分支，故其注释输出代码未审读**。
- **论文（README 所列）**：Meng G, Li Y, Yang C, Liu S (2019) MitoZ: a toolkit for animal mitochondrial genome assembly, annotation and visualization. *Nucleic Acids Res* 47(11): e63. https://doi.org/10.1093/nar/gkz173
- **GenBank 提取部分**：由同作者的 **gbseqextractor**（https://github.com/linzhi2013/gbseqextractor ；star 9；GPL-3.0；最后提交 2024-01-31；README 声明"本脚本是 MitoZ 软件包的一部分"）完成：`gbseqextractor -f x.gb -prefix p -types CDS rRNA tRNA wholeseq gene`，**按 feature 坐标切序列**，ID 取 `/gene` 或 `/product`（两者都没有则**不输出**该基因），支持 `join()` 复合位置（2020-11-28 版起）、`-rv` 负链反向互补、`-F` 仅取完整长度基因（去掉位置含 `<`/`>`）、`-t/-s/-p/-l` 在 ID 行附加分类谱系/物种名/位置/长度。**明示不会把同一基因的多个 CDS 合并成一条**。
- **与 g2t 的关系**：这是"线粒体基因组 -> 各基因序列"最轻量的现成实现，可直接作为 g2t 下游的切序列步骤。

### 2.9 BOLDconnectR（BOLD 数据下载，可选项）

- **仓库**：https://github.com/boldsystems-central/BOLDconnectR ；star 27；MIT + LICENSE 文件（DESCRIPTION）；**最后提交 2026-08-20**（v1.0.2）。
- **论文（README 所列，Crossref 核实）**：Padhye SM, Ballesteros-Mejia L, Agda J, Agda J, Hebert PD, Ratnasingham S (2026) BOLDconnectR: An R package for streamlined retrieval, transformation, and analysis of DNA barcode data on BOLD. *PLoS ONE* 21(8): e0355496. https://doi.org/10.1371/journal.pone.0355496
- **用途**：R 包，11 个函数（`bold.fetch`、`bold.public.search`、`bold.full.search`、`bold.analyze.*`、`bold.export` 等），以 BCDM（Barcode Core Data Model）格式取公开/私有 BOLD 数据；`bold.fetch` 可按 processid/sampleid/bin_uris/dataset_codes/project_codes 取，单次硬上限 100 万条记录（函数文档原话）。
- **与 g2t 的关系**：BOLD 是 g2t 明确不覆盖的来源（README 限制 7）。BCDM 字段表（README 第 121 行）含 `insdc_acs`（INSDC accession）、`sampleid`、`specimenid`、`museumid`、`fieldid`，即 BOLD 记录自带"标本 ID"与"GenBank accession"的对应；[推测] 可用 `insdc_acs` 把 BOLD 标本 ID 与 GenBank accession 对上，以补充 g2t 的凭证号合并。该字段在实际数据里的填充率未核实。
- **缺点**：只覆盖条形码（主要 COI 等）；需 BOLD API key；R 环境。

### 2.10 CRABS（补充：条形码参考库构建，非用户指定）

- **仓库**：https://github.com/gjeunen/reference_database_creator ；star 52；MIT；**最后提交 2026-01-13**；GitHub 最新 release v1.14.0（2025-11-20）（README 文字仍称"CRABS v 1.0.0"，版本号口径不一致，未深究）。
- **论文（README 所列）**：Jeunen G-J, Dowle E, Edgecombe J, von Ammon U, Gemmell NJ, Cross H (2022) crabs—A software program to generate curated reference databases for metabarcoding sequencing data. *Mol Ecol Resour*. https://doi.org/10.1111/1755-0998.13741
- **相关机制**：`crabs --download-ncbi --query '<Entrez 检索式>' --database nucleotide --batchsize 5000 --email ...`，也支持 `--species` 名单；其 `--import` 将 NCBI/BOLD/MIDORI/MitoFish/SILVA 等统一为"一行一序列"的 CRABS 格式，**分类谱系用 NCBI `names.dmp`/`nodes.dmp` + `nucl_gb.accession2taxid` 通过 accession->taxid 重建**，而非解析记录文本；之后做 in-silico PCR（cutadapt）、去重、按条件过滤。README 称 v1.0.0 增加"解析异名和未接受名"，细节我未深读，未核实。
- **与 g2t 异同**：CRABS 面向宏条形码"参考库"（序列为主、无标本层）；对 g2t 有参考价值的是"按 accession 用 accession2taxid 重建谱系"，可以避免依赖记录里的 lineage 文本。

---

## 3. 对比总表

图例：Y = 有；部分 = 有但受限（见注）；N = 无；n/a = 该工具不涉及此环节；"未核" = 未能核实。维护状态取 GitHub 默认分支最后一次提交日期（2026-10-08 查询）和 star 数。

| 工具 | 按类群下载 | 按基因/线粒体筛选 | 续传与校验 | 按 feature 切序列 | rRNA 区段拆分 | 标本/凭证号合并 | 名称校正 | 输出矩阵 | 维护状态 |
|---|---|---|---|---|---|---|---|---|---|
| **g2t v0.01**（本工具） | Y（taxid/名称，`[Organism:exp]`，默认排除 WGS/mRNA/RefSeq model） | Y（`--mito/--mitogenome/--gene/--minlen/--query`；按 DEFINITION 归 13 类） | Y（按 accession 分批，逐批核对记录数，退避重试，重跑续传，manifest） | N（只给 accession） | N（`18-28s`/`its1-its2` 仅标类型；9/175 条 rRNA 记录被归为 its1-its2 而漏 18S/28S，README 限制 1） | Y（`organism+voucher` 建键 + 证据合并 step 3b） | N（名称照录；ete3 按 taxid 补谱系，BUGS.md） | Y（标本 x 基因，accession） | v0.01，2026 年发布；无论文 |
| **OGU**（原 BarcodeFinder） | Y（`[organism]`/txid + 过滤器；无默认排除 WGS/mRNA） | Y（`-og mt/cp`、`-gene`、`-refseq`、`SLEN`、`PDAT`） | N（`'w'` 覆盖写，无记录数核对；累计 10 次失败中止；解析时跳过坏记录） | Y（gene/CDS/tRNA/rRNA/misc_feature/misc_RNA/D-loop；派生 IGS 与 intron） | 部分（rRNA feature 可单切；ITS 命名分支读码存疑） | N（仅 `specimen_voucher+isolate` 作标签；去冗余按物种） | 部分（基因名正则归一；物种名不校正） | N（按基因 FASTA + 评估 CSV + 引物表） | 2026-05-18；v2.1.0；25 star；MER 2025;25(3):e14044 |
| wpwupingwp 旧脚本（`rename`、`taxon_tools`） | 部分（名单逐类群；accession 列表） | 部分（质体 `[filter]` 硬编码） | 部分（`-redo accession` 手动续传，README 明说不校验） | 部分（`gene_rename.py`/`gb2fasta.py` 的前身） | 未核 | N | 部分（`taxon_tools`：GBIF 查科，跳过 synonym；个人脚本） | N | `rename` 2026-02-21（4 star）；`taxon_tools` 2026-03-07（0 star） |
| **SuperCRUNCH** | N（用户手动下 FASTA；`Remove_Long_Accessions.py` 去 >150 kb） | Y（检索词表 + 负向词；`Reference_Blast_Extract` 可从整条 mtDNA 抽目标基因） | N | N（输入是 FASTA，已无 feature）；改用 BLAST 坐标切 | 部分（靠参考序列 BLAST；仓库带 12S/16S/CO1/CYTB/ND 参考集，18S/28S 需自备） | 部分（描述行抽 `Voucher_ID` 做标签；无证据合并） | 部分（`Taxa_Assessment` + `Rename_Merge` 手工异名表） | Y（`Make_Acc_Table` accession 表；`Concatenation` 拼接+分区） | 2024-04-25；v1.3.2（2022-07）；45 star；MEE 2020 |
| **PyPHLAWD** | N（本地 flat-file sqlite 库） | 部分（bait 参考 / BLAST+MCL 聚类，不靠名称） | n/a | N | n/a | N | 部分（依 taxdump taxid；`filternamemismatch`） | N（对齐/簇） | 2024-10-27；唯一 release v1.0（2018）；23 star |
| **phylotaR** | Y（taxid；分层下载；默认排除 predicted/WGS/unverified/synthetic/RefSeq/TSA） | 部分（簇导向，不按基因名；SLEN 250-2000 默认） | Y（可 `restart`，缓存 ID 与记录；批 100，重试；逐批记录数核对未见） | N | N | N | n/a（沿用 NCBI Taxonomy） | N（序列簇） | 2026-03-20；v1.3.0（2023-07）；25 star；Life 2018 |
| **PhyloSuite** | 部分（GUI 检索式或 ID 清单；批 20） | Y（检索式；预设 Mitogenome/chloroplast/cox1/16S/18S） | N（未见逐批核对） | Y（feature+qualifier 优先序；含重叠区与基因间区） | 部分（rRNA feature；Single loc 模式取整条） | N（仅显示 `specimen_voucher` 等列） | 部分（名称统一表；谱系可替换为 NCBI/WoRMS，手动） | 部分（拼接矩阵+分区，非 accession 表） | 2026-02-16；180 star；MER 2020;20(1):348 |
| **NCBI Datasets CLI** | Y（taxon 级，但对象是组装/Gene/病毒） | 部分（RefSeq 细胞器；Gene） | 部分（dehydrated/rehydrate；续取未核） | 部分（organelle/gene 包含基因、转录本、蛋白序列，据 OpenAPI 描述） | 未核 | N | 部分（taxonomy 服务） | N | 2026-09-28；v18.38.0；561 star；Sci Data 2024 |
| **Entrez Direct** | Y（任意 Entrez 检索） | Y（检索式 + `filter-genbank`） | 部分（内置重试与延时；断点续传未见） | Y（`xtract -insd CDS gene product feat_location sub_sequence`） | 取决于注释 | N | N | N（可自行拼表） | FTP 构建 2026-10-08；官方；引文未核 |
| **ncbi-acc-download** | N（按 accession） | N | 部分（429 等待；`--extended-validation` 解析校验） | N（仅 `--range` 子区间 + `correct` 去残缺 feature） | N | N | N | N | 2024-08-05；0.2.9；133 star |
| **MitoFinder** | n/a（参考 gb 由用户给） | 部分（README 给线粒体 RefSeq 检索模板） | n/a | 部分（`extract_genes.py` 仅处理参考 gb 的 CDS/rRNA） | 部分（rRNA 按 gene/product） | N | N | N | 2025-09-02；116 star；MER 2020 |
| **MitoZ / gbseqextractor** | N | Y（动物线粒体基因组） | n/a | Y（`gbseqextractor`：CDS/rRNA/tRNA/gene/wholeseq，处理 join，`-F` 去残缺） | Y（`-types rRNA`） | N | N | N | gbseqextractor 2024-01-31（9 star）；MitoZ 2024-11-06（150 star）；NAR 2019 |
| **BOLDconnectR** | Y（BOLD，非 GenBank；按 taxonomy/地理/BIN/项目） | 部分（BOLD 以条形码为主，未核） | 未核（单次上限 100 万条） | N | N | 部分（BCDM 含 `sampleid`/`museumid`/`insdc_acs` 便于对照） | 部分（BOLD 分类） | N（BCDM 表） | 2026-08-20；v1.0.2；27 star；PLoS ONE 2026 |
| **CRABS** | Y（NCBI 检索式/`--species` 名单，批 5000；也支持 BOLD、MIDORI、MitoFish 等） | 部分（检索式含 `mitochondrion[filter]` 等） | 未核 | N（in-silico PCR 取扩增子） | N | N | 部分（accession->taxid 重建谱系；异名处理细节未核） | N（参考库 FASTA/BLAST/IDTAXA） | 2026-01-13；v1.14.0；52 star；MER 2022 |

**阅读要点**

1. 在表内的开源工具里，**没有一个**同时做到"按类群下载 + 逐批校验续传 + 标本/凭证号证据合并 + 标本 x 基因矩阵"，这四项合起来是 g2t 的独占组合（以本次核实范围为限，不代表全网不存在）。
2. **按 feature 切序列**是 g2t 缺的、而 OGU / PhyloSuite / gbseqextractor / EDirect 都有的能力；它们的共同前提是提交者给了 feature 注释。
3. **不依赖注释的切法**只见到 SuperCRUNCH（BLAST 参考序列坐标）；代价是需要参考序列集。
4. 下载端，phylotaR 的默认排除词表和分层下载、OGU 的 `[PDAT]` 日期范围、ncbi-acc-download 的 429 处理，是 g2t 可以补的细节。

---

## 4. g2t 可借鉴的具体做法（8 条）

> 每条格式：做法（来源工具与机制）-> 对应 g2t 的哪个已知限制 -> 落地建议。落地建议中带 [推测] 者为我的设计推断，未在任何来源工具中验证。

1. **按 feature 坐标切序列，作为独立的下游步骤。**
   来源：OGU `gb2fasta.divide/write_seq`（Biopython `feature.extract(whole_seq)`，名称取 `/gene`->`/product`->`/locus_tag`->`/note`，复合 `join()` 与链向自动处理，`-max_gene_len` 跳过过长 feature）；PhyloSuite 的"feature + qualifier 优先序"设置；gbseqextractor 的 `-F`（去 `<`/`>` 残缺）与 `-types`；EDirect 的 `xtract -insd CDS gene product feat_location sub_sequence`。
   对应限制：README 限制 2（不切序列）与限制 1（多区段 rRNA 记录按整条 DEFINITION 归类，漏 18S/28S）。
   落地：g2t 已把原始 `.gb` 存在 `gb/<tag>/batch_*.gb`，可新增只读这些文件的 `g2t-slice`，对 `rRNA`/`CDS`/`misc_feature` 按坐标输出"每基因一个 FASTA"，ID 带 `accession|start-end|strand`，并写一张"记录 x feature"表；矩阵逻辑不动，只在 `18-28s`/`mtgenome`/被误归 `its1-its2` 的记录上补出真正的 18S/28S/各线粒体基因列。[推测]

2. **无注释或注释残缺的记录，用参考序列 BLAST 坐标兜底。**
   来源：SuperCRUNCH `Reference_Blast_Extract.py`（参考序列建库，把长 mtDNA 片段/整条细胞器基因组中的目标区段按 BLAST 坐标抽出，`-m span|nospan|all` 处理不连续命中；文档称可发现线粒体基因重复）及其 `data/reference-sequence-sets/`。
   对应限制：限制 2 的"注释缺失"分支；也覆盖 feature 法抓不到的老记录（只有 DEFINITION 写 "18S ... ITS1 ... 28S" 而无 feature）。
   落地：只对 `1` 里切不出的记录启用；参考序列用本项目自己已确认的 Priapulida 序列建（SuperCRUNCH 自带的是 squamate/anuran 参考集，不能直接用）。[推测]

3. **自动生成"名称统一表"并支持用户回灌，同时给线粒体/tRNA 基因名加规则归一。**
   来源：PhyloSuite 首次提取自动写出 `StatFiles/name_for_unification.csv`（列出所有出现过的名称，用户改 "New Name" 后导入）；OGU `utils.gene_rename`（tRNA 按反密码子+翻译表归一为 `trn{氨基酸}_{反密码子}`；`coi->COX1`、`cob->CYTB`、`nadh?N->nadN`、`atp(ase)?N->ATPN`）。
   对应限制：限制 4（只有 13 种基因类型，其余落入 `unmatched_sequences.csv`）。
   落地：把 `unmatched_report.txt` 里的未匹配 DEFINITION/feature 名按频次自动输出成"待归类名称表"（CSV），用户填基因类型后由 `--path_dict` 回灌，免手写 YAML；OGU 的 tRNA/线粒体基因规则可作为切序列步骤的 feature 名归一。

4. **位点词典加"负向词"，并支持 accession 白名单/黑名单。**
   来源：SuperCRUNCH v1.3.0 `Parse_Loci.py` 第四列负向词（如 `pseudogene`）；v1.3.0 `Filter_Seqs_and_Species.py --accessions_include/--accessions_exclude`（include 列表可覆盖长度等选择规则，exclude 永不选）。
   对应限制：限制 7（`--gene` 按基因字段与标题词检索，会带入线粒体基因组等无关记录）与 DEFINITION 关键词的误匹配（`gene_dict.yaml` 目前只有同义词列表，未见排除词字段）。
   落地：`gene_dict.yaml` 每个基因增加 `exclude:` 列表；CLI 增加 `--accessions-exclude/--accessions-include`，用于人工否决明显错配或强制保留某条。

5. **每个过滤步骤都输出"被拒绝清单 + 计数日志"，不静默丢弃。**
   来源：SuperCRUNCH `Taxa_Assessment.py` 同时写 Matched/Unmatched 两个 FASTA 及 accession 清单，`Parse_Loci.py` 写 `Loci_Record_Counts.log`；OGU `clean_gb` 对坏记录逐条 `log.critical` 并统计数量；ncbi-acc-download 的 `--extended-validation loads` 把"能否解析"作为显式检查。
   对应限制：限制 3（150-50,000 bp 之外的记录在分类前被删，且不进 `unmatched_sequences.csv`）。
   落地：长度过滤改为"打标签、不删除"，被滤掉的 accession 写入 `rejected_by_length.csv`；每批 `.gb` 解析失败的 accession 写入 manifest。

6. **名称校正走"匹配/未匹配 + 人工异名表"的两段式，异名表由 WoRMS 数据生成。**
   来源：SuperCRUNCH `Taxa_Assessment.py`（对照分类群名单，产出 Matched/Unmatched 与 `Unmatched_Taxon_Names.log`）+ `Rename_Merge.py`（两列 tab 异名表，回填后并回主集）；PhyloSuite 文档 4.4.1 的"谱系可替换为 NCBI Taxonomy 或 WoRMS 数据"。
   对应限制：限制 6（名称照提交者原样，未对照权威库）。
   落地：本项目已有 `yzz-worms` 产出的"异名 -> 有效名"表，可直接作为 `Rename_Merge` 式的两列表，在矩阵里新增 `valid_name` 列而不改 `organism` 原列（保留可追溯性）；匹配不上的名称进 Unmatched 清单。[推测]

7. **下载端的检索式卫生与增量更新。**
   来源：phylotaR 默认 `srch_trm`（`NOT predicted[TI] NOT "whole genome shotgun"[TI] NOT unverified[TI] NOT "synthetic construct"[Organism] NOT refseq[filter] NOT TSA[Keyword]`）与 `hierarchic_download`（子树序列数超限时改对节点 `[Organism:noexp]` 逐级下载）；OGU 的 `[PDAT]` 日期范围；ncbi-acc-download 对 HTTP 429 读 `Retry-After` 等待。
   对应限制：限制 7（下载只覆盖 nuccore，噪声记录靠后处理）及大类群时的单次检索规模。
   落地：在 `build_query` 增加可选 `--exclude-tsa/--exclude-unverified/--exclude-synthetic`；`manifest.json` 已存日期，可加 `--since <manifest 日期>` 配合 `[PDAT]` 做增量补下；`_call` 的重试中读 429 的 `Retry-After`。[推测：需确认 Biopython 的 HTTPError 是否暴露该响应头]

8. **用 BOLD 的标本 ID 与 `insdc_acs` 交叉印证凭证号合并。**
   来源：BOLDconnectR 的 BCDM 字段（README 第 121 行列出 `insdc_acs`、`sampleid`、`specimenid`、`museumid`、`fieldid`）。
   对应限制：限制 5（无共同文献/日期/坐标时，凭证号变体保持不合并）和限制 7（不含 BOLD）。
   落地：对 g2t 判为"未合并"的候选对，若两条 accession 在 BOLD 中对应同一 `sampleid`/`museumid`，可作为额外的强证据。该字段在目标类群（Priapulida）里的实际填充率未核实，先做可行性统计再决定。[推测]

---

## 5. 未核实与需注意的事项

- EDirect 的推荐引文：NCBI Bookshelf 页面被 reCAPTCHA 拦截，WebFetch 中断，未核实。
- PyPHLAWD 论文的卷页码：README 只给了期刊页 DOI 链接（`10.1111/2041-210X.13096`），页码未在仓库里看到；`phlawd_db_maker` 仓库本身未打开。
- MitoZ 本体源码不在 master 分支（树内仅 README、LICENSE、`test/`、`.github/`），其注释/GenBank 输出实现未审读；gbseqextractor 为其同作者脚本，README 声明属 MitoZ 软件包。
- NCBI Datasets：`datasets download` 是否有直接的 organelle 子命令，文档页清单中未见；OpenAPI 与 `dataformat tsv` 清单中有。
- OGU 两处读码观察未运行验证：(a) `get_feature_name` 中 ITS 改名后被 `safe_path(name)` 覆盖；(b) `-og no` 分支检索式括号不配对。
- CRABS 的"异名/未接受名解析"仅见 README 的功能列表一行，未读实现；GitHub release 标签（v1.14.0）与 README 文字（v 1.0.0）版本口径不一致。
- BOLDconnectR 的 `insdc_acs` 字段在真实 Priapulida 数据里的填充率未核实。
- 所有 star 数与日期取自 2026-10-08 的 GitHub API，会随时间变化。
- GitHub 匿名 API 对 `pushed_at` 与默认分支最后提交日期的取值可能不同，表中统一用默认分支最后一次 commit 的作者日期；OGU 的 star=25、commit=2026-05-18，已两种口径互相印证。

---

## 6. 主线程抽查（2026-10-08）

| 结论 | 核查方式 | 结果 |
|---|---|---|
| BarcodeFinder 即 OGU | GitHub API：`repos/wpwupingwp/BarcodeFinder` 返回 301 → repositories/111626171 = wpwupingwp/OGU | ✅ |
| OGU：25 star，最后推送 2026-05-18，最新 release v2.1.0 | GitHub API | ✅ |
| OGU 论文 Mol Ecol Resour 25(3): e14044，doi:10.1111/1755-0998.14044 | Crossref | ✅ |
| OGU `-og no` 分支检索式括号不配对 | 读 `src/OGU/gb2fasta.py` 第 154–155 行：`'NOT mitochondrion[filter] NOT plastid[filter] ' 'NOT chloroplast[filter])'`，只有右括号 | ✅（读码确认；未运行） |
| phylotaR 默认排除 predicted/WGS/unverified/synthetic 等 | `R/phylotaR.R` 第 48–55 行（`"NOT predicted[TI] "` …） | ✅ |
| SuperCRUNCH：MEE 11: 763–772，doi:10.1111/2041-210X.13392 | Crossref | ✅ |
| PhyloSuite：MER 20: 348–355，doi:10.1111/1755-0998.13096 | Crossref | ✅ |
