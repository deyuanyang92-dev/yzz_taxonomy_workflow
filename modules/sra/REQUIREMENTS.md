# sra 模块需求

| # | 需求 | 来源 | 状态 |
|---|---|---|---|
| 1 | 自动获取类群的 SRA RunInfo，不再手动从网页下载 | 用户 2026-10-27 | ✅ 01（类群名） |
| 2 | 也可输入 SRR 号列表或网页下载的 RunInfo | 用户 2026-10-27 | ✅ 01 `--runs` / `--runinfo` |
| 3 | 补 metadata（参考 kingfisher annotate） | 用户 2026-10-27 | ✅ 02（efetch db=sra XML，同 kingfisher 做法） |
| 4 | 自动补分类信息（门–种），整合成系统总表 | 用户 2026-10-27 | ✅ 03 + 04 |
| 5 | 区分浅层 WGS / 全基因组 / 转录组等（NCBI 无此字段，后加工） | 用户 2026-10-27 | ✅ 04 `category_derived`，阈值 `rules.json`（0.5 / 10 Gb，设计方初值，可改） |
| 6 | 减少打开文件、手动整理 Excel | 用户 2026-10-27 | ✅ 04 Excel（Summary/Samples/各类型/Runs/QC） |
| 7 | 筛选后得到下载清单（旧 filter 脚本规则） | 用户旧脚本 | ✅ 05（默认按样本取前 3，`--per run` = 旧行为） |
| 8 | 不做下载，下载用 kingfisher 等现成工具 | 用户 2026-10-27 | ✅ 05 输出 run_list，摘要给出 kingfisher 命令 |
| 9 | 不按 BioProject 绕路、不用自由文本检索 | 实测 2026-10-27（见 README） | ✅ taxid 子树检索 + 条数核对 |
| 10 | 不硬编码 API key / 邮箱 | 旧脚本问题 | ✅ config/ncbi.json 或环境变量 |
| 11 | 失败不静默：条数核对、错误页/截断响应重试、查不到的 run 列出 | 旧脚本问题 + 实测（HTTP 414、截断响应） | ✅ eutils.py；长检索式 POST |
| 12 | 增量更新（只取上次以来新增） | 设计 | ⏳ 未做（Annelida 全量约数分钟） |
| 13 | 用同种/同属基因组大小估算覆盖度 | 设计 | ⏳ 未做 |
| 14 | WGS+PCR 不当作扩增子排除，只在 QC 提示 | 实测 Annelida 2026-10-27（多为 genome skimming / 基因组） | ✅ 04 |
| 15 | Annelida 规模（1.5 万 run、400+ 列）可在合理时间/内存内出 Excel | 实测 | ✅ 04 xlsxwriter 流式写（84 s / 0.4 GB） |
