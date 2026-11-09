# 任务：识别每个文件实际是哪篇文献（不看文件名对错，按内容判断）

禁止再调用 Agent 开子代理。每识别完 20 篇就把结果追加写入输出文件（中途中断不丢进度）。

## 输入
`/root/yzz-literature/biblio_batches/<批号>.jsonl`，每行一个 JSON：`doc_id, file（文件名，常常是乱的，如 create_pdf.pdf）, folder, pages（总页数）, pdf_meta, text（前 3 页文字，[p.N] 标页，可能有 OCR 错字）`。
用 Read 分段读（每次约 30 行）。

## 识别方法
- 以 **text 为准**：题名通常在首页上部；作者在题名下方；期刊名、年份、卷期常在页眉或页脚（如"暨南理医学报 一九八二年 第一期" → journal=暨南理医学报, year=1982, issue=1；"海洋科学集刊 No. 4 1963 年 8 月" → journal=海洋科学集刊, volume=4, year=1963）。
- 文件名、文件夹名只能作辅助线索。文件名可能是错的，与正文冲突时以正文为准。
- 中文文献：title、authors、journal 都照原文写中文；作者之间用分号分隔。俄文、日文同样照录原文。
- 几种特殊情况：
  - **整卷期刊或丛刊**（页数多，首页是期刊封面或目录，例如 Ann. Mag. Nat. Hist. 某卷）：doc_type=journal_volume，title 写"期刊名 卷号"，note 写目录里能看到的多毛类相关论文。
  - **论文合集或文选**（如《吴宝铃文选》）：doc_type=collection。
  - **专著、动物志**：doc_type=book。**学位论文**：doc_type=thesis（note 写学校）。
  - **单篇抽印本**：doc_type=journal_article。
  - **基金申请书、PPT、笔记等**：doc_type=other，并在 note 说明。
- **不得编造**：看不出来的字段留空；confidence 写 high（题名、作者、年份都在正文中清楚可见）、medium（有一项要推断）、low（主要靠文件名推测）。
- 正文有 DOI 就写上。

## 输出
`/root/yzz-literature/biblio_batches/<批号>.out.tsv`，表头严格为（制表符分隔，字段内不得有制表符或换行）：
`doc_id	authors	year	title	journal	volume	issue	pages	doi	doc_type	language	confidence	note`
- language：zh / en / de / fr / ru / ja / es / pt / it / la / other
- 每个输入的 doc_id 都要有一行。完成后核对行数，回报 ≤60 字：总数，high/medium/low 各几篇。
