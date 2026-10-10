# genbank 模块需求

| # | 需求 | 来源 | 状态 |
|---|---|---|---|
| 1 | 下载某类群 NCBI 全部 GenBank (.gb) 记录 | 用户 2026-10-08 | ✅ 01（`--all`） |
| 2 | 整理为多基因表（标本 × 基因） | 用户 2026-10-08 | ✅ 02 g2t + 03 Excel |
| 3 | 使用并安装 gb2taxonomy (g2t) 到工作流 | 用户 2026-10-08 | ✅ `vendor/gb2taxonomy`，`pip install -e` |
| 4 | 可选择只下载线粒体基因 | 用户 2026-10-08 | ✅ `--mito`、`--mitogenome` |
| 5 | 可选择下载某个特定基因 | 用户 2026-10-08 | ✅ `--gene COI,18S,...`（genes.py） |
| 6 | 默认排除对多基因表无用的 WGS/mRNA/RefSeq 重复 | 实测 Priapulidae（WGS+mRNA >96%） | ✅ 可用 `--include-*` 放开 |
| 7 | 断点续传、失败重试、条数校验 | 优化原 download_entrez.py | ✅ |
| 8 | 凭证号写法不一致时合并同一标本 | 实测（COI_/28S_ 前缀） | ✅ 03 归一化，同物种内合并 + QC（v1，已被 #11 取代） |
| 9 | 每基因 FASTA 供比对建树 | — | ✅ 03 |
| 11 | 凭证号合并须由脚本独立完成，不依赖人工核对：按记录证据（论文/日期/坐标/采集人/地点）判定，矛盾不合并 | 用户 2026-10-08 | ✅ g2t 新步骤 reconcile (3b)，22 项测试；yzz 03 改为只读其结果 |
| 12 | 优化的脚本同步到 GitHub（deyuanyang92-dev/gb2taxonomy） | 用户 2026-10-08 | ✅ download / reconcile 进 g2t 包，`g2t-download`、`g2t-reconcile` |
| 10 | 与 WoRMS 有效名对照（organism → 有效名） | — | ⏳ 若项目已有 worms/names.tsv 时加入 |
| 13 | 18S/28S/ITS 按 g2t 原逻辑（DEFINITION 整条归类），暂不拆分区段 | 用户 2026-10-08 决定 | ✅ 保持；已知限制与备选方案见 vendor/gb2taxonomy/BUGS.md 与 CHANGELOG v0.01 |

g2t 版本：v0.01（包内 0.0.1，2026-10-08，GitHub release deyuanyang92-dev/gb2taxonomy v0.01）。
| 14 | 被过滤的记录列清单，不静默丢弃（不做序列切割） | 用户 2026-10-09 | ✅ g2t classify 输出 filtered_records.csv + record_status.csv；Excel Not classified 表列 status + reason（Priapulidae：filtered 30 / unmatched 22） |
| 15 | g2t v0.02：全面代码审查后修复（下载续传、凭证号核对、分类、提取、矩阵） | 2026-10-09 | ✅ GitHub release v0.02；yzz genbank all Priapulidae 结果不变 |
| 16 | 矩阵增加统一凭证号列（保留 GenBank 原样写法） | 用户 2026-10-09 | ✅ voucher_standardized / voucher_as_submitted / voucher_note（g2t organize + yzz 03） |
| 17 | 按 accession 或凭证号更新元数据（经纬度、物种名、出版物等），得到校正后矩阵 | 用户 2026-10-09 | ✅ g2t-curate；yzz genbank 04（模板 → 校正 → curated Excel + 修改记录） |
| 18 | NCBI 矩阵 Excel A + 用户自己整理的 Excel B（任意列名）→ 修正 A 中错误 → 新 Excel C | 用户 2026-10-09 | ✅ g2t-curate -m A -u B -o C（自动识别列，`--map` 覆盖）；yzz genbank 04 --table B 或把 B 放进 curation/ |
| 19 | 线粒体记录全部用 MitoZ 重新注释，统一 NCBI 注释不一致/注释缺失；直接用 Temp_scripts/Mitoz-annotate/batch_mitoz.py，不另建模块、不做基因名映射 | 用户 2026-10-09 | ✅ 05_mitoz；tests/check_mitoz.py（fake MitoZ） |
| 20 | batch_mitoz.py 内部映射中间文件（内部 ID FASTA、id_map.tsv、各轮 MitoZ 工作目录）跑完删除，最大化节约空间 | 用户 2026-10-09 | ✅ batch_mitoz.py `--keep_intermediate no`（默认）；问题样本日志留 failed_logs/ |
| 21 | intron 注释：MitoZ 注释不出 intron（MitoZ 缺陷，需备注并升级） | 用户 2026-10-09 | ✅ 已备注（--help、pipeline.log、README）；升级：mito_intron.py = MFannot intron 方法的 Python 移植（Exonerate + MFannot 边界规则 + Rfam 判型），batch_mitoz.py `--intron_fix auto` 自动调用；验证 Metridium COX1/ND5、Nematostella ND5 与 NCBI 完全一致，Platynereis 不变；tests/test_mito_intron.py + check_mitoz.py |
| 22 | 真实 MitoZ 端到端运行 | — | ⏳ 本机未装 MitoZ（无 conda 环境/可执行文件），需用户提供位置 |
| 23 | 升级 intron 注释：结合 MFannot 优势整合进 MitoZ 结果，用真 MFannot 比对验证 | 用户 2026-10-09 | ✅ mito_intron.py v2（MFannot 预筛 + 蛋白库 + 片段串联 + 边界规则；MitoZ 端点整合）。85 条动物 mt 基因组 / 138 intron：完全一致 97、≤6 nt 23、漏检 4（MFannot：65 / 13 / 53 漏检）；阴性 20 条 0 假阳性。已知：Polyplacotoma 反式剪接、9 nt 小外显子 |
| 24 | 移植 MFannot 小外显子（AnnotateMiniExonsByHMM）与反式剪接处理 | — | ⏳ |
| 25 | 下载太慢（Polynoidae 6110 条 → 6.7 GB/2 批，约 1 h/批）：查明并修复 | 用户 2026-10-09 | ✅ 原因：267 条 >100 kb 染色体/基因组 scaffold（单批 5.8 GB）。默认跳过 >100 kb（`--include-large` 保留），批 6 s，全类群约 3 min |
| 26 | 再次下载时跳过已下载数据；新数据合并进之前的整理，避免重复下载 | 用户 2026-10-09 | ✅ g2t `recstore`：记录按 accession.version 存共享库 `cache/genbank/nuccore_records.sqlite`，只下载库中没有的；换选择/重叠类群复用；旧版批文件自动导入；`gb/<tag>/changes.tsv` + `changes_history.tsv` 记录新增/更新/撤下（筛选条件变化单独标注）；并行请求 `-w 3`。Polynoidae 重跑：5858 条全部复用、0 下载 |
| 27 | 避免下载全基因组数据，但长度上限会误伤大线粒体基因组（>40 kb） | 用户 2026-10-09 | ✅ 长度上限只作用于核记录，细胞器记录不限长度；`--mitogenome` 去掉 30 kb 上限并收录 DToL “genome assembly, organelle: mitochondrion”（Polynoidae 18 → 31，Annelida 634 → 733）；失败批次二分定位单条记录 |
| 28 | 大数据量下载提速 | 用户 2026-10-09 | ✅ gzip 传输（7.7×小）、每请求 500 条（吞吐 2.5×）、60 s 超时快速重试、失败批二分、统计检索只在 --dry-run/--report；Nereididae 17,403 条从零 193 s（下载 69 s），全复用重跑 37–100 s |
| 25 | 下载后去重：同一序列的原始提交记录被人工校正为 RefSeq NC_ 后，保留 NC_、去掉原始提交；另去同号旧版本与完全相同序列；可单独输出 GenBank + FASTA | 用户 2026-10-09 | ✅ batch_mitoz.py 去重（COMMENT "derived from / identical to" + 序列相同时 RefSeq 优先），`batch_mitoz.py dedup -i gb -o out`；tests/test_dedup.py。环节动物：900 → 733（去掉 167 条被 NC_ 取代的原始提交） |
| 26 | 环节动物线粒体 intron 双向验证（NCBI 记录 ↔ 本脚本），含臭海蛹属 | 用户 2026-10-09 | ✅ 见 temp_scripts/Mitoz-annotate/README.md「环节动物」。NCBI 带 intron 特征的环节动物 mt 序列 11 条（臭海蛹属 8）；733 条去重基因组：NCBI 18 个 intron（3 特征 + 15 由 CDS join 推出），本脚本找到 15，漏 3（Decemunciger ND4 265 nt，MFannot 亦漏）；本脚本 21 个预测，13 个与真 MFannot 坐标完全一致，其余为 Decemunciger ND1（MFannot 判为 2 个 intron + 19 nt 小外显子）与 Chaetopterus 5 个约 300 nt 未定型（MFannot 未报，未确证）；5 条 NCBI 完全无注释的记录（含臭海蛹 T. forbesii）补出 6 个 intron，其中 5 个与 MFannot 坐标一致（Chaetopterus dewysee 的 1 个 MFannot 未报） |
| 29 | 根据 NCBI 时间信息增量下载；不用本地库也能只补缺（追踪下载时间） | 用户 2026-10-10 | ✅ `--since auto|日期`（Entrez [MDAT]，上次日期往前 3 天；撤下记录需不带 --since 的完整核对，manifest 记 last_full_check）；`--no-store`（批文件即唯一副本）。Polynoidae：since 21 s、46 条候选，结果与完整清单一致 |
| 27 | intron 注释满足 NCBI 提交要求、尽量复现 NCBI 注释、避免照抄 NCBI 错误 | 用户 2026-10-10 | ✅ mito_intron v5：table2asn 校验本脚本写入特征 ERROR 0（刺胞 105 条、环节 12 条）；/product、transl_except、3′ 端第一终止；证据门槛（内部终止/起始密码子/弱剪接/与标准基因冲突 → 不写入）；小外显子；NCBI 不一致处以同源蛋白与 ωG 规则判定（14 处本脚本更好）。tests 11 项 |
| 28 | 注释后无 cox1 时如何定方向 | 用户 2026-10-10 | ✅ batch_mitoz.py `--fallback_genes`（默认 cox2,cox3,cob,nad1，依次尝试；`none` = 不旋转），`oriented_by_fallback.txt` 记录；基因被拆成多段时取 5′ 最前一段；线性序列不旋转（v0.29 已有）。tests/test_orientation.py |
| 29 | 用真实 MitoZ 验证完整流程 | 用户 2026-10-10 | ✗ 取消：用户确认 MitoZ 本身注释不出 intron，intron 验证改用裸序列直接跑 mito_intron.py（见 #32） |
| 30 | 借鉴 MitoFinder 的 intron 注释优点 | 用户 2026-10-10 | ✅ 读源码确认：MitoFinder `--allow-intron` = BLASTX 片段按相似性合并（geneChecker_fasta_gaps.py:150），README 明言不搜 intron 边界，需近缘参考。吸收两点：`--ref_gb`（近缘 GenBank 的 CDS 作同源蛋白，基因名统一为 MFannot 写法；batch_mitoz `--intron_ref_gb`）、外显子总长 ≤ 3×蛋白长+33 的合理性检查。tests 18 项 |
| 31 | 收集 intron 训练模型再预测 | 用户 2026-10-10 | ⏳ 方案：NCBI 线粒体 intron（真核 18,929 条记录；动物 2,184；环节 11）质控后构建自有协方差模型与边界 PSSM，留一属交叉验证优于 v5 才替换；深度学习不适用（数据量） |
| 32 | 臭海蛹属 / 环节动物 intron 与 NCBI 双向验证；参考 MITOS2 等软件找最优方案 | 用户 2026-10-10 | ✅ 裸序列 741 条：写入 21 个 intron 与 NCBI 0 矛盾、全部高可信；NCBI 27 个中找到 16。MITOS2 实测不注释 intron（边界偏差至 174 nt、臭海蛹 cox1 漏外显子 1）；MitoFinder 仅相似性合并。吸收：Rfam group II D1–D4、Sellés Vidal 2025 group I 亚型模型（刺胞判型 54% → 79%）、起始密码子搜索与不完整 CDS。tests 19 项 |
| 33 | intron 注释提速、更稳健 | 用户 2026-10-10 | ✅ v7：两步判型（--rfam 快速 + 未定型再全灵敏度，判型结果不变）、每记录一次 cmsearch、小外显子两步搜索；超时、单记录出错隔离、--jobs 并行。单记录 6–14 倍提速，846 条验证 12 分钟，坐标与 v6 完全一致；tests 20 项（含异常输入测试） |
| 34 | 用户建议：按基因长度异常推断 intron | 用户 2026-10-10 | — 不另加：MFannot 预筛（同一蛋白命中相隔 ≥142 nt 的两个 ORF）已是更精确的同一思路；单看长度会被 MitoZ 只注一段外显子、天然长基因（NC_056771 ND5 724 aa）、移码误导；预筛仅 1–3 s，不是瓶颈 |
| 35 | 注释后单独校正 GenBank：PCG 与 12S/16S 边界，参考 Ghiselli et al. 2021（rstb.2020.0159）与用户 2026-05-01 设计文档（/mnt/n/codex/download_plublic/） | 用户 2026-10-10 | ✅ mito_curate.py（P1–P4、R1、R3；Fourdrilis 2018 准则 i–vi）。31 条真实 MitoZ 注释：PCG 3′ 与 NCBI 一致 211 → 254，12S 5′/3′ 5/2 → 17/15，16S 0/0 → 17/11，rRNA 重叠 44 → 0，table2asn ERROR 128 → 4（均为已标出的需人工检查基因）。tests/test_mito_curate.py 5 项。⏳ 软体动物数据验证；tRNA 多工具共识（设计文档 6.x）；rRNA 近缘参考末端修订（设计文档 5.2/7.1） |
| 36 | 校正流程内置评估：注释 → NCBI 评估 → 校正 → NCBI 评估 → 对比差异 | 用户 2026-10-10 | ✅ mito_curate.py 自动在校正前后运行 table2asn，输出 validation_compare.tsv（fixed/remaining/new）；31 条真实 MitoZ 注释：ERROR 128 → 4、WARNING 54 → 0，fixed 124、new 0 |

