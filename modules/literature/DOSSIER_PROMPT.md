# 任务：从文献中抽取 *{species}* 的全部信息

禁止再调用 Agent 开子代理。每处理完一篇就立即写该篇输出文件（中途中断不丢进度）。

## 物种与名称
有效名与 WoRMS 异名：{names}
只抽取指向本种（或上述名称）的内容；同页同属其他种不抽，但比较句（"differs from T. forbesii in …"）中关于本种的陈述要抽。OCR 变体（错字、全大写、缩写属名）照常识别。若文献把别的种当作 T. forbesii（误鉴定）或作者认为该记录可疑，照录并在 note 写明。

## 输入
`{dir}/packets/<doc_id>.txt`：头部有 path（文件名常含作者年份）、pdf_meta；正文按 `=== PDF p.N ===` 分页（N 是 PDF 页序，不是印刷页码；印刷页码请从页眉页脚读出，写成 "印刷 p.375 (PDF p.380)"，读不出就只写 PDF 页）。文本是文字层或 OCR，可能有错字。
**性状定义与计数规则**：先完整阅读 `{rules}`，严格按它的代码、计数换算、证据等级、"原文没提到的性状不填"执行。

## 每篇输出三个文件（目录 `{dir}/out/`）
1. `<doc_id>.meta.json`：`{"doc_id", "citation"(作者 年份 题名 期刊卷页，尽量从正文解析), "short"(如 Jirkov2001), "lang", "record_type"(treatment=有描述/重描述 | checklist=名录或分布记录 | key=检索表 | comparison=比较表或比较段 | mention=仅提及 | not_this_species=实为他种或同名), "level"(L2-L5，按规则 §0), "name_used"(文中用的名称原样), "material"(产地、水深、标本数、是否模式；无则空), "summary"(≤60 字中文)}`
2. `<doc_id>.chars.tsv`：表头严格为
   `species	level	source_short	source_ref	pages	material	character	raw_quote	raw_value	raw_unit	conversion	value	certainty	note`
   species 一律写 {species}；raw_quote 逐字（≤40 词，保留原语言）；数值来自 OCR 时 certainty 至多"未确证"，除非同一数在文中多次一致出现。没有性状描述的文献只写表头。
3. `<doc_id>.syn.tsv`（异名录/引用条目，treatment 的异名录或名录中的引文）：表头
   `name_as_cited	author_year_cited	page_cited	locality_cited	note`
   没有就只写表头。

**属级陈述不是种的性状值**：属的特征描述（"Gattung …"、"Genus diagnosis"）、"除 X、Y 外本属各种均……"这类句子，只能记为 character=`note_general` 并在 note 写"属级陈述"，不得填入 Toc、br_first 等性状代码（试点 2026-10-21：Hartmann-Schröder 1996、Dauvin & Bellan 1994 各一例）。
引文 raw_quote 保持文字层原样（含 OCR 错字）；你认为的正确读法写在 raw_value/value，并在 note 写"OCR 校正：原文 X"。

分布记录（产地、水深、生境）即使只是名录，也写进 chars.tsv：character=`distribution`（产地）或 `tl_depth`（水深，按规则换算英寻）。

## 你的文献清单
见任务说明里给出的 doc_id 列表。全部完成后核对：每个 doc_id 都有 3 个文件。回报 ≤150 字：各 record_type 篇数、性状记录总行数、3 个你认为最重要的 treatment 文献。
