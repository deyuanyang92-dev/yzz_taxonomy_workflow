# worms 模块 —— 调用 oworms

**2026-11-09 起，WoRMS 部分全部由 oworms 完成**（用户的独立软件，GitHub `deyuanyang92-dev/oworms`，开发副本 `/root/github/oworms`，已 `pip install -e`）。yzz 只调用，不再维护自己的抓取和解析代码。新功能写进 oworms，配测试。

```bash
python3 yzz.py worms all <Taxon>       # = oworms run <Taxon> --out <项目>/02_原始数据/worms [--od-text ...] + yzz 独有步骤 23
python3 yzz.py worms 14-19 <Taxon>     # 一段 -> oworms --steps
python3 yzz.py worms 23 <Taxon>        # yzz 独有: 物种 × 文献 (23_species_literature.py)
```

- 输出采用 oworms 原生结构：`<项目>/02_原始数据/worms/<Taxon>/data/*.tsv` 与 `reports/*.xlsx`。`lib/common.data_dir(taxon, "worms")` 指向 `data/`。
- 项目有 `08_知识库/结构化/od_texts.tsv`（由 `yzz.py compilation 05` 导出原始描述原文）时，自动加 `--od-text`，跑 oworms 10/14/17 原文复查。
- 步骤说明见 oworms README。下面是迁移前 yzz 自己那套步骤的说明，脚本已移到 `_legacy/`，只供参考。

---

## （旧）yzz worms 步骤说明

从 WoRMS 抓取并整理一个类群的名称、文献、模式产地、标本。需求见 [REQUIREMENTS.md](REQUIREMENTS.md)。

```bash
python3 yzz.py worms all Polynoidae      # 全部步骤（首次大科约 30–60 分钟，之后走缓存几分钟）
python3 yzz.py worms 06 Polynoidae       # 只重跑标本
python3 yzz.py worms 13-19 Polynoidae    # 地名标准化后重新合并导出
```

**两层结构**：提取层（01–07）只把 WoRMS 记录值完整照搬下来，不做解释；转换层（11–15）只读提取层，每个转换独立，可按需增删。需要新的转换（如别的地理格式）= 新增一个 1x 步骤，对指定列做转换，不动提取层。

| 层 | 步骤 | 输入 → 输出（`projects/<Taxon>/02_原始数据/worms/`） | WoRMS 数据面 |
|---|---|---|---|
| 提取 | 01_names | 类群名 → `names.tsv` | REST AphiaChildren / Record / Classification |
| 提取 | 02_sources | names → `sources.tsv` | REST AphiaSourcesByAphiaID |
| 提取 | 03_refs | sources → `refs.tsv`（含 `worms: <标签>` 全部原始字段） | 网页 sourcedetails |
| 提取 | 04_taxdetails | names → `taxdetails_fields.tsv`（页面全部区块记录）+ `taxdetails_items.tsv`（Type data / Descriptive notes 每一项：标本 sm、分布 dr、注释 note）+ `source_notes.tsv`（Sources 区每条文献的 page 与 **note**，如 "redescription from holotype"；REST 不提供 note） | 网页 taxdetails |
| 提取 | 05_distributions | names → `distributions.tsv`（全部分布记录，含非模式，字段原样） | REST AphiaDistributionsByAphiaID |
| 提取 | 06_specimens | 类群名 → `specimens.tsv`（全部字段 `worms: <标签>`） | 网页 speclist + specdetails |
| 提取 | 07_attributes | names → `attributes.tsv` + `vernaculars.tsv` | REST attributes / vernaculars |
| 转换 | 11_original_desc | names + sources + refs + source_notes → `original_descriptions.tsv`（重描述带 note） | — |
| 转换 | 12_type_locality | 04 + 05 + 06 → `types.tsv`（模式产地汇总，每列注明出处） | — |
| 转换 | 13_localities | types + specimens → `localities.tsv`（英文地名层级，AI，缓存 `cache/locality_norm.json`） | — |
| 转换 | 14_coordinates | types + specimens + localities → `coordinates.tsv` | Nominatim + Marine Regions；缓存 `cache/geocode_cache.json` |
| 转换 | 15_qc | 全部 → `qc.tsv` | — |
| 转换 | 16_species_literature | names + sources + refs + 11 + source_notes → `species_literature.tsv` + `04_处理数据/worms/<Taxon>_物种文献_<date>.xlsx`：**物种 × 文献**，按 Travisia 证据等级分级：L3 原始描述 / L2 模式标本重描述（note 或页码提到 holotype、lectotype 等）/ L4 重描述（未注明模式）/ 其他用途。有效名带命名人（区分同名异物）。现归他属的有效名（如 Paucibranchia bellii）的文献一并取（REST + 网页）；属级类群另查 AphiaRecordsByName 补漏网名称 | REST + 网页（缓存） |
| 转换 | 18_gaps | 全部 → `04_处理数据/worms/<Taxon>_WoRMS_gaps_<date>.xlsx`：每个名称缺什么（模式产地/坐标/低精度坐标/原始文献/页码/模式标本/水深）+ 空白填写列，供人工从文献补充 | — |
| 分布 vs 模式产地 | 21_distribution_check | 每条 WoRMS 分布记录（05 步，含网页上的来源文献）离模式产地多远：type locality / near ≤500 km / regional ≤2000 km / distant >2000 km / coarse region；每种判定 distant records / regional only / near TL only / TL record only / TL not located → 广布记录、待修订清单 | distribution_check.tsv, distribution_species.tsv（Excel 两张表） |
| 模式产地原文复查 | 22_tl_verify | WoRMS 模式产地/坐标逐种对照原始描述原文（需先跑 `yzz.py compilation 05 <项目>`）：agree ≤100 km / close ≤1000 km / conflict（>1000 km 或不在原文国家内）/ same country / OD only / OD no locality / no OD text。14 步在 WoRMS 无模式产地时改用原文，原文写明经纬度时优先于 WoRMS 近似点 | type_locality_verify.tsv（Excel 表 TL check vs OD） |
| 区域 | 20_region_subset | `--region china` → A 模式产地在该海域（WoRMS 记录或 High/Medium 坐标）/ B WoRMS 其他字段提及 / C 有该海域分布记录（非模式） | — |
| 导出 | 19_export | 全部 → `04_处理数据/worms/<Taxon>_WoRMS_<date>.xlsx` + `.md`。地理列三段并排：`WoRMS: `（WoRMS 记录值）→ `Std: `（转换）→ `coord_*`；另附原始数据表 | — |

**13 地名标准化**：若摘要显示 `TODO > 0`，Claude 按 [LOCALITY_PROMPT.md](LOCALITY_PROMPT.md) 给 `cache/locality_inbox/todo_N.json` 派 sonnet 子代理（每个 1–2 个文件），完成后运行 `yzz.py worms 13-19 <Taxon>`。

**缓存**：`cache/worms_cache.sqlite`（HTTP）、`cache/aphia_records.json`（名称记录）、`cache/locality_norm.json`（地名）——跨项目共用，重跑不重复联网、不重复花 token。

**回归测试（改任何脚本后必须跑，全部 PASS 才算完成）**：`python3 modules/worms/tests/check_polynoidae.py`、`check_ophelia.py`（需先 `worms all Ophelia --refresh`）；`check_travisia.py` 对照臭海蛹人工坐标表（2026-10-31 时已有 4 FAR + 2 MISSING，均为 10-09 前的坐标结果，待处理）。

**刷新缓存**：WoRMS 记录会被编辑修改（如年份、模式产地），缓存不自动过期。定稿数据加 `--refresh`：`python3 yzz.py worms all <Taxon> --refresh`（01 透传给 checklist，其余步骤的 HTTP 也重新联网；其他项目的缓存记录保留）。用户每指出一个错误，就加一条检查。

**区域筛选**：`python3 modules/worms/20_region_subset.py <Taxon> --region china` → A 模式产地在该海域（确定）/ B 待文献核对 / C 有该海域分布记录（非模式）。

**已知 WoRMS 坑**
- 记录的 `citation` = Taxonomic citation（数据库条目引用），不是原始文献 → 用 11 的 od_* 列。
- 标本清单的类群过滤参数是 `pid`；`tid` / `tName` 会被忽略而返回全库 13 万条。
- sourcedetails 页标签是 "Zoobank LSID"、"Full text"；specdetails 页是 "Depthshallow"、"Begindate"、"Note"（多行）。
- worms_taxonomy_app `checklist` 导出整个缓存库的名称 → 01 已按子树过滤。
- 模式产地可能按文献题目概括（Hartman 1965 *O. profunda* → "off New England"，原文 Bermuda）→ 15 QC `TL_FROM_TITLE`。
- 原始文献可能挂错（*O. denticulata* 挂 Verrill 1875 第 9 卷，该文无 Ophelia）→ 只能靠原文核对（REQUIREMENTS R5）。
- 原始组合在目标类群外（*Pseudophelia translucens*）→ 04 额外抓原始组合页，12 回退取模式产地。
- 环境标记偶有错误（Polynoidae 中 3 个深海种被标 freshwater）→ 15 QC 提示，不改原值。

**14 坐标优先级**（沿用 codex/WORMS 决策引擎 + 臭海蛹 01_build_type_localities.py 的 original/approximate 区分）：
manual_override（`coordinates_override.tsv`）> worms_specimen（Holotype>Lectotype>Neotype>Syntype>Paratype）> type_text_coordinates（严格解析，须带 N/S/E/W）> worms_type_distribution（地名中心点）> geocode_locality（Nominatim，限定国家）> geocode_water_body > worms_place_name（WoRMS 地名记录精确匹配 Marine Regions）> geocode_country_eez（国家 EEZ 中心点）> specimen_geounit > geocode_ocean_region（大洋/海区中心点）。只有无任何地理信息才留空；`coord_uncertainty_km` 给出模糊程度。有效名无证据时回退原始组合，不用次异名。`coord_precision`: original / approximate (…)，作图须区别显示。

**已修复的转换 bug（2026-10-08，均有回归检查）**
- Nominatim 无地名类结果时曾取第一条（匹配到酒店/商店）→ 只接受 place/natural/water 类。
- Marine Regions 国家级记录（Nation/Country）= 陆地中心 → 改用该国 EEZ；EEZ 用 WFS 按 territory1 / ISO3 精确查找（不猜 'Chinese'/'Ivorian' 等名称）。
- Marine Regions 部分记录东西界填反（West Indies 等 18 条）→ 取跨度小的解释；跨 180° 区域（新西兰 EEZ）正确处理。
- 区域中心点改用多边形内部代表点（边界框中心会落在弯曲 EEZ 的陆地上，如中国 EEZ → 江西）。
- 洲 / 淡水生态区 / TDWG 陆地分区不用作坐标。
- 近似坐标仍在陆地（城市中心、陆地区域）→ 移到最近海上约 5 km，原值留在 coord_raw_lat/lon。
- WoRMS 有只填纬度的分布记录 → 经纬度都有才算坐标。
