# g2t 新增代码审查（41c45bc..HEAD，实际审到 9e5c642）

- 仓库：`/mnt/n/yzz-分类工作流/vendor/gb2taxonomy`（editable 安装，Python 3.13 / pandas 3.0.0 / Biopython 1.86）
- 范围：`git diff 41c45bc..HEAD -- src/ scripts/`
- 基线：`pytest tests` 236 passed（审查前）
- 所有复现脚本在 `/tmp/claude-0/-mnt-n------/0f3bff3e-0e88-466e-8774-d266b53421ea/scratchpad/review_new/`（`fake_entrez.py` 为离线 Entrez 替身，`test_dl_repro.py` 等）。除特别注明外，均已实际运行并复现。
- 联网仅用于核对 12S/16S 检索子句：6 次 nuccore esearch + 1 次 taxonomy esearch/efetch（未超 10 次）；download 的全部问题用 monkeypatch `g2t.download._call` 离线复现（`fake_entrez.py`）。仓库源码与 `02_原始数据` 均未改动（`git status` 干净）。
- 严重度：高 = 静默丢数据/错数据；中 = 特定输入下错误结果或与文档不符；低 = 边界/误导。

## 总览

| 编号 | 严重度 | 位置 | 一句话 |
|---|---|---|---|
| D1 | 高 | download.py:213 | 批文件只按记录数校验；记录集变化后复用旧批，新记录丢失、旧记录重复，且无任何提示 |
| D2 | 高 | download.py:149-152 | tag 不含 `--query` 内容和 `--include-*`/`--all`；不同检索共用目录并互相复用批文件 |
| D3 | 中 | download.py:207-212 | 批大小变大后遗留旧 batch_*.gb，下游读目录会重复 |
| D4 | 低 | download.py:185-194 | `--dry-run` 覆盖已有 manifest.json |
| D5 | 低 | USAGE.md:104 | "旧脚本参数相同"不成立：默认选择、输出位置、批大小已变 |
| R1 | 中 | reconcile.py:301-304 | ≥3 个同 organism+core 的互斥标本，新键 `_reconciled` 冲突被并成一个 |
| R2 | 中 | reconcile.py:279-291 | 传递合并绕过"同基因须强证据"规则 |
| R3 | 低 | reconcile.py:236-283 | 含多个 core 的分组可传递合并互相冲突的组 |
| R4 | 低 | reconcile.py:175 | 跨 180° 经线坐标距离算成 360° 冲突 |
| R5 | 低 | reconcile.py:53,83 | voucher_core 丢年份/前缀，`USNM 123456` 与 `123456` 配不上，与"acronyms stripped"不符 |
| R6 | 低 | reconcile.py:98,265 | `organism` 列缺失时按同物种处理 |
| R7 | 低 | reconcile.py:270 | 多匹配 gene_type（`coi,16s`）按原始字符串求交，漏判同基因 |
| R8 | 低 | reconcile.py:54 | clone/strain 优先级与 voucher 步骤相反 |
| A1 | 中 | __init__.py:23-52 | `g2t.reconcile()/download()` 等首次调用后被同名模块覆盖；README API 示例会失败 |
| C1 | 中 | classify.py:1353 | `g2t-classify` 命令行不产生 record_status.csv（文档称产生） |
| C2 | 低-中 | classify.py:1266 | record_status 读旧的 `_all` 文件，关 recheck 重跑同目录时状态错误 |
| C3 | 低-中 | classify.py:905 | 全部记录被过滤时 classify 以 `KeyError: 'gene_type'` 失败（既有缺陷） |
| C4 | 低 | classify.py:848 | `1,234 bp` 被当"长度缺失"丢弃；filtered 里 Length 为空 |
| P1 | 低 | _pipeline.py:188 | `--resume` 下 reconcile 选项变化被静默忽略 |

共确认 19 项（高 2、中 5、低-中 2、低 10）。

---

## 一、已确认的问题

### D1（高）download：批文件只按"记录数"校验，不核对内容 → 记录集变化后静默复用旧批，丢记录并重复

- 位置：`src/g2t/download.py:213`（`if f.exists() and _n_records(...) == len(ids)`），与 `:196-206`（accessions.tsv 重建）。
- 现象：accessions.tsv 重建（NCBI 新增记录使 count 变化）后，批文件 `batch_000k.gb` 只要记录条数等于新 `ids` 长度（满批 200 条必然相等）就被当作"已完成"跳过，但其内容是旧列表对应的。esearch 默认新记录排前，所以新增 3 条会使每个批次整体平移：新记录不会被下载，同时出现重复。README/模块文档声称"re-running the same command skips finished batches"，用户会以为数据完整。
- 复现（离线，`test_dl_repro.py::test_D2_growing_db_shifts_batches`）：
```python
fake.default = accs("AB", 400)                       # 第一次：400 条
download("Priapulidae", out, DownloadOptions())
fake.default = accs("ZZ", 3) + accs("AB", 400)       # NCBI 在列表头部新增 3 条，共 403
res = download("Priapulidae", out, DownloadOptions())
```
- 实际输出：
```
expected 403 records; skipped batches: 2 downloaded: 1
records in dir: 403 unique: 400 missing vs list: ['ZZ000001.1', 'ZZ000002.1', 'ZZ000003.1']
```
  （目录里 403 条但只有 400 条唯一，3 条新记录缺失、3 条旧记录重复；`failed=0`，退出码 0。）
- 修复建议：跳过批文件前，核对批文件中的 VERSION/ACCESSION 集合与 `ids` 完全一致（解析 `^VERSION\s+(\S+)`）；或把 accessions.tsv 的哈希写入 manifest，列表变化时清空旧 batch_*.gb；同时校验每条记录以 `//` 结束（见"检查过未发现"里的截断说明）。

### D2（高）download：输出子目录 tag 不区分 `--query` 内容和 `--include-*` 选项 → 不同检索共用目录并复用对方批文件

- 位置：`src/g2t/download.py:149-152`（`tag.append("custom")`；`include_wgs/mrna/refseq` 不进 tag）+ `:213`（同 D1 的只比记录数）。
- 现象：`--query 'Russia[Country]'` 与 `--query 'Norway[Country]'` 都落在 `<out>/custom/`；`--include-wgs` 与默认都落在 `<out>/markers/`。第二次运行时 manifest.json 被覆盖成新检索式，但满批文件（200 条）被当作已完成，目录里混有两次检索的记录，且 manifest 与内容不符。
- 复现（`test_D1_query_change_same_tag_reuses_old_batches`、`test_D4_flags_not_in_tag`）：
```python
fake.db = {"Russia": accs("RU", 400), "Norway": accs("NO", 450)}
download("Priapulidae", out, DownloadOptions(query="Russia[Country]"))
res = download("Priapulidae", out, DownloadOptions(query="Norway[Country]"))
# D4: download(..., DownloadOptions()) 然后 download(..., DownloadOptions(include_wgs=True))
```
- 实际输出：
```
tag: custom | skipped batches: 2 | downloaded: 1
accessions in dir after the Norway run: RU = 400 , NO = 50       # Norway 检索拿到 400 条俄罗斯记录
tags: markers markers | second run skipped 2 of 2
WGS records present: 0 of 400                                    # --include-wgs 完全没拿到 WGS
```
- 补充（`build_query` 直接打印）：`--mito` 与 `--all --mito` 同为 `mito`；默认、`--include-wgs`、`--include-refseq` 同为 `markers`；任何 `--query` 都是 `custom`。
- 修复建议：tag 中加入检索式短哈希（如 `custom-<sha1(query)[:6]>`）并把 `include-wgs/mrna/refseq` 写进 tag；复用旧文件前比对 manifest.json 中的 `query`，不同则拒绝或要求 `--tag`；配合 D1 的内容核对。

### D3（中）download：批大小变大/总数变小后，多余的旧 `batch_*.gb` 不删除 → 下游 g2t 读目录时记录重复

- 位置：`src/g2t/download.py:207-212`（只写 `range(nb)` 的文件，不清理 `batch_{nb+1..}`）。
- 现象：先 `-b 100`（4 个批文件），再 `-b 200`（应只有 2 个）：`batch_0003/0004.gb` 残留，目录里记录总数 600 而唯一仅 400；`g2t -i <tag目录>` 会把它们全读进去。
- 复现（`test_D3_stale_batches_when_batch_size_grows`）：
```python
fake.default = accs("AB", 400)
download("Priapulidae", out, DownloadOptions(batch=100))
download("Priapulidae", out, DownloadOptions(batch=200))
```
- 实际输出：
```
batch files: ['batch_0001.gb', 'batch_0002.gb', 'batch_0003.gb', 'batch_0004.gb']
records: 600 unique: 400
```
- 修复建议：下载完成后删除 `batch_{nb+1:04d}` 及之后的文件，或批大小/列表变化时清空 tag 目录内的 batch_*.gb。

### R1（中）reconcile：同一 organism + 同一 voucher_core 下出现 ≥3 个互不相容的标本时，新键冲突，后两个被静默并成一个

- 位置：`src/g2t/reconcile.py:301-304`
```python
new_key = f"{...organism...}_{core}"
if new_key in used_keys - member_keys:
    new_key += "_reconciled"          # 只加一次后缀，且不再检查加后缀后的键是否已存在
used_keys.add(new_key)
```
- 现象：第 1 个合并标本得到 `Org_core`，第 2 个得到 `Org_core_reconciled`，第 3 个也得到 `Org_core_reconciled`（已被第 2 个占用），于是 `df[key].isin(...)` 之后在 organize 里第 2、第 3 个标本被并成同一行。三者之间本来有"采集日期冲突"，正是 reconcile 要避免合并的情形。
- 触发条件：`voucher_core` 去掉了年份与机构（`MNHN-IU-2012-1234` / `MNHN-IU-2013-1234` / `MNHN-IU-2014-1234` 的核心都是 `1234`，见 R5），同物种的多个馆藏号核心相同时即会触发。
- 复现（`test_rec_repro.py::test_R1_three_disjoint_specimens_same_core_collide`）：
```python
rows = []
for yr in (2012, 2013, 2014):
    v, d = f"MNHN-IU-{yr}-1234", f"{yr}-06-01"
    rows.append(row(f"C{yr}", f"Pc_COI_{yr}", v, "coi", collection_date=d))
    rows.append(row(f"N{yr}", f"Pc_28S_{yr}", v, "28s", collection_date=d))
out, rep = reconcile_dataframe(pd.DataFrame(rows))
```
- 实际输出：
```
ACCESSION gene_type species_voucher_g2t                species_voucher_new match_basis
    C2012       coi         Pc_COI_2012            Priapulus_caudatus_1234  reconciled
    N2012       28s         Pc_28S_2012            Priapulus_caudatus_1234  reconciled
    C2013       coi         Pc_COI_2013 Priapulus_caudatus_1234_reconciled  reconciled
    N2013       28s         Pc_28S_2013 Priapulus_caudatus_1234_reconciled  reconciled
    C2014       coi         Pc_COI_2014 Priapulus_caudatus_1234_reconciled  reconciled
    N2014       28s         Pc_28S_2014 Priapulus_caudatus_1234_reconciled  reconciled
distinct specimens after reconcile: 2 (expected 3)
```
- 修复建议：`while new_key in used_keys - member_keys: new_key = f"{base}_reconciled{n}"`（计数递增），并在 `used_keys` 中同步登记。

### R2（中）reconcile：传递合并绕过"同基因双方须有强证据"规则，一个标本里出现两条同基因序列

- 位置：`src/g2t/reconcile.py:270-276`（重叠基因检查只在两两比较时做）与 `:279-291`（并查集合并时只检查 `conflict_pairs`，不检查合并后成员间的基因重叠）。
- 现象：A(coi) ~ B(28s) 强证据、B(28s) ~ C(coi) 强证据，而 A 与 C 都含 coi 且只有中等证据（报告里 A–C 明确写"not merged: same gene in both groups, strong evidence required"），但经 B 传递后 A、B、C 仍合成一个标本，同一标本有两条 coi。文档（模块头 §3）说"If both groups already contain the same gene, only strong evidence can merge them"，实际被绕过。
- 复现（`test_R2_transitive_merge_bypasses_same_gene_rule`）：
```python
A = row("A1","kA","WS399","coi", collection_date="2019-06-12", collected_by="Smith", geo_loc_name="Russia: White Sea")
B = row("B1","kB","WS399","28s", collection_date="2019-06-12", lat_lon="66.5 N 33.1 E")
C = row("C1","kC","WS399","coi", lat_lon="66.5 N 33.1 E", collected_by="Smith", geo_loc_name="Russia: White Sea")
out, rep = reconcile_dataframe(pd.DataFrame([A, B, C]))
```
- 实际输出：
```
group_a group_b                                evidence                                                       decision
     kA      kB                            strong: same collection date                                  merged (high)
     kA      kC     moderate: same locality; same collector not merged: same gene in both groups, strong evidence required
     kB      kC                         strong: same coordinates                                  merged (high)
A1 / B1 / C1 全部得到 species_voucher_new = Priapulus_caudatus_WS399   （期望 2 个标本）
```
- 严重度理由：真实 Priapulidae 数据（496 行）上未触发（合并后每个标本×基因最多 1 条），但规则被绕过时不会有任何提示。
- 修复建议：合并前对 `members[ra] × members[rb]` 追加检查——两个簇的基因集合有交集时，要求这两簇之间存在一条 strong 边，否则跳过并在报告里标注；或把"同基因"视为 `conflict_pairs` 的一种。

### R3（低）reconcile：并查集冲突检查只覆盖"同 core 的两两比较"，含多个 core 的分组可把互相冲突的组传递合并

- 位置：`src/g2t/reconcile.py:236-238, 251-274`（`cores[core]` 只在同 core 内两两比较并写入 `conflict_pairs`）与 `:283`。
- 现象：分组 B 内部各行 raw voucher 不同（core=WS399 与 core=WS500），A 与 B 共享 WS399、B 与 C 共享 WS500，则 A 与 C 从未被比较，`conflict_pairs` 中没有它们。A（2001 年 / 挪威）与 C（2019 年 / 俄罗斯）有明显的日期与国家冲突，却被并入同一标本。
- 复现（`test_R3_multi_core_group_hides_conflict`）：
```python
A  = row("A1","kA","WS399","coi", collection_date="2001-01-01", geo_loc_name="Norway: Oslo", Ref1Title="Paper X")
B1 = row("B1","kB","WS399","28s", Ref1Title="Paper X")
B2 = row("B2","kB","WS500","18s", Ref1Title="Paper X")
C  = row("C1","kC","WS500","h3",  collection_date="2019-06-12", geo_loc_name="Russia: White Sea", Ref1Title="Paper X")
out, rep = reconcile_dataframe(pd.DataFrame([A, B1, B2, C]))
```
- 实际输出：A1、B1、B2、C1 全部 `Priapulus_caudatus_WS399`；报告只有两行（WS399: kA–kB merged (high)；WS500: kB–kC merged (high)），没有 kA–kC 的记录。
- 严重度理由：真实数据 435 个分组中 0 个含多 core，仅在 voucher 步骤产出"一组多凭证"时触发。
- 修复建议：合并 ra、rb 时，对所有 `members[ra] × members[rb]` 现场调用 `compare_groups` 检查冲突（不依赖预先计算的 `conflict_pairs`）。

### R4（低）reconcile：坐标距离用平面欧氏距离，跨 180° 经线时把 0.02° 的两点算成 360° 冲突

- 位置：`src/g2t/reconcile.py:175`（`math.dist(x, y)`）。
- 现象：`50.0 N 179.99 E` 与 `50.0 N 179.99 W`（实际相距约 0.02°）被判为"coordinates 360.0 deg apart"冲突，阻止合并。（同时经度度数在高纬度不做余弦校正，仅是粗略阈值，不算 bug。）
- 复现（`test_R4_antimeridian`）：
```python
A = row("A1","kA","WS399","coi", lat_lon="50.0 N 179.99 E", collected_by="Smith", geo_loc_name="Russia: Kuril")
B = row("B1","kB","WS399","28s", lat_lon="50.0 N 179.99 W", collected_by="Smith", geo_loc_name="Russia: Kuril")
out, rep = reconcile_dataframe(pd.DataFrame([A, B]))
```
- 实际输出：`moderate: same locality; same collector | conflict: coordinates 360.0 deg apart -> not merged: conflicting metadata`
- 修复建议：`dlon = abs(x[1]-y[1]); dlon = min(dlon, 360-dlon)`，再 `math.hypot(x[0]-y[0], dlon)`。

### R5（低）reconcile：`voucher_core` 丢弃年份与馆藏前缀，不同年份的同序号凭证共享 core；而"ACRONYM 数字"与"纯数字"又配不上，与文档"collection acronyms stripped"不符

- 位置：`src/g2t/reconcile.py:53`（CORE 正则）、`:83-95`；模块文档第 6 行与 §1。
- 实际输出（`vc.py`）：
```
'MNHN-IU-2014-1234' -> '1234'     'MNHN-IU-2013-1234' -> '1234'      # 年份被丢，不同标本同 core（触发 R1）
'USNM 123456'       -> 'USNM123456'   '123456' -> '123456'             # 同一标本，两种写法不同 core，永远不会成为候选
'ZMUC_123456'       -> 'ZMUC123456'
'2019-123'          -> ''  'BMNH 2019.123' -> ''  'NHM 2019.1.2.3' -> ''   # 年份-序号型凭证全部被当作无 core（<4 字符）
'WS399 (holotype)'  -> ''  'WS399.' -> ''                              # 末尾有括号/句点 → 无 core，静默跳过
'WS399, WS400' / 'WS399/WS400' -> 'WS400'                              # 多个编号只取最后一个
```
- 影响：漏合并（'USNM 123456' vs '123456'）和跨年份误配候选（需另有证据才会合并）。均不会单独造成错误合并，但缺失的情形无任何报告。
- 修复建议：保留年份（`\d{4}[-_.]\d+` 作为整体）；core 同时生成"带前缀"和"仅数字"两个键用于候选配对；对末尾括号/标点先做 strip；多编号时每个编号各自作为候选键。

### R6（低）reconcile：`organism` 列缺失时静默按"同物种"处理，不同物种仅凭共享论文就会合并

- 位置：`src/g2t/reconcile.py:98-101`（`_vals` 对缺列返回空集）、`:258-268`（`oa != ob` 对两个空集为 False）、`:299`（organism 为空 → `"unknown"`）。
- 现象：输入没有 `organism` 列（或 `--organism_column` 写错；reconcile CLI 没有该参数，只能在 API 里设）时，所有候选对都被当作同一物种，核心相同、同一论文的 *Priapulus caudatus* 与 *Halicryptus spinulosus* 被合并为 `unknown_WS399`。模块文档声明"The same core in different organisms is reported, never merged"。
- 复现（`test_R6_no_organism_column_treats_all_as_same_species`）：
```python
A = row("A1","Priapulus_caudatus_WS399","WS399","coi", Ref1Title="Paper X")
B = row("B1","Halicryptus_spinulosus_WS399","WS399","28s", org="Halicryptus spinulosus", Ref1Title="Paper X")
out, rep = reconcile_dataframe(pd.DataFrame([A, B]).drop(columns=["organism"]))
```
- 实际输出：两行的 `species_voucher_new` 都是 `unknown_WS399`。
- 修复建议：`organism_column` 缺失时抛 `KeyError`/报错；或 organism 集合为空时视为"未知 → 不合并"。

### R7（低）reconcile：同基因重叠判断按原始字符串集合求交，多匹配 `gene_type`（如 `coi,16s`）与 `16s` 判为无重叠

- 位置：`src/g2t/reconcile.py:270`（`_vals(ga, "gene_type") & _vals(gb, "gene_type")`）。
- 现象：`classify` 对一条记录可输出逗号分隔的多个 gene_type（`multiple_matched.csv`），`coi,16s` 与 `16s` 交集为空，于是"同基因需强证据"规则不触发，中等证据即可合并。
- 复现（`test_R7_gene_overlap_compares_raw_strings`）：
```python
A = row("A1","kA","WS399","coi,16s", collected_by="Smith", geo_loc_name="Russia: White Sea")
B = row("B1","kB","WS399","16s",     collected_by="Smith", geo_loc_name="Russia: White Sea")
```
- 实际输出：`genes_a=coi,16s genes_b=16s  moderate: same locality; same collector -> merged (medium)`
- 严重度理由：Priapulidae 数据 gene_type 没有逗号值（`value_counts` 仅 coi/28s/18s/16s/h3/its1-its2/mtgenome），其它类群可能出现；另外 `mtgenome` 与 `coi` 也不判重叠（可能是有意）。
- 修复建议：先按 `,` 拆分再求交集。

### D4（低）download：`--dry-run` 也会创建输出目录并覆盖已有 manifest.json（日期、count 被改写）

- 位置：`src/g2t/download.py:185-194`（manifest 在 `if dry_run` 之前写入）。
- 现象：对一个已下载完成的 tag 目录再跑一次 `--dry-run`，manifest.json 的 `date`/`count` 被改成"今天/最新计数"，而目录里的 batch 文件仍是旧数据，可复现性记录与实际内容脱节。
- 复现（`test_dl_repro.py::test_D5_dry_run_overwrites_manifest`）：先正常下载 400 条并把 manifest 日期改成 2026-01-01，NCBI 增至 405 条后 `download(..., dry_run=True)`。
- 实际输出：`manifest after dry-run: date = 2026-10-09  count = 405  | batch files on disk hold 400 records`
- 修复建议：dry-run 不写磁盘；或把 manifest 写入推迟到下载完成之后（下载中断时也不应记录"count=总数"）。

### D5（低）download：`scripts/download_entrez.py` 并非"参数相同"的无差别替换（默认选择、输出位置、批大小都变了）

- 位置：`USAGE.md:104`（"旧脚本仍可用，参数相同"）、`CHANGELOG.md:25`（"旧参数兼容"）、`scripts/download_entrez.py`（现为 `g2t.download.main` 的包装）。
- 差异（对照 `git show 41c45bc:scripts/download_entrez.py` 与 `download.py`）：旧脚本默认下载该类群**全部**记录（`txid{id}[Organism]`，含 WGS/mRNA），新默认是 markers（排除 WGS/mRNA/RefSeq）；旧脚本把 `batch_0001.gb…` 与 `download_progress.json` 直接写进 `-o` 目录，新脚本写进 `-o/<tag>/`（默认 `markers/`）；默认批大小 500 → 200；`-e` 由必填变为可选。
- 影响：照旧命令 `python scripts/download_entrez.py --taxon X -o dir` 得到的记录集和目录结构与以前不同；用旧目录重跑"续传"不会识别旧的 batch 文件（会在 `dir/markers/` 重新下载）。`g2t -i dir` 默认递归，若 `dir` 下已有多个 tag 子目录（markers ⊃ mito ⊃ …），同一记录会被读多次，只靠 classify 的 LocusID 去重（会在 filtered_records.csv 里记为 duplicate）兜底。
- 复现：`python3 scripts/download_entrez.py --help` 对比旧脚本参数列表（未联网实测下载；差异来自代码阅读，已用 `build_query` 打印确认默认检索式）。
- 修复建议：文档改成"选项兼容，但默认选择与输出位置已变化，旧默认行为请用 `--all`，输出在 `<out>/all/`"。

### A1（中）`g2t.reconcile()` / `g2t.download()` 等包级函数在首次调用后被同名子模块覆盖，第二次调用 `TypeError: 'module' object is not callable`；README 的 Python API 示例本身就会失败

- 位置：`src/g2t/__init__.py:23-52`（`def download / extract / classify / voucher / reconcile / organize` 与同名子模块冲突；`download`、`reconcile` 为新增，其余为既有同一模式）。
- 原因：包装函数内部 `from g2t.reconcile import reconcile` 会加载子模块，导入系统随即把 `g2t.reconcile` 属性重绑为模块对象，覆盖了包装函数。`g2t.run()` 内部的 `importlib.import_module("g2t.extract")` 等同样触发覆盖。
- 复现 1（单独调用两次）：
```python
import g2t
g2t.reconcile("pipe1/updated_species_vouchers/updated_species_voucher.csv", "s3_api")   # 第一次成功 (success=True, 496 行)
g2t.reconcile("pipe1/updated_species_vouchers/updated_species_voucher.csv", "s3_api")   # 第二次
```
  实际输出：`before: function ...` -> `after 1st call: g2t.reconcile is module` -> `2nd call: TypeError 'module' object is not callable`
- 复现 2（README "Python API" 小节的原顺序：先 `g2t.run(...)`，再逐步调用）：
```python
import g2t
res = g2t.run([".../markers"], "pipe_api", quiet=True)      # success
g2t.organize("pipe_api/updated_species_vouchers/reconciled_species_voucher.csv", "m.csv")
```
  实际输出：`extract module / classify module / voucher module / reconcile module / organize module` 与 `g2t.organize after g2t.run -> 'module' object is not callable`。README 示例里 `g2t.run(...)` 之后紧跟的 `g2t.extract(...)` 同样会抛错。
- 修复建议：在 `__init__.py` 里急切导入并显式绑定（`from g2t.reconcile import reconcile` 等，放在所有子模块导入之后，使包属性最终指向函数）；或把包装函数改名（如 `run_reconcile`），或让包装函数在返回前 `globals()[name] = wrapper`。

### C1（中）`g2t-classify` 独立命令行不生成 `record_status.csv`，与 README/USAGE/CHANGELOG 不符

- 位置：`src/g2t/classify.py:1353`（只在 `classify()` API 里调用 `build_record_status`）对比 `_run_cli`（约 `:1140-1247`）与 `main`（没有调用）；文档 `README.md:64`、`USAGE.md:219`、`CHANGELOG.md:8`。
- 现象：README 第 2 步写明 `g2t-classify -i s1/final.csv -o s2` → 产出 `record_status.csv`；实际只有 `filtered_records.csv`。通过 `g2t`（流水线）或 `g2t.classify()` 才有。
- 复现：
```
$ g2t-classify -i sub40.csv -o cli_out
$ ls cli_out
assigned_genes_type.csv  assigned_genes_types2.csv  assigned_genes_types_all.csv  filtered_records.csv
unmatched_sequences.csv  unmatched_sequences2.csv                           # 没有 record_status.csv
```
- 修复建议：在 `_run_cli` 末尾同样调用 `build_record_status`（需要把 `if_recheck`、`unmatched_sequences`、`prematch_output_file_name` 等参数传入；注意 CLI 的 `--length/--organelle/--moleculetype/--mol_type` 过滤已在 `process_prematch` 内记录到 filtered_records.csv，我用 `--organelle mitochondrion --length 300:500 --moleculetype dna --mol_type "genomic DNA"` 核对过：34 条被过滤、input_row 与 LocusID 全部对应、无遗漏，见"检查过未发现"）。

### C2（低-中）`record_status.csv` 读取旧的 `assigned_genes_types_all.csv`：同目录二次运行且关闭 recheck 时，状态与本次结果不符

- 位置：`src/g2t/classify.py:1266-1268`（优先读 `assigned_genes_types_all.csv`，不存在才读 `assigned_genes_type.csv`）；`classify()` 在 `if_recheck=False` 时不会重写/删除 `_all`、`assigned_genes_types2.csv`、`unmatched_sequences2.csv`。
- 现象：第一次 recheck 开启，某条仅靠第 2 轮（Topology=circular）分到 mtgenome；第二次同目录关闭 recheck，该记录实际在本次的 unmatched_sequences.csv 中，而 record_status.csv 仍写 `assigned / mtgenome`（读了旧 `_all`）。
- 复现（`test_cls_stale.py::test_C3_stale_all`）：
```python
df.loc[0, ["Definition","Topology","Length"]] = ["Priapulus caudatus isolate X2 sequence", "circular", "15000 bp"]
classify(p, out, MatchConfig(), if_recheck=True)    # row0 -> assigned, mtgenome
classify(p, out, MatchConfig(), if_recheck=False)   # 同一 out 目录
```
- 实际输出：
```
run1 (recheck on): row0 -> ['assigned', 'mtgenome']
run2 (recheck off): row0 -> ['assigned', 'mtgenome', 'Topology=circular -> direct mtgenome']
run2 unmatched_sequences.csv contains row0 LocusID: True | assigned_genes_type.csv contains it: False
```
- 备注：下游 voucher 步骤同样固定读 `assigned_genes_types_all.csv`（既有行为），所以旧文件问题本来就存在；新增的 record_status 把它放大成"报告说已分配"。
- 修复建议：`classify()` 开头删除上次遗留的 `assigned_genes_types_all.csv / assigned_genes_types2.csv / unmatched_sequences2.csv / record_status.csv`；或 `build_record_status` 直接用内存里的 round-1/round-2 结果，不读盘。

### C3（低-中）所有记录都被过滤时 `classify()` 以 `KeyError: 'gene_type'` 失败，且无 record_status.csv（既有缺陷，新功能使其更显眼）

- 位置：`src/g2t/classify.py:905-906`（`res_df` 为空 DataFrame 时没有 `gene_type` 列）；该处未改，但 filtered_records.csv 已在 `:893` 左右写出。
- 复现（`test_cls_repro.py::test_C2_all_records_filtered`）：把输入表所有 Length 改成 `50 bp`（低于全局下限 150）后 `classify(...)`。
- 实际输出：`ERROR g2t.classify: Classify failed: 'gene_type'`，`success: False | files: ['filtered_records.csv']`；流水线报 `Step 2 failed`，不告诉用户原因在长度过滤。
- 修复建议：`res_df` 为空时补齐列（`pd.DataFrame(columns=...)`），仍写出空的 assigned/unmatched 与 record_status（全部 filtered）；或给出明确错误信息并指向 filtered_records.csv。

### C4（低）带千分位的长度（`1,234 bp`）被当作"长度缺失/非数字"而丢弃

- 位置：`src/g2t/classify.py:848-849`（只去掉 `bp`，`pd.to_numeric` 对 `1,234` 得 NaN）与同文件 `clean_length`（`:372-376`，会去掉所有非数字，二者不一致）。
- 现象：输入表（手工编辑/Excel 导出）里 `Length` 写成 `1,234 bp` 时，这条记录进入 filtered_records.csv，原因为 "length missing or not numeric"（实际长度合法）。extract 自己输出的是 `N bp`，不含逗号，所以流水线正常使用不受影响。
- 复现（`test_cls_repro.py::make_input`，row 2）：`df.loc[2, "Length"] = "1,234 bp"` -> 实际输出 `2  1,234 bp  filtered  length missing or not numeric`。
- 修复建议：先 `str.replace(",", "")` 再转数值。
- 另：这类记录在 filtered_records.csv 里 `Length` 列也是空的（`_filtered_rows` 用转换后的数值），看不到原始写法 `1,234 bp`，容易误判成真的缺失。
- 另见：把 `--length_range2_all` 设成空字符串时，缺长度的记录原先会保留（NaN 比较不触发过滤）、现在一律被丢（`:853-855` 新增的 missing 分支），属于行为变化（README 已声明"or without a length"）。

### R8（低）reconcile 的凭证字段优先级与 voucher 步骤不一致（clone/strain 顺序相反）

- 位置：`src/g2t/reconcile.py:54`（`["specimen_voucher","isolate","culture_collection","strain","clone"]`）对比 `src/g2t/voucher.py:83`（`["specimen_voucher","isolate","culture_collection","clone","strain"]`）与 `USAGE.md` 的"凭证号优先级"（4. clone，5. strain）。
- 现象：一条记录同时有 clone 和 strain、前面三个字段为空时，voucher 步骤的分组键用 clone，reconcile 却从 strain 取 core，候选配对依据的不是该记录实际分组所用的凭证。
- 复现（`test_order.py::test_R8_clone_strain_priority`）：
```python
df = pd.DataFrame([dict(ACCESSION="A1", LocusID="A1.1", organism="Priapulus caudatus", gene_type="coi", clone="C1234", strain="S5678", specimen_voucher="", isolate="", culture_collection="")])
build_species_vouchers(...); reconcile_dataframe(updated_species_voucher)
```
- 实际输出：`voucher step key: Priapulus_caudatus_C1234 | reconcile voucher_core: S5678`
- 修复建议：从 `voucher.py` 导入同一个默认顺序常量（并让 pipeline 的 `voucher_extra["columns_order"]` 传给 reconcile）。

### P1（低）`--resume` 下 reconcile 不会随选项变化重跑：`--reconcile_min_confidence`、`--skip_reconcile` 的变更被静默忽略

- 位置：`src/g2t/_pipeline.py:188-206`（reconcile 仍用统一的 `resume and is_valid_output(...)` 判定）与第 4 步的同样判定。
- 现象：已跑过完整流水线后，`g2t ... --resume --reconcile_min_confidence high`：第 3b 步显示 `skipped (resume)`，reconciled_species_voucher.csv 的修改时间不变，用的仍是 medium 结果；`--resume --skip_reconcile` 时第 4 步因输出已存在而跳过，最终矩阵仍含 reconcile 的合并（`match_basis` 仍有 94 条 reconciled）。
- 复现：
```
g2t -i .../markers -o pipe1                                   # 完整运行
cp -r pipe1 pipe3 (去掉 organized_genes)
g2t -i .../markers -o pipe3 --resume --reconcile_min_confidence high
  -> "Step 3 skipped (resume): .../reconciled_species_voucher.csv"，mtime 1791478262 前后相同
g2t -i .../markers -o pipe4 --resume --skip_reconcile        # pipe4 = pipe1 的拷贝
  -> "Step 4 skipped (resume)"；organized 里 {'exact': 229, 'reconciled': 94}
```
- 说明：这是 `--resume` "输出存在即跳过"的既有语义，不是新代码独有，但新选项让它对用户更不直观。另外控制台打印的仍是 "Step 3 done/skipped"（只有返回的 `log` 被改成 3b），`steps_completed` 也不计入 3b。
- 修复建议：把 reconcile 参数写入输出旁的小 sidecar（如 `reconcile_report.csv` 头或 `.json`），不一致则重跑；或文档里写明 resume 不检测参数变化。

---

## 二、检查过但未发现问题（含证据）

| 项目 | 做法 | 结果 |
|---|---|---|
| `_parse_date`：`Jun-2019`、`2019-06`、`12-Jun-2019`、`2019`、`2019-6-2`、区间 `2019-06-12/2019-06-14` | `dl.py` 逐个打印 | `Jun-2019`/`2019-06` 都得 `(2019,6,None)`，互相兼容但不算"同日"；区间只比年份（代码注释即如此）；`June-2019`、`Sept-2019`、`2019/06` 退化为只取年份，不会误判冲突 |
| `_dates_compatible` 的"同日"判定 | 16 组配对 | 仅 `日期完整且相等` 才返回 identical；`2019-06-12` vs `12-Jun-2019` 正确判同日；`2019-12` vs `2020-01` 判冲突 |
| `_latlon`：`12.5 S 45 W`、`12.5S 45W`、小数、小写方向 | `dl.py` | 南/西取负正确；缺方向（`12.5 45`）、度分秒（`12°30'S 45°20'W`、`12 30 S 45 20 W`）、逗号分隔返回 None，只是不产生证据，不会误判。INSDC 规范的 lat_lon 本就是十进制度 + 方向，故不算缺陷 |
| 并查集冲突检查（同 core 的 A~B、B~C，A 与 C 冲突） | `test_rec_ok.py::test_ok_same_core_triple_conflict_respected` | C 被拒绝（A–C 日期冲突），报告三行判定正确。只有"含多个 core 的分组"才绕过，见 R3 |
| 新键与已有无关分组同名 | `test_ok_new_key_equal_existing_key` | 正确加 `_reconciled`，原分组不动（三个以上才冲突，见 R1） |
| `--min_confidence high` | `test_ok_min_confidence_high` | 仅中等证据时不合并，报告 `medium confidence below threshold (high)` |
| `voucher_core` 对 NaN、纯数字、小写、`WS-399`/`WS 399`/`ZMMU MSU WS399`/`COI_ZMMU_MSU_WS399`/`28S_..._WS399` | `vc.py` | 全部得 `WS399`；`NaN`/`12`/`ABC` 得空；长度<4 的 core 被丢弃 |
| 真实数据 Priapulidae：reconcile 结果合理性 | `real_rec.py`、`real_rec2.py`、`pipe1` | 496 行 → 94 个合并标本（来自 206 个分组），全部 `high`（共享论文）；无"一个标本×同一基因 >1 条"；合并后无含 >1 个 WS 编号的标本；`WS3020`（*P. caudatus* COI 与 *H. spinulosus* 28S）正确报告为 "different organisms" 未合并；与 README 的 130 对/94 标本一致 |
| 空输入 | `test_R5_empty_input` | `reconcile_dataframe` 对 0 行不崩溃 |
| 组织步骤的新 tail 列 | `organize` 4 种 metadata_mode（first_nonempty/all/advanced/per_gene）× 有/无 reconcile 输入 | 全部成功；有 reconcile 时 `match_basis` {exact:229, reconciled:94}，`match_evidence` 94 条；无 reconcile 时三列为空，不报错 |
| 流水线 `skip_reconcile` 时 organize 的输入 | `g2t ... --skip_reconcile`（API/`organize` 直跑） | organize 读 `updated_species_voucher.csv`，435 行（未合并）正常 |
| 标准流水线端到端 | `g2t -i .../gb/markers -o pipe1` | 5 步完成；record_status 548 行 = assigned 496 + filtered 30 + unmatched 22，与 filtered_records.csv(30 行) 一致 |
| record_status / filtered_records 的 input_row 对应 | `test_cls_repro.py`：csv/tsv/xlsx × recheck 开/关 共 6 组，含 `50 bp`、空长度、`60000 bp`、重复 LocusID、无关键词记录 | 每组 status 行数 = 输入行数，filtered 的 input_row 与 LocusID 全部对应原表；重复 LocusID 仅后一条被标 filtered，首条 assigned |
| CLI 可选过滤的 filtered_records | `g2t-classify -i sub40.csv --organelle mitochondrion --length 300:500 --moleculetype dna --mol_type "genomic DNA"` | 34 条被过滤，与我独立用 pandas 算出的期望集合完全相同，input_row↔LocusID 0 处不符，无重复行；原因文字按首个未通过的过滤给出 |
| `Length` 带 `bp` | 真实 `final.csv`（全是 `N bp`） | 正确解析 |
| download 查询构造：`--gene`+`--mitogenome`、`--mito`+`--mitogenome`、带引号/OR 的 `--query`、重复基因 | `build_query` 打印 | 括号完整；`mitogenome` 优先于 `mito`；`--query` 被原样括起来；`COI,coi` 去重逻辑缺失但只产生重复子句（tag 为 `gene-COI_COI`，无害）；`ITS1,ITS2` 同样重复 |
| `_n_records` 被序列内容干扰 | 真实 3 个批文件 | 每批 `_n_records` = `^LOCUS` 行数 = `^//` 行数（200/200/148），合计 548 = accessions.tsv 行数。序列行以空格+数字开头，不可能出现行首 `LOCUS ` |
| 12S/16S 的 `clause`（`A OR B OR C AND mitochondrion[filter]` 无括号） | 联网 4 次 esearch（Priapulidae, txid37891） | 带括号与不带括号的写法 count 相同（37），本数据无法区分 Entrez 的运算顺序，未发现错误；`16S[Title]` 单独为 0 是因为本类群的 16S 记录标题写作 "large subunit ribosomal RNA"，由第三个子句命中 |
| `scripts/download_entrez.py` 包装 | `--help`、缺 `-t`、`--gene XYZ` | 正常转发；未知基因抛 `ValueError`（在两次 taxonomy 网络请求之后才抛，且是裸 traceback，仅体验问题） |
| 联网总量 | 共 6 次 esearch（nuccore）+ 1 次 taxonomy esearch/efetch | 未超 10 次 |

### 加固建议（仅有模拟证据，没有在真实 NCBI 上出现，因此不计入确认问题）

- `download.py:213-220` 只数 `LOCUS`：把最后一条记录截掉 300 字符后 `_n_records` 仍等于 148（上面的脚本输出），截断的响应会被接受。建议同时要求 `//` 行数相同。
- `download.py:207`：`accs` 数量与 esearch 的 `total` 不一致时不报警（比如分页拿到的比声明的少），继续下载并以退出码 0 结束；建议下载前 `if len(accs) != total: warn/失败`。
- `reconcile` API 的 `ReconcileConfig(min_confidence="low")` 等非法值直到有候选对时才抛 `KeyError`（CLI 有 `choices` 保护，API 没有）。
- `_pipeline.py` 的 `steps_completed` 不计 3b；控制台打印仍是 "Step 3 ..."（只有返回的 `log` 被改成 3b）。纯显示问题。
- `classify.py` 的 `--length_range2_all none` 会 `int("none")` 报错（既有行为，`parse_interval` 不识别 `none`）。
