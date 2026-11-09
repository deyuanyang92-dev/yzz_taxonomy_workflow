# 任务：判定每篇文献是否含 {region}海域（含台湾、香港、澳门）的 {taxon} 材料或记录

禁止再调用 Agent 开子代理。每判完 10 篇就把结果追加写入输出文件（中途中断不丢进度）。

## 输入
`{dir}/packets/<doc_id>.txt`：头部是文件名和首页前 800 字（据此识别作者、年份、题名），正文是学名出现处前后各约 400 字的片段，按 `=== PDF p.N ===` 标页。文本来自文字层或 OCR，可能有错字。
你负责的 doc_id 见任务说明。片段不够判断时，可以用 `sqlite3 /root/yzz-literature/polychaeta.db "SELECT text FROM pages WHERE doc_id=<id> AND page_no=<N>"` 读整页（只读）。

## 判定（只能选一个）
- **A**：本文自己有 {region}海域的该类群材料或记录。包括：在{region}采集的标本（新种、新记录、重描述、检视材料）；{region}的名录、动物志、调查报告中列出该类群；本研究在{region}采样并测序。
- **B**：只是引用。包括：引用他人的{region}记录或文献；比较表、系统发育表里列了{region}的 GenBank 序列（例如 "Namalycastis abiuma KU351089 China Lin et al. 2016"）；参考文献列表里出现{region}地名；讨论里提到某种"分布于中国"，但本文没有{region}材料。
- **C**：片段里的{region}地名与该类群无关，例如同页其他物种的产地，或者鱼类养殖地点等。

用户已确认的判例：Alves et al. 2020/2023/2024、Villalobos-Guerrero et al. 2024 只在序列表里引用了 Lin et al. 2016 的厦门序列，判 **B**；Wilson et al. 2023 的 China 只出现在参考文献里，判 **B**。

## 同时判定文献类型（type）
treatment（描述、重描述、新种、新记录、修订）| record（名录或调查中列出该类群）| molecular（测序、系统发育）| ecology（生态、养殖、污染等，非分类）| mention（仅提及）

## 输出
`{dir}/packets_out/<你的组号>.tsv`，表头严格为：
`doc_id	判定	type	作者年份	证据	证据页`
- 作者年份：从首页或文件名识别，如 "Wu et al. 1981"，识别不出就写文件名。
- 证据：≤30 词的原文引语（保留原语言），要能支持你的判定。A 必须引出{region}的产地或材料句。
- 每个 doc_id 都要有一行。完成后核对行数，回报 ≤80 字：A、B、C 各几篇，以及 3 篇最重要的 A。
