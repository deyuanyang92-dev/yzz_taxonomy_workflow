# WoRMS 模块需求（yzz 团队）

整理自 2026-10-08 与杨德援的讨论。每条注明对应步骤；"状态"一列 ✅ 已实现 / ⏳ 计划中。
新增需求请直接在本文件追加，再改代码。

## 1. 总原则

| # | 需求 | 实现 | 状态 |
|---|---|---|---|
| G1 | **越全越好**：WoRMS 有的信息都要取，不只是名称和状态 | 01–06 覆盖 REST + taxdetails / sourcedetails / speclist / specdetails 四类网页 | ✅ |
| G2 | **缺失就空着**，不猜、不用别处数据补 | 所有步骤只写 WoRMS 原值；AI 标准化只依据 WoRMS 记录值 | ✅ |
| G3 | **分类学内容一律英文**（表头、地名、生境）；中文示例只是格式示例 | 全部 TSV / Excel 英文 | ✅ |
| G4 | **省 token**：脚本完成抓取与整理，Claude 只跑命令、读摘要，不读大表 | `yzz.py worms all <Taxon>`；每步 ≤5 行摘要 | ✅ |
| G5 | **单一职责小脚本**，形成本地工作流，可单步重跑 | 01–09 各一个脚本，TSV 进 TSV 出 | ✅ |
| G6 | 先学习已有脚本（`/mnt/n/codex/fetch_Worms_data`、`/mnt/n/codex/WORMS`）再写新代码 | 复用 worms_taxonomy_app 客户端与 type data 解析 | ✅ |
| G0 | **提取优先**：首先保证 WoRMS 信息完整、正确地原样提取（提取层 01–07，只照搬 WoRMS 记录值）；转换是独立步骤（11+），按用户需要对特定列增加转换函数；输出中WoRMS 记录值与转换结果并排显示（`WoRMS: ` / `Std: ` 前缀）（2026-10-08 用户强调） | ✅ |
| G8 | **模块边界**：本模块只用 WoRMS 信息；WoRMS 缺失的（如无模式产地记录）留空，由 literature 模块从文献补、在合并步骤合并。不从文献题目推断地点，不用非模式分布凑模式产地（2026-10-09 用户强调） | ✅ |
| G7 | 发现 WoRMS 自身数据错误要提示，但不改原值 | 09_qc | ✅ |

## 2. 名称与分类（01_names）

| # | 需求 | 状态 |
|---|---|---|
| N1 | 类群（科/属/…）下**全部名称**：各阶元，有效 + 非有效 | ✅ |
| N2 | **完整归属**：界→门→纲→亚纲→下纲→目→亚目→科→亚科→族→属→亚属 | ✅ |
| N3 | 非有效名**归到哪个有效名**，以及该有效名的科/亚科/属 | ✅ |
| N4 | 有效名下列出其**全部异名**；异名在表中紧跟有效名 | ✅ |
| N5 | 原始组合、是否转属（命名人带括号）、年份 | ✅ |
| N6 | 只保留目标类群子树（缓存库共用时不得混入其他类群） | ✅ |
| N7 | 有效属统计：每属有效种数、含异名的种级名称数、2000 年后新种数、属级异名 | ✅（10 Valid genera） |
| N8 | 按年代统计有效种描述数 | ✅（10 Decades） |

## 3. 文献（02_sources, 03_refs, 04_original_desc）

| # | 需求 | 状态 |
|---|---|---|
| L1 | **原始文献 = WoRMS "Original description"**（来源 use = original description）。WoRMS 记录的 `citation` 是数据库条目的 Taxonomic citation，**不是原始文献** | ✅ |
| L2 | 转属名称的原始文献挂在原始组合上 → 自动回退并注明 `od_taken_from` | ✅ |
| L3 | 原始文献**结构化拆分**：authors / year / title / journal / volume(issue): pages / **本种所在页码与图** / DOI / link / ZooBank LSID / open access / source ID —— 取自 sourcedetails 页分项字段，不靠正则猜 | ✅ |
| L4 | DOI 与链接分列（DOI 是 10.xxxx 标识，link 是期刊网页） | ✅ |
| L5 | 重描述（use = redescription）、新组合文献、异名来源文献 | ✅ |
| L6 | 全部文献清单（refs.tsv）供后续 literature 模块按 DOI/链接下载 PDF | ✅ 数据就绪；下载 ⏳ |

## 4. 模式产地与生境（05_type_data, 07_localities）

| # | 需求 | 状态 |
|---|---|---|
| T1 | 保留 WoRMS **WoRMS 模式产地记录**：taxdetails 的 Type locality 注释（含来源 From editor…）、type locality contained in、[from synonym]、(of 原始组合)、标本项；Descriptive notes（Distribution、Depth range、Habitat、Etymology…）全部逐项保留（04） | ✅ |
| T1b | **全部 Documented distribution**（含非模式分布记录）原样提取（05）；此前只保留模式分布，漏 269 个名称 721 条 | ✅ |
| T1c | 属性（体长、功能群、AMBI…）与俗名原样提取（07） | ✅ |
| T2 | 转换为易理解的层级：**Region（大洋/大洲）→ Country → State/Province → County/City → Locality**，另加 Water body、ISO | ✅（AI 标准化，结果全局缓存） |
| T3 | 标准化**只依据 WoRMS 记录值**；不确定留空；Confidence High/Medium/Low，Low 需人工核对 | ✅ |
| T4 | 不得用地名检索服务按文本自动匹配（实测把 Greenland 匹配到美国新罕布什尔州） | ✅ 已弃用 |
| T5 | 生境：WoRMS 环境标记（marine/brackish/freshwater/terrestrial）原样保留 | ✅ |
| T6 | 浅水/深水：由模式产地文本或标本水深推断，>200 m = Deep | ✅ |
| T7 | WoRMS 环境标记不合理时提示（如深海种被标 freshwater） | ✅（09 ENV_FLAG） |
| T8 | 模式材料（正模/合模等）摘要 | ✅ |

## 4b. 坐标（08_coordinates）

| # | 需求 | 状态 |
|---|---|---|
| C1 | 每个种级名称给出模式产地经纬度；**无明确坐标、只有地区信息的，转换为近似坐标** | ✅ |
| C2 | 证据分级取最佳坐标：人工修正 > 标本页 > 文本中坐标 > WoRMS 模式分布 > 地名地理编码 > 水体中心点；同级按模式类型排序（沿用 Ophelia 决策引擎） | ✅ |
| C3 | 每个坐标注明 basis / precision（original 或 approximate）/ confidence / 依据详情，近似坐标作图须区别显示（同臭海蛹 Fig. 1） | ✅ |
| C4 | 不得把站号等数字误解析为坐标（旧解析器把 "Stat. 105" 解析成经度 105）；度分秒须带半球字母 | ✅ |
| C5 | **坐标不能空着**：只有国家/海区/大洋级信息也要给模糊坐标（2026-10-08 用户以 *Benhamipolynoe antipathicola*「New Zealand」为例指出）。国家用 **EEZ 中心点**（落在海里，不用陆上国家中心）；WoRMS 地名记录先在 Marine Regions 精确匹配；再到标本 Geounit、大洋/海区中心点。全部标 approximate / Low，并给 `coord_uncertainty_km`。仅在 WoRMS 完全无地理信息时留空 | ✅ |
| C5b | 中心点用边界框自算并处理跨 180° 经线（Marine Regions 自带的新西兰 EEZ 中心点 71.7°E 是错的）；跨全经度的区域用 MR 自带中心点 | ✅ |
| C5c | 低可信度坐标进 QC（COORD_LOW），可在 coordinates_override.tsv 人工修正后重跑 | ✅ |
| C6 | 坐标落在陆地上的检查（land check，只警告不覆盖） | ⏳ |

## 5. 标本（06_specimens）

| # | 需求 | 状态 |
|---|---|---|
| S1 | **每个物种的 WoRMS 标本信息全部抓取**：馆藏号、博物馆、数量、保存方式、模式类型、Geounit、verbatimGeounit、经纬度（起止）、水深（浅/深）、日期、Note（多行）、Label、Phys. Location、Alternative code 等——页面有什么取什么 | ✅ |
| S2 | 清单来自 WoRMS Specimen 库（`speclist?pid=<AphiaID>&inc_sub=1` 翻页），保证完整（Polynoidae 485/485） | ✅ |
| S3 | **标本全部字段进总表**（Names 与 Species summary 的 spec_* 列：模式类型、馆藏号、机构、博物馆全称、数量、保存方式、Geounit、verbatimGeounit、起止经纬度、水深、起止日期、采集人、Note、Label、Phys. Location、Alternative code、Precision、链接）；多份标本用 ' \|\| ' 按同一顺序连接；有效名同时汇总挂在其异名/原始组合上的标本，spec_linked_name 注明 | ✅（10，2026-10-08 用户指出总表缺标本后补） |

## 6. 输出（10_export）

| # | 需求 | 状态 |
|---|---|---|
| O1 | 一个 Excel：Names / Species summary / Original descriptions / References / Specimens / Valid genera / Decades / QC / Notes | ✅ |
| O2 | 第一张表要全；非有效名灰底；可筛选 | ✅ |
| O3 | Notes 写明数据来源、覆盖率、口径 | ✅ |

## 7. 计划中

| # | 需求 |
|---|---|
| P1 | literature 模块：按 refs.tsv 的 DOI / link / BHL 下载原始文献 PDF 到 `01_文献/` |
| P2 | synonymy 模块：由 names + sources 生成规范异名录（Name Author, year: page, fig.） |
| P3 | maps 模块：模式产地图（按 MEOW realm 着色）、标本分布图 |
| P4 | 向 WoRMS 编辑报告 QC 发现的数据错误（人工） |
