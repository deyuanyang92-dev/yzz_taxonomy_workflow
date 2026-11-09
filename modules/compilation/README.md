# compilation 模块 — 类群修订本地分类数据库 + 物种图文汇编

用途：属级修订的第二步（第一步是 `yzz.py worms all <属>` 加文献收集）。把每个种的全部描述文献（原始描述 L3、模式标本重描述 L2、非模式重描述 L4）本地化，做成结构化表，再为每个种生成一份图文汇编（pptx 和 pdf）。来源：Travisia 项目（P:/Travisia，脚本 85/87/88，2026-11-06 用户认可的排版），2026-11-08 在岩虫项目中通用化。

项目目录须有 `08_知识库/compilation.json`，格式见 `cfg.py`。所有命令的第 1 个参数都是项目目录。

| 步骤 | 命令 | 做什么 |
|---|---|---|
| 01_kb_pages | `python3 yzz.py compilation 01 <项目> [--workers 8]` | `pdf_dir` 下每个 PDF 逐页取文字（文字层 → 复用多毛类文库 OCR → tesseract），写入 `<Genus>_KB.sqlite`（表 files、pages、worms_names）；可续跑 |
| 02_locate | `python3 yzz.py compilation 02 <项目>` | 物种 × 文献每行 → 候选 PDF 页（WoRMS 印刷页 + 页码偏移；种加词容 1 字错；标题行），输出 `结构化/treatment_candidates.tsv` |
| （子代理） | 按 `CONFIRM_PROMPT.md` 把候选拆成 4 批 `confirm/in_K.tsv`，派 sonnet 子代理 | 逐行确认起止页、记述类型（description / short_description / record_only / key_or_table / mention / not_found / wrong_file）、是否检视模式 |
| （二次核对） | wrong_file、not_found，以及 comment 提到“另一个文件”的行 → `confirm/fix_in.tsv` → 子代理写 `confirm/fix_out.tsv` | 同一文献的分册或副本（V1/V2、`_2`/`_3`）放错时，改指正确的 PDF |
| 03_tables | `python3 yzz.py compilation 03 <项目>` | 生成 Travisia 同结构的 `work.csv`、`treatment.csv`、`name_usage.csv`；原文由 `account_text.py` 截取；输出 `03_待核.tsv` 和 `03_缺原始描述.tsv` |
| 04_decks | `python3 yzz.py compilation 04 <项目> [--species "X y"] [--force]` | 每个有 L1–L4 记述的分类单元 → `11_物种图文汇编/<种>/<种>_accounts_<日期>.pptx/.pdf` |
| 05_type_locality | `python3 yzz.py compilation 05 <项目>` | 原始描述（L3）原文导出为 `结构化/od_texts.tsv`，再调用 oworms（`--od-text`，步骤 10/14/16/17/19）：抽原文模式产地、复查 WoRMS 坐标。规则都在 oworms | `结构化/od_texts.tsv`；结果在 oworms `data/type_locality_verify.tsv` |

## 硬性要求（用户反馈，不得退化）

1. **每个种必须有原始描述**（2026-11-08）。WoRMS 没挂的原始描述（如 Monro 1934 的 *Marphysa sinensis*），用户给了 PDF 就写进 `结构化/supplement_accounts.tsv`，不能只复制到文件夹。每次 03 结束都看 `03_缺原始描述.tsv` 的计数，并向用户报告。
2. **汇编原文只放该种的记述正文**（2026-11-08 用户截图）：不得混入页眉页脚、比较表、图注、版权水印或下一个种。页码标记写成单独一行 `[p. 印刷页]`，由 typeset.py 显示为灰色分隔。只有图或表的页不留空标记。
3. **排版沿用 Travisia 认可版**：段落重排、run-in 标题加粗、学名斜体、左对齐、行距 1.1。不擅自改版式（UI 设计保护）。
4. 交付前必须：跑 `python3 modules/compilation/tests/check_account_text.py` 全部 PASS；对汇编 PDF 跑 `yzz.py zh check`；渲染 2–3 张原文页，用眼睛看过。

## 文件

- `cfg.py`：项目根目录和配置（属名、KB、物种文献表、PDF 目录、斜体属名、WoRMS 名称表）。
- `account_text.py`：记述原文截取。
  - 文字层：按版面过滤，去掉上下页边内的块，以及字号小于正文 0.8 pt 的块（表格、图注、脚注）；去掉 TABLE/FIGURE 开头的块；双栏按左右栏顺序排；块与块之间空一行作段落分隔。
  - OCR：去掉跨页重复的页眉行和纯页码行。
  - 扫描件带隐藏 OCR 文字层的页（如 Willey 1905、T&F 重排的 Monro 1934）：字号和分块都不可靠，所以不按字号过滤，改为按坐标把词重建成真实的行；竖排水印丢弃。
  - 标题行也认缩写属名，如 “N. corallina n.”（Kinberg 1865），须带 n. 或作者。
  - 块与块之间，只有上一块以句末标点结束时才分段。
  - 标题行：已知属名 + 种加词，或带作者、年份、n. sp.。截取终点是下一个种的标题行或科名小标题。
- `deck.py`：单种汇编（Travisia 85）。`enhance.py`：扫描页增强（87）。`typeset.py`：原文排版（88，带 verify() 逐字校验）。
- `kbshow.py`：子代理取页文字，`python3 kbshow.py <项目> "<文件名片段>" <页> [止页] [--scan 种加词]`。
- `CONFIRM_PROMPT.md`：子代理核对记述页的提示词。

## 已知限制

- 原文为 OCR 或文字层，未经人工校对，以页面原图为准。非英文记述暂无英译（Travisia 有）。图版未单独裁切，只放整页图。
- 文字层质量差的老扫描件（T&F 重排 OCR）句子会断行，reflow 能合并大部分。
