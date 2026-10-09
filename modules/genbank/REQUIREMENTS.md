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
