# 线粒体注释流程 benchmark + 细胞器注释知识库 + 迭代优化 — 设计

日期：2026-10-20　状态：用户 2026-10-20 同意，修改为"先以 NC_ 注释为准"
代码位置：`temp_scripts/Mitoz-annotate/`（独立 GitHub 仓库 Temp_scripts）；需求登记：`modules/genbank/REQUIREMENTS.md`

## 1. 目的（用户原话要点）

- benchmark 两用：**论文里的方法对比** + **我们自己定默认设置**。
- 主要目的是**找出流程的 bug 和潜在问题，反复优化，确保不出现明显注释错误**，方便外部用户和我们自己用。
- 以 NC_（RefSeq）为基准，**优先选有转录组注释或三代组装数据的记录**。
- 对比维度：**准确性、时间、安装难易程度**等。
- 类群：**覆盖整个后生动物，尽可能广**（扩大用户群）。
- 阅读各软件**源码、文献、issues、使用说明**，建立**本地细胞器注释知识库**，便于后续更新、避免反复学习；在此基础上再优化软件。

## 2. 目标 / 非目标 / 反目标

目标
1. 一套可复现的 benchmark：冻结的记录清单 + 运行脚本 + 评估脚本 + 报告表，一条命令可重跑。
2. 一个有出处的本地知识库：每条结论带 `file:line`、DOI、issue 链接或文档 URL，并注明软件版本和查阅日期。
3. 一轮或多轮"跑 → 分类错误 → 查因 → 修 → 加回归检查 → 再跑"，直到开发集上没有可归因于我们流程的系统性明显错误。

非目标
- 不重新实现 MitoZ/MITOS2 的整个注释算法（只在知识库找到依据时局部移植，沿用 mito_intron.py 的做法）。
- 不做植物/真菌线粒体、叶绿体（知识库可记录，但本轮 benchmark 只做后生动物）。
- 网页版工具（GeSeq、MitoAnnotator 网页端等）不批量跑。

反目标（做了也算失败）
- 为了分数好看而针对测试集调参（见 §3.4 开发集/测试集分离）。
- 把 RefSeq 当绝对真值：与 NCBI 不一致不等于我们错（见 §5.3 人工裁定）。
- 推测写成结论：知识库与报告区分"已确证 / 未定 / 推测"。
- benchmark 数据放在 /tmp（上次 /tmp 被清空导致清单丢失）。

## 3. 金标准数据集

### 3.1 来源与分层
- NCBI nuccore：`<门>[Organism] AND mitochondrion[Filter] AND complete genome[Title] AND refseq[Filter]`，只取 NC_。
- 按**门**分层随机抽样（固定随机种子，记录检索日期），覆盖所有有 RefSeq 线粒体基因组的后生动物门；大门（Chordata、Arthropoda、Mollusca、Annelida、Cnidaria…）在纲/目层次再分散，避免集中于少数科。
- 每个门的配额：我的设定 = 大门 12 条、小门全部可用记录但上限 6 条；总量约 250 条（视检索结果调整，最终数写进清单）。

### 3.2 证据等级（优先"转录组/三代"记录）
对每条 NC_，追溯其源 INSDC 记录（`COMMENT` 中的 "The reference sequence is identical to ..."），从源记录抽取：
- **A 级 转录组证据**：structured comment / COMMENT / 参考文献标题中出现 RNA-seq、transcriptome、Iso-Seq、cDNA 等，或 SRA 关联有 RNA 数据。
- **A 级 三代组装**：`Sequencing Technology` 含 PacBio / Nanopore / Oxford（HiFi、ONT）。
- **B 级**：其余 RefSeq。
每门先尽量从 A 级抽，不够再用 B 级补足；清单中标注等级，报告分等级给结果（A 级子集更接近真值）。识别规则是关键词匹配，会有漏判/误判——我的判断，报告中说明。

### 3.3 遗传密码与类群覆盖
- 遗传密码取 NCBI CDS 的 `transl_table` 众数（2、4、5、9、13、14、21、24 等都会出现）。
- 必须包含 MitoZ 不支持的类群（MitoZ 3.6 `--clade` 只有 Chordata、Arthropoda、Echinodermata、Annelida、Bryozoa、Mollusca、Nematoda、Nemertea、Porifera；`batch_mitoz.py:331`）——如 Cnidaria、Platyhelminthes、Placozoa、Ctenophora、Brachiopoda、Rotifera 等，用于暴露流程在这些类群上的行为。

### 3.4 开发集 / 测试集
- 按门内 1:1 随机切成**开发集**（用于找 bug、调参、优化）和**测试集**（只在定稿时跑一次，论文报告用）。
- 优化期间不看测试集结果。

### 3.5 存放
- 清单（accession、门、纲、遗传密码、证据等级、dev/test、检索日期）进 git：`benchmark/sets/mito_bench_2026-10.tsv`。
- 下载的 GenBank 与运行结果放 `projects/mito_benchmark/`（不进 git，不放 /tmp）。

## 4. 对比对象

| 对象 | 说明 |
|---|---|
| **本流程（默认）** | batch_mitoz.py 当前默认流程（MitoZ + 定向 + intron + curate + NCBI 校验；tRNA 来源按当前默认） |
| 本流程（可选组合） | 如 `--select mitos2` tRNA、多方法 tRNA，用于定默认 |
| MitoZ 3.6 单跑 | 原版 `mitoz annotate`，不经我们的后处理 |
| MITOS2 单跑 | runmitos，refseq89m，完整模式（PCG+rRNA+tRNA） |
| MitoFinder（可选） | 若 bioconda 可装且能在裸序列上注释，纳入；否则只进知识库 |

| 机器学习 tRNA 预测（实验） | 用户 2026-10-20：MITOS2 好是因为有数据库；可尝试训练 tRNA 预测。先在知识库调研已有 ML/深度学习 tRNA 预测方法与其训练数据；再试训练一个模型（训练数据 = RefSeq tRNA，**按属切分**，排除 benchmark 测试集所在属），与 MITOS2 等在同一 benchmark 上比较。效果不如现有方法就只留报告，不进流程 |

输入一律为**裸序列**（只留 source），按 NCBI 原方向。

## 5. 评估

### 5.1 准确性（每类特征：PCG、rRNA、tRNA、intron、控制区不计）
- 匹配：同基因名（统一命名表）+ 同链 + 重叠 ≥50%。
- 指标：召回、精确（FP = 该处无 NCBI 同名特征）、起止完全一致 / ±3 nt / >3 nt、链向错误、基因名错误（如 trnL1/trnL2、trnS1/trnS2、nad4/nad4l）。
- PCG 额外：翻译后内部终止密码子、起始/终止密码子是否合法（按遗传密码表）、不完整终止 T/TA 处理、长度与 NCBI 比值。
- intron：沿用现有 `compare.py`/`eval_features.py` 规则。

### 5.2 "明显注释错误"清单（优化的主要对象）
缺失 PCG/rRNA、PCG 移码或内部终止、链向反、基因重复注释、基因名错、坐标偏差 > 30 nt、table2asn ERROR/REJECT、流程崩溃或静默跳过。每条记录输出一行错误汇总。

### 5.3 不一致的人工裁定
由我（Claude）逐条查证裁定，用户抽查（用户 2026-10-20：不清楚哪个注释更好）。对开发集里的每个"明显错误"，查证后归为：**我们错 / NCBI 错 / 无法判定**；依据（近缘种比对、文献、源码行为）写进知识库或 `benchmark/adjudication.tsv`。NCBI 错的不计入我们的错误率，但单独报告。

### 5.4 时间
同一台机器（16 核、62 GB），固定线程数；每条记录墙钟时间，并分步统计（MitoZ、tRNA、intron、curate、校验）。报告中位数和总耗时。

### 5.5 安装难易
- 在干净 Docker 容器（Linux）里按各软件官方说明从零安装，记录：步骤数、需手动下载的数据、conda 环境数、磁盘体积、总耗时、失败点。
- macOS（Intel / Apple Silicon）：用 `CONDA_OVERRIDE_OSX` + mamba dry-run 判断 bioconda 包是否可解，实机不测（标"未实测"）。
- Windows：只走 WSL2/Docker，说明即可。

### 5.6 不依赖 NCBI 的质量检查（后期，暂缓）
用户 2026-10-20：**目前先以 NC_ 注释为准**。主指标 = 与 NCBI 的一致性（§5.1）；§5.2 中 PCG 翻译、table2asn 两项照做。下列其余检查放到后期：
- PCG 翻译：内部终止、移码、起始/终止密码子合法、长度与同基因近缘种中位数之比；
- tRNA：二级结构得分、反密码子与氨基酸一致、22 个 tRNA 的种类齐全度（不强制 22 个）；
- rRNA：长度与近缘种比；
- 基因顺序：与同科/同目 RefSeq 的基因顺序比较，标出孤立的重排（多为注释错误而非真实重排——需查证）；
- table2asn ERROR/REJECT 数。
后期启用时，报告同时给两套数字，两者矛盾的记录优先人工查。
- 可选后期：A 级（有 RNA-seq）记录用 SRA 转录组 reads 比对验证基因边界（线粒体多顺反子转录、tRNA 间隔切割模型），量大，第一轮不做。

## 6. 细胞器注释知识库

位置：`temp_scripts/Mitoz-annotate/knowledge/`（进 git）。

```
knowledge/
  INDEX.md                 # 总目录 + 每条结论的状态（已确证/未定/推测）
  tools/<tool>.md          # MitoZ, MITOS2, MFannot, MiTFi, ARWEN, ARAGORN, tRNAscan-SE, MitoFinder, GeSeq, MitoAnnotator, table2asn…
                           #   版本、算法要点、源码关键位置(file:line)、默认参数、已知 bug/issues、局限、引用 DOI
  topics/<topic>.md        # 遗传密码与起止密码子、tRNA 命名与反密码子、不完整终止密码子、intron 类型与边界、
                           #   定向与起点、重叠基因、NCBI 提交规则、类群特有现象（如刺胞缺 tRNA、扁形动物 nad 结构）
  benchmark_findings.md    # 每轮 benchmark 暴露的问题 → 原因 → 修复 commit
```

- 每条结论：出处 + 软件版本 + 查阅日期；没找到依据的写"未确证"。
- 来源：本机已装各软件源码、GitHub 仓库与 issues、论文全文、官方文档。
- 以后版本升级只需更新对应 tools/*.md 并查看 issues 增量。

## 7. 优化循环

1. 在开发集上跑全部对比对象 → 评估 → 错误汇总表。
2. 按错误类型聚类；每类查知识库/源码找原因（证据先行，不猜）。
3. 修复本流程；每个修掉的错误加一条回归检查（`tests/` 或 `modules/genbank/tests/check_mitoz.py`），全部 PASS。
4. 重跑开发集，对比上一轮；用户提出的新需求/纠正写进 REQUIREMENTS.md。
5. 默认流程（REQUIREMENTS #38 是用户定的）：benchmark 显示另一组合更好时，我写出证据和建议，用户确认后再改默认；测试集运行前锁定默认。
6. 停止条件：开发集上没有可归因于本流程的系统性明显错误，或剩余问题需要用户决策（汇总后交用户）。
7. 定稿后测试集跑一次，出论文表。

## 8. 交付物

- `benchmark/` 新增：抽样脚本、运行脚本、评估脚本、报告生成脚本、冻结清单、`adjudication.tsv`。
- 报告：准确性表（总体/按门/按证据等级/按特征类型）、时间表、安装表，写入 README 与 `benchmark/README.md`；可选导出 Excel（用户要时）。
- 知识库 `knowledge/`。
- 修复的 commit + 回归检查；REQUIREMENTS.md 新条目。

## 9. 约束

- NCBI E-utilities 限速（无 API key 3 次/秒）。
- 机器 16 核；MitoZ 每条约数分钟，benchmark 运行时间以小时计，后台跑并分批记录进度（中断可续）。
- 子代理：检索/阅读用 sonnet，机械活 haiku，提示词写明禁止再开子代理、逐项写文件。
- 磁盘 /mnt/n 剩余约 800 GB，足够。

## 10. 我替你做的决定（可改）

- 总量约 250 条、dev/test 1:1、每门配额（§3.1）。
- 证据等级用关键词规则识别（§3.2）。
- 对比对象列表，MitoFinder 视可装性纳入（§4）。
- 匹配阈值：重叠 ≥50%、"明显错误"坐标阈值 30 nt（§5）。
- 知识库放在 Mitoz-annotate 仓库内（§6）。

## 10b. 审阅后补充的决定（我的判断，可改）

- **参考库循环**：MITOS2 refseq89m、MitoZ 的模型和我们的 `models/` 都来自 RefSeq，自注释会虚高。抽样时记录每条记录的 RefSeq 收录日期；报告单列"晚于 refseq89m 截止"子集；支持留一法的工具（mito_intron.py `--exclude_own_species`）用留一法。
- **输入公平**：所有工具都拿到用户能知道的信息——遗传密码（按分类群，即 NCBI transl_table）、类群；环状/线性取 NCBI 拓扑。MitoZ 不支持的类群：MitoZ 单跑记为"不支持"（覆盖率指标），不计入准确率；本流程在这些类群上的行为作为优化对象记录。
- **基因组结构**：线性 mtDNA（水母类）、多染色体（虱类）、非常规起点都纳入，作为"结构压力"子集单独报告；评估前把定向后坐标换算回 NCBI 原坐标。
- **数据切分**：dev/test 按**属**切分（同属不跨两集），防近缘种泄漏；论文只报总体和大类群数字，按门数字仅作描述。
- **真值来源**：从 COMMENT/参考文献记录 NCBI 注释所用方法（如 "annotated with MITOS"），按方法分层报告，避免偏向某工具；A 级子集太小时只描述不下结论。
- **知识库顺序**：核心工具（MitoZ、MITOS2、MFannot、MiTFi、ARWEN、ARAGORN、tRNAscan-SE、table2asn、MitoFinder）在第一轮 benchmark 前先建；其余工具和专题按 benchmark 暴露的问题补。

## 11. 留给实施者

脚本具体拆分、统一基因命名表的实现、报告格式细节、并行调度方式。
