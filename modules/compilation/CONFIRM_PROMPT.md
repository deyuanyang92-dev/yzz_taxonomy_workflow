# 任务: 核对 Marphysa 物种记述页 (第 K 批)

工作目录: /mnt/p/岩虫属系统修订
输入: 08_知识库/结构化/confirm/in_K.tsv（每行 = 一个种名 × 一篇文献，脚本已给候选 PDF 页 pdf_start–pdf_end）
输出: 08_知识库/结构化/confirm/out_K.tsv（制表符分隔，首行表头；**每核完一行立即追加一行**，中断后可续：先读已有 out_K.tsv，跳过已做的 row）

## 取文字（只用这个工具，不要直接打开 PDF）
- 紧凑扫描（先用这个）：`python3 03_脚本/kbshow.py "<file 名片段>" <起页> <止页> --scan <种加词>`
  输出每页页眉 2 行、疑似分类标题行、种加词前后 2 行。
- 整页全文（需要确认边界或内容时再用）：`python3 03_脚本/kbshow.py "<file 名片段>" <页> [止页]`
- 页号都是 PDF 页（从 1 起）。文字多为 OCR，种名可能有错字（如 sanguinea → sangninea）。
- 候选页附近没找到，就扩大范围：先看 head_pages / hit_pages 列，再扫描全文件。

## 每行要判断
1. 该文献里关于这个种名（或其原始组合名、或作者当时用的名称）的“记述”（account）从 PDF 哪页开始、哪页结束。
   记述 = 从该种标题行（或正文中首次专门讨论该种的段落）到下一个种的标题行之前。
   该种分几处出现时（如正文加图版说明），只记主记述；图版或图注页写在 fig_pages。
2. content，取下列值之一：
   - `description`：有形态描述（新种描述、重描述、或记录中描述了形态特征，哪怕一段）
   - `short_description`：只有几句形态说明或鉴别特征（diagnosis / remarks 里谈到形态）
   - `record_only`：只有名称、产地、标本、文献，没有形态内容
   - `key_or_table`：只出现在检索表或比较表里
   - `mention`：只是顺带提到（引言、讨论、参考文献）
   - `not_found`：全文找不到该种
   - `wrong_file`：PDF 不是这篇文献（看首页作者、年份、题名）
3. 其他字段见下方表头。

## 输出表头（顺序固定）
row	pdf_start	pdf_end	printed_start	printed_end	name_as_printed	content	type_material	fig_pages	confidence	comment

- printed_start/printed_end：印刷页码（看页眉/页脚），没有就留空。
- name_as_printed：文中标题里的名称及作者，照原文抄（例：`Marphysa orientalis Treadwell, 1936`）。
- type_material：文中明说检视了 holotype、lectotype、syntype、paratype、neotype 时写哪一种；否则留空。
- confidence：high / medium / low。
- comment：一句话，≤30 词；不确定的地方写在这里。

## 规则
- 禁止调用 Agent 工具开子代理。
- 不要改 in_K.tsv 和任何其他文件，只追加 out_K.tsv。
- 同一 file 的多行一起做，减少重复扫描。
- 最后回报 ≤100 字：完成行数，各 content 计数，wrong_file 列表。
