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
| 25 | 下载太慢（Polynoidae 6110 条 → 6.7 GB/2 批，约 1 h/批）：查明并修复 | 用户 2026-10-09 | ✅ 原因：267 条 >100 kb 染色体/基因组 scaffold（单批 5.8 GB）。默认跳过 >100 kb（`--include-large` 保留），批 6 s，全类群约 3 min |
| 26 | 再次下载时跳过已下载数据；新数据合并进之前的整理，避免重复下载 | 用户 2026-10-09 | ✅ g2t `recstore`：记录按 accession.version 存共享库 `cache/genbank/nuccore_records.sqlite`，只下载库中没有的；换选择/重叠类群复用；旧版批文件自动导入；`gb/<tag>/changes.tsv` + `changes_history.tsv` 记录新增/更新/撤下（筛选条件变化单独标注）；并行请求 `-w 3`。Polynoidae 重跑：5858 条全部复用、0 下载 |
| 27 | 避免下载全基因组数据，但长度上限会误伤大线粒体基因组（>40 kb） | 用户 2026-10-09 | ✅ 长度上限只作用于核记录，细胞器记录不限长度；`--mitogenome` 去掉 30 kb 上限并收录 DToL “genome assembly, organelle: mitochondrion”（Polynoidae 18 → 31，Annelida 634 → 733）；失败批次二分定位单条记录 |
| 28 | 大数据量下载提速 | 用户 2026-10-09 | ✅ gzip 传输（7.7×小）、每请求 500 条（吞吐 2.5×）、60 s 超时快速重试、失败批二分、统计检索只在 --dry-run/--report；Nereididae 17,403 条从零 193 s（下载 69 s），全复用重跑 37–100 s |
| 29 | 根据 NCBI 时间信息增量下载；不用本地库也能只补缺（追踪下载时间） | 用户 2026-10-10 | ✅ `--since auto|日期`（Entrez [MDAT]，上次日期往前 3 天；撤下记录需不带 --since 的完整核对，manifest 记 last_full_check）；`--no-store`（批文件即唯一副本）。Polynoidae：since 21 s、46 条候选，结果与完整清单一致 |
