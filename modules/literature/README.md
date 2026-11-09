# literature 模块 — 分类文献本地全文库

文献库 (corpus) 跨项目共享, 不属于某个类群. 配置: `config/literature.json` (默认见 `litdb.py` DEFAULTS).

| 步骤 | 命令 | 做什么 |
|---|---|---|
| 01_inventory | `python3 yzz.py literature 01 polychaeta` | 遍历文献目录 (只读), PDF 逐页取文字层; docx 整篇; 无文字层页标 pending |
| 03_discover | `python3 yzz.py literature 03 polychaeta` | 全盘 PDF 清单 (discovery/pdfs_*.tsv) 去重 + 多毛类相关性打分 -> candidates.tsv |
| 04_reocr | `python3 yzz.py literature 04 polychaeta` | 修 QC 问题: 语言误判重做 / 低置信旋转重做 / 乱码文字层重 OCR; 旧文本存 page_alt |
| 05_ingest | `python3 yzz.py literature 05 polychaeta` | 03 判 include 的库外 PDF 原地引用入库 (relpath=绝对路径, folder=external), 之后跑 02 |
| 06_triage | `python3 yzz.py literature 06 polychaeta rules` / `merge` | 03 判 review 的候选: 规则排除 -> 子代理读首页判定 -> 合并进 candidates.tsv, 再跑 05 |
| 07_fts | `python3 yzz.py literature 07 polychaeta build` / `search '<查询>'` | FTS5 全文检索 (西文按词, 中日文 trigram); pages 改动后重跑 build |
| 08_names | `python3 yzz.py literature 08 polychaeta genera` / `index` | 学名索引 (需 WoRMS 环节动物属名表); 暂缓 (2026-10-21) |
| 09_rescan | `python3 yzz.py literature 09 polychaeta` | 修 03 漏判: exclude 中扫描件/长文献全书均匀抽 6 页重判; 文件名「属 种 命名人, 年份」也计入 |
| 10_dossier | `python3 yzz.py literature 10 polychaeta retrieve "<种>" [--rules 规则.md]` / `merge "<种>"` | 物种档案: WoRMS 名称 -> 检索 -> 子代理按 DOSSIER_PROMPT.md 逐篇抽取 -> Excel |
| 11_cn_names | `python3 yzz.py literature 11 polychaeta build` / `lookup <名称>` | 中文学名知识库: 刘瑞玉 2008《中国海洋生物名录》全门类 3.2 万名称 + 异名 -> cache/cn_names.sqlite; 学名译中文必须先查 |
| 12_library | `python3 yzz.py literature 12 polychaeta plan` / `copy` / `add` / `replan` | 统一文库: 库外文献复制到 <backup>/文库/<科>/, 按正文科名/属名定科; 原文件不动, docs.relpath 改指新位置 (原路径 orig_path) |
| 13_zh_reocr | `python3 yzz.py literature 13 polychaeta detect` / `latin` / `redo` | 中/日文扫描书被按英文 OCR -> 抽样按不同汉字种数判中文后重做; latin: 知网文字层缺拉丁学名/数字 -> 补 OCR |
| 14_search | `python3 yzz.py literature 14 polychaeta find 溪沙蚕属 --region 中国` / `merge` | 按类群查文献 (WoRMS 异名 + 名录中文名 + cache/cn_alias.tsv 历史译名); 区域判定交子代理 (SEARCH_REGION_PROMPT.md) |
| 15_biblio | `python3 yzz.py literature 15 polychaeta auto` / `prev` / `pack` / `merge` | 文献映射表: DOI->Crossref, 题名->Crossref, 用户旧映射, 其余子代理 (BIBLIO_PROMPT.md) -> 文库/文献映射表.xlsx |
| 16_refresh | `python3 yzz.py literature 16 polychaeta` | 全盘增量刷新 (PDF + 知网 caj/kdh/nh), 新文件打分追加到 candidates |
| 02_ocr | `python3 yzz.py literature 02 polychaeta` | pending 页 tesseract OCR (自动判语言, 裁边重试); 可中断续跑; 后台长跑 |

数据: SQLite `/root/yzz-literature/polychaeta.db` (表 `docs`, `pages`), 每步结束备份到 `/mnt/n/多毛类文献库/`.
`pages.source`: pdf (原文字层) / ocr / docx / pending. `quality` = 像单词的 token 占比 (低 = 乱码文字层); `ocr_conf` = tesseract 平均置信度.

后台跑 OCR: `setsid nohup nice -n 10 python3 modules/literature/02_ocr.py polychaeta --workers 14 > /root/yzz-literature/02_ocr.log 2>&1 &`

回归检查: `python3 modules/literature/tests/check_literature.py` (改完脚本必须全 PASS)
