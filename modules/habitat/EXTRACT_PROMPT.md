# 抽取规则：非海洋多毛类物种记录（给 sonnet 子代理）

禁止再调用 Agent 开子代理。每处理完一篇就把结果追加写入输出文件，并把该篇 id 追加到 done_ids 文件。
临时脚本放在派发时指定的独立子目录（并行子代理共用一个目录会互相覆盖，2026-10-10 实例）。
审稿意见、决定信、作者回复等非正文条目不抽取，只记 done_ids。

输入：`extract/todo_N.tsv`（id, doi, year, title, venue, abstract, decision, reason）
输出：
- `extract/found_N.tsv`（制表符分隔，首行表头，列见下）
- `extract/done_ids_N.txt`（每行一个已处理的 id，含无记录的文献）

读取顺序：先读摘要；摘要不足以判断时，按 DOI 打开开放全文（publisher 页面、PMC、Zootaxa/ZooKeys/BHL 免费页），
本地 PDF 可在 `/mnt/n/溪沙蚕属-review/library/` 下按作者/年份查找。拿不到全文就只用摘要，confidence 记“待核”。

收录条件（同 Glasby et al. 2009 口径，只收多毛类，不收寡毛类和蛭类）：
文献中明确报道某个多毛类物种出现于淡水（河、湖、泉、洞穴、地下水、潜流带、植物积水）、内陆咸水湖或内陆海、
或可耐受淡水的低盐河口/潟湖（≈<5 psu），或陆生湿土。纯海洋记录不收。

列：
| 列 | 内容 |
|---|---|
| species | 文中使用的学名（不含作者），原样 |
| authority | 作者, 年份（文中有则填） |
| habitat_cn | 纯淡水 / 半盐水 / 均可 / 陆生（判定见下） |
| habitat_evidence | 支持生境判定的原文短句（英文原文，≤40 词） |
| salinity | 文中给出的盐度值或范围，原样；无则空 |
| locality | 地点（国家 + 水体），英文 |
| record_type | new species / new record / habitat evidence / revision |
| reference | 完整引文：作者 (年份) 标题. 期刊 卷: 页码 |
| doi | DOI |
| work_id | 输入行的 id，原样 |
| page | 证据所在页码（只看摘要则填 abstract） |
| confidence | 确证（全文或摘要明确写出物种+非海洋生境）/ 待核（推断或信息不全） |

habitat_cn 判定：
- 纯淡水：只记录于淡水（文中盐度 ≤0.5 psu，或明确写 freshwater 且无盐度值）。
- 内陆（athalassic）咸水湖、内陆海、盐泉：不论盐度高低都收，记“半盐水”（Glasby 2009 的 ST 类，例：Manayunkia athalassia 27–95‰）。“<5 psu”门槛只用于与海相通的河口、潟湖、港湾（thalassic）。
- species 栏只能填学名（属名 + 种加词，或文中原样的未定种如 “Namanereis sp. A”）；文献只给描述、没有学名时不写行，在 done_ids 记录即可。
- 盐度口径统一用 Venice 系统：有盐度值且 >0.5 psu 的内陆水体（含地下水、洞穴）记“半盐水”，不按“内陆即淡水”推断（2026-10-10 两个子代理对 N. pilbarensis 0.5–1.5 ppt 判定不一致）。
- 半盐水：只记录于内陆咸水湖/内陆海或低盐咸水，未见淡水记录。
- 均可：同时有淡水和咸水（河口、潟湖、海）记录，或文中称 euryhaline/freshwater-tolerant。
- 陆生：湿土、苔藓等陆地生境。

规则：
- 只依据文献原文，不凭印象补充。一个物种在一篇文献里只写一行；同一篇多个物种写多行。
- 未定种（sp.）只有在文中明确给出非海洋生境时才收，species 写成文中原样（如 “Namalycastis sp. A”）。
- 文献未报道任何符合条件的物种：不写 found 行，只记 done_ids。
- 完成后用 python 校验 found 文件列名与列数，回报一行：处理篇数、记录行数、确证/待核数。
