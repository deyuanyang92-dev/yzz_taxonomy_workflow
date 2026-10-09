# g2t 原有模块代码审查（extract / classify / voucher / organize / utils / gene_dict.yaml）

- 审查对象：`/mnt/n/yzz-分类工作流/vendor/gb2taxonomy/src/g2t/` 下 `extract.py`、`classify.py`（不含 `_write_filtered/_filtered_rows/_filter_dataframe_logged/build_record_status`）、`voucher.py`、`organize.py`、`utils.py`、`data/gene_dict.yaml`。不含 `download.py`、`reconcile.py`。
- 环境：Python 3.13.11，pandas 3.0.0，Biopython 1.86；仓库自带 236 项测试全部通过（说明下列问题均不在现有测试覆盖内）。
- 方法：每个问题均写最小复现并实际运行；复现脚本与输入保存在 `/tmp/claude-0/-mnt-n------/0f3bff3e-0e88-466e-8774-d266b53421ea/scratchpad/review_legacy/`（下文以 `scratch/` 指代），文件名在各条目中给出。真实数据（`Priapulidae/02_原始数据/genbank/gb/markers/*.gb` 与 `g2t/markers/` 输出）只读。
- 严重度含义：高 = 功能整体失效，或静默产生错误/丢失数据且触发条件现实；中 = 在特定输入/选项下产生错误结果、或与文档不符；低 = 边界/一致性问题。
- 证据状态：除标注“代码阅读”的部分外，均为“已确证（实际运行复现）”。

## 0. 汇总

| 编号 | 严重度 | 文件:行 | 一句话 |
|---|---|---|---|
| L-01 | 高 | extract.py:1203,1256 | `--batch` 并行模式整体不可用（局部函数无法 pickle，所有文件 FAILED） |
| L-02 | 高 | extract.py:887-905,1301-1319 | 文件中途解析失败仍判 SUCCESS，后续记录静默丢失；`extract()`（流水线路径）还静默跳过无效文件且不产生任何报告 |
| L-03 | 高（条件触发） | classify.py:372-376,848-854 | 只要有一行 Length 缺失/非数字，其余行 Length 变 float，`clean_length("550.0")` 得 5500，长度被放大 10 倍，导致误判 18-28s / mtgenome |
| L-04 | 中 | extract.py:1015 | `final.csv` 合并时 `read_csv` 未设 `dtype=str`，数值型列被改写（`007`→`7`，`1E5`→`100000.0`，真实数据 `Ref1PubMed` 变 `32671913.0`） |
| L-05 | 中 | extract.py:75-126 | Python 3.13 下 ete3 导入失败，Class/Order/Family/Genus 全空（真实输出 0/548），与 USAGE 不符 |
| L-06 | 中 | gene_dict.yaml + classify.py:232-234 | 关键词误配：`16S rRNA methyltransferase`→16s、`histone H3 lysine 4 demethylase`→h3、英文词 `its`→its1-its2（并因优先返回吞掉真基因）、`elongation factor-1 beta`→ef-1、isolate/voucher 名 `CO1/CO2/COI-12` 引入多余基因 |
| L-07 | 中 | classify.py:670-677,688-695 | 冲突解析用单基因覆盖整个候选集（丢基因），且遍历 `set`，结果随 `PYTHONHASHSEED` 变化（非确定性） |
| L-08 | 中 | organize.py:129-130,135-149；classify.py:650-654 | mtgenome 无条件复制到 coi/16s/12s/cob/cox2/cox3；`--mtgenome_includes` 完全无效；3 个线粒体蛋白基因 + 长度>3000 即被改判 mtgenome 后再复制到 16s/12s/cob |
| L-09 | 中 | organize.py:91-95,182-184,296-315 | `first_nonempty` 逐列独立取首个非空值：同一行内 Conflict=False 但 Conflict_reason 非空；geo_loc_name 与 country 可来自互相矛盾的不同记录 |
| L-10 | 中 | classify.py:1320-1371 | 复用输出目录时 `assigned_genes_types_all.csv`/`conflicted_genes.csv`/`multiple_matched.csv` 陈旧；`if_recheck=False` 时不生成 all 文件却返回 success=True |
| L-11 | 中 | voucher.py:50-62 | `--normalize_columns` 把所有列名转小写（`LocusID`→`locusid`），Step 4 必然失败；帮助文字只说“空格→下划线” |
| L-12 | 中 | voucher.py:284-286,281 vs 82-83,71 | `g2t-voucher` CLI 默认凭证列缺 `culture_collection` 且默认用 haplotype 回填，与 API/流水线及 USAGE 的优先级不一致 |
| L-13 | 中 | classify.py:855-866,946-957,985；README Limitations 3 | README 建议的 `--length_range2_all 1:1000000` 不足以让短序列参与分类；全部记录被过滤或第 2 轮全被长度过滤时抛 `KeyError: 'gene_type'` |
| L-14 | 低 | classify.py:874-875,961-962 | `itertuples()` 把含空格的列名（`Assembly Method` 等）改成 `_56…`，输出里列名丢失，且第 1/2 轮编号不同（`_56-_60` 与 `_62-_66`） |
| L-15 | 低 | classify.py:232,361 | 同义词以非字母数字字符开头（如 `(COI)`、`-cox1`）时 `re.PatternError: look-behind requires fixed-width pattern` |
| L-16 | 低 | utils.py:79-97；classify.py:856 | `--length_range2_all none/all` 崩溃；无法解析的长度在 `length_in_range` 中静默视为“在范围内”；`500:150` 不校验 |
| L-17 | 低 | classify.py:491,653,730 | mtgenome 下限硬编码 3000，覆盖 `--length_range2_mtgenome` 的下界；恰好 3000 bp 通过范围但被拒 |
| L-18 | 低 | classify.py:719-721,723,1209 | 第 2 轮：Topology=circular 直接判 mtgenome（无长度/细胞器校验）；第 2 轮忽略 `--mtgenes_list/--ntgenes_list`；`--which_gene_types_extract` 只含第 1 轮结果 |
| L-19 | 低 | extract.py:546-550 | 非 taxon 的 `db_xref`（如 BOLD）被丢弃，`db_xref` 列永远为空（真实数据 batch_0003 有 1 条 BOLD） |
| L-20 | 低 | extract.py:1095-1097 vs 1153 | `--stream` 与非 stream 的 `final.csv` 取值相同，但列集合与列顺序不同 |
| L-21 | 低 | extract.py:579-582；voucher.py species_name_column | 只取第一个 source feature；无 source 时 `organism` 为空且 voucher 不回退到 `Organism` |
| L-22 | 低 | voucher.py:140-142 | 纯空白/纯标点的 voucher（`" "`、`".."`、`"()"`）不是 NaN，不触发回退，清洗后为空，键退化为“物种名”，无关记录被并成一个标本 |
| L-23 | 低 | organize.py:107-116,371-374 | gene_order 外的基因（如自定义 `nd1`）静默丢弃；`species_voucher_new` 为 NaN 的行全部并入 `UNKNOWN`，不同物种混在一行 |
| L-24 | 低 | extract.py:855-873 | `assembly_failed` 永远为 0（死计数），汇总里的 Assembly coverage 恒为 100% |
| L-25 | 低 | 见正文 | 杂项：`categorize_unmatched_definition` 的 `'nad'` 子串；classify CLI 在当前目录写 `extract_methods.log`；`infer_objects(copy=False)` 在 pandas 4 将失效；16s/28s 重复同义词 |

范围外但顺带发现：`_cli.py:107-110` 的 `--extract_extra/--classify_extra/--voucher_extra/--organize_extra` 解析后从未传给 `run()`，是死选项；因此用 `g2t` 命令无法给 organize 传自定义 `gene_order`（见 L-23）。

---

## 1. 高

### L-01 extract `--batch` 并行模式整体不可用

- 位置：`extract.py:1203`（在 `process_batch_mode` 内部定义 `_process_single_file_batch`），`extract.py:1256`（`ex.submit(_process_single_file_batch, f)`）。
- 现象：`ProcessPoolExecutor` 需要 pickle 被提交的函数，局部函数不能 pickle，所有文件都返回 FAILED。`g2t --batch` 走 `_pipeline.run → extract()` 时，因为 batch 模式不生成 `final.csv`，`_find_fallback` 抛未处理的 `FileNotFoundError`。USAGE“多文件处理：使用 `--batch` 参数并行处理”因此不成立。
- 复现（`scratch/e2_batch.py`，`scratch/e2b_pipe_batch.py`）：

```python
ex = importlib.import_module("g2t.extract")
s = ex.process_batch_mode(["e2/rec_good1.gb","e2/rec_good2.gb"], "e2/out",
                          max_tasks=2, stream_mode=True, include_taxonomy=False)
for r in s.file_results: print(os.path.basename(r.file_path), r.status.value, r.error_message)
# g2t.run(input_files=["e2"], output_dir="e2/pipe", stream=True, batch=True, max_tasks=2)
```

实际输出：

```
rec_good1.gb failed Can't get local object 'process_batch_mode.<locals>._process_single_file_batch'
rec_good2.gb failed Can't get local object 'process_batch_mode.<locals>._process_single_file_batch'
[]                                   # e2/out 为空
EXC FileNotFoundError Step 1: no valid output found matching *final*.csv in .../e2/pipe/gb_metadata
```

- 次要（代码阅读，未运行）：即使修好 pickle，batch 模式只写 `<base>_metadata/<base>_metadata_final.csv`，而 `extract()` 与流水线期望 `output_dir/final.csv`（`extract.py:1321`），仍接不上后续步骤；两个目录下同名文件还会互相覆盖（`base` 取自 basename）。
- 修复：把 worker 提到模块级函数（用 `functools.partial` 传参）；batch 完成后合并各子目录为 `final.csv`；`base` 加入路径哈希或序号；`extract()` 在 batch 下也返回真实的 `final.csv`。

### L-02 解析中途失败仍判 SUCCESS，后续记录静默丢失；流水线路径无报告且静默跳过无效文件

- 位置：`extract.py:887-889`（外层 `except` 只写 `error_message`），`extract.py:894-905`（状态只看 `metadata_failed`），`extract.py:1301-1319`（`extract()`）。
- 现象：
  1. `SeqIO.parse` 在第 k 条记录抛异常后，第 k 条及之后的记录全部丢失。`total_records` 只记到出错前的条数，`metadata_failed=0`，状态为 SUCCESS，CLI 末尾打印 “All processing complete!”。唯一痕迹是一行 ERROR 日志和 JSON 里的 `error_message`。
  2. `extract()`（`g2t`/`g2t.run` 实际调用的入口）对 `validate_and_estimate_records` 失败的文件直接跳过，不记录、不告警；`ProcessingSummary` 被丢弃，也不写 `extraction_report.json` / `record_tracking.csv`（只有 `main()` 才写）。真实输出目录 `gb_metadata/` 里确实只有 `assembly.csv final.csv metadata.csv`。
- 复现 1（`scratch/e1_trunc.py`）：3 条记录，第 2 条 LOCUS 行长度写成 `abc`：

```
status: success | total_records: 1 | metadata_extracted: 1 | metadata_failed: 0 | error_message: Biopython parse error: invalid literal for int() with base 10: 'abc'
rows in metadata.csv: 1
records in file (// count): 3
...  OK trunc.gb / Records: 1 | Metadata: 1/1 ...  / All processing complete!
```

- 复现 2（`scratch/e7_invalid.py`）：目录里一个正常 `.gb`，一个内容为 NCBI 错误 XML 的 `batch_0002.gb`：

```
INFO File discovery: 2 files, 2 GenBank, 0 skipped
INFO [1/1] ok.gb (1.9 KB)
RESULT success= True rows= 1            # 无任何关于 batch_0002.gb 的警告
['assembly.csv', 'final.csv', 'metadata.csv']
```

- 修复：外层异常时置 `FileStatus.PARTIAL/FAILED`；用 `validate_and_estimate_records` 已计算的 `//` 条数与实际解析条数对账，不等则报错；改为按 `//` 切记录逐条解析，单条失败只计该条；`extract()` 对无效文件 `logger.warning` 并写入报告，始终写 `extraction_report.json`，有失败时返回 `success=False` 或至少把计数带回 `StepResult`。

### L-03 Length 缺失导致其余行长度放大 10 倍（条件触发，影响面大）

- 位置：`classify.py:848-849`（`pd.to_numeric(..., errors='coerce')` 在有 NaN 时得到 float64 列），`classify.py:372-376`（`clean_length` 用 `re.sub(r'[^\d]','',str(x))`），`classify.py:554,708,806`。
- 现象：README 明确支持“缺 Length 的记录被过滤并列入 `filtered_records.csv`”。但只要输入里有一行 Length 缺失/非数字，保留下来的所有行 Length 都是 float，经 `itertuples` 传入后 `str(550.0)="550.0"`，`clean_length` 把小数点去掉得到 5500。结果：550 bp 的 18S-ITS-28S 片段满足 `18-28s` 的 5000:15000 范围；800 bp 的 “mitochondrion, partial genome” 满足 mtgenome 的 `>3000`；organize 再把它们复制到 18s/28s/its 或 coi/16s/12s/cob/cox2/cox3 各列。extract 产生的表 Length 恒为数字，所以标准流水线不触发；手工/外部表格（README 声明支持 CSV/TSV/Excel）会触发。
- 复现（`scratch/c5_float_length.py`）：

```python
# 3 行: A 550bp 18S-ITS1-5.8S-ITS2-28S 定义；B 800bp "mitochondrion, partial genome"; C 700bp COI；可选再加 D: Length 为空
cl.process_prematch("in.csv", d, cl.MatchConfig(), "a.csv","m.csv","u.csv","c.csv","all","all","all","all")
```

```
with Length-missing row: False
 A.1  550   its1-its2  18-28s: keyword matched but length 550 outside range 5000:15000; its1-its2: priority match hit ...
 C.1  700   coi
 (B.1 未匹配，正确)
with Length-missing row: True
 A.1  550.0 18-28s     18-28s: priority match hit ...
 B.1  800.0 mtgenome   mtgenome: priority match hit ...
 C.1  700.0 coi
```

- 修复：`clean_length` 先 `pd.to_numeric(str(x).replace('bp',''), errors='coerce')` 再取整，而不是剔除所有非数字字符；`process_prematch` 里把 Length 转 `Int64`；`process_recheck` 同理。

---

## 2. 中

### L-04 `final.csv` 合并时数值列被改写

- 位置：`extract.py:1015`（`md_df = pd.read_csv(md_file, low_memory=False)`），1022 的 `asm_df` 同理。
- 现象：`metadata.csv` 写得正确，但合并成 `final.csv` 时重新读入没有 `dtype=str`，整列都是数字样式的列被转为数值：前导零丢失、科学计数法展开、有空值的整数列变 `xxx.0`。
- 真实数据证据：`gb_metadata/final.csv` 的 `Ref1PubMed` 有 109 行是 `32671913.0`，而 `metadata.csv` 中为 `32671913`；其余列无差异。
- 复现（`scratch/e5_numeric.py`，3 条记录的 `specimen_voucher` 分别为 `007`、`0123`、`45`，`strain` 为 `1E5`、`2E5`）：

```
metadata.csv:  specimen_voucher 007 / 0123 / 45     strain 1E5 / 2E5 / NaN
final.csv:     specimen_voucher   7 /  123 / 45     strain 100000.0 / 200000.0 / NaN
```

- 影响：当某批数据的 `specimen_voucher`/`isolate`/`strain` 整列都是数字时，凭证号被改写，`007` 与 `7` 会被并成同一标本，且无法与 GenBank 原值核对。
- 修复：两处 `read_csv` 加 `dtype=str, keep_default_na=False`（再统一转空串），或在内存中直接合并不落盘再读。

### L-05 ete3 在 Python 3.13 导入失败，分类列全空，且文档与依赖未说明

- 位置：`extract.py:75-95`（`initialize`），`97-126`（`get_lineage`）。
- 现象：`ete3 3.1.3` 依赖已被 3.13 移除的 `cgi` 模块，`from ete3 import NCBITaxa` 抛 `ModuleNotFoundError: No module named 'cgi'`，被吞为一条 warning，之后 Class/Order/Family/Genus 全部为空。USAGE 把这些列列为“提取内容”，README 称 ete3 警告“harmless”，`pyproject.toml` 也没有声明 ete3。
- 证据：`g2t_log.txt` 首行 `ete3 init error: No module named 'cgi'`；真实 `final.csv` 中 `Class/Order/Family/Genus` 非空数为 0/548，`organized_species_voucher.csv` 为 0/323（`TaxonID` 则 548/323 完整）。`python -c "import ete3"` 在本环境直接 `No module named 'cgi'`。
- 修复：在 `pyproject` 声明可选依赖并注明 Python ≤3.12，或装 `legacy-cgi`；更稳妥是改用 Biopython `Entrez.efetch(db="taxonomy")` 或解析 taxdump 获取 lineage；失败时输出明确提示“分类列将为空”。

### L-06 关键词误配与“优先返回”放大损失

- 位置：`gene_dict.yaml`（`16s`、`h3`、`its1-its2`、`ef-1`、`coi/cox2/cox3` 的短缩写同义词）；`classify.py:232-234` 的 `\b…\b` 匹配；`classify.py:484-496` 命中优先基因后立即 `return`。
- 现象（均为 `process_row`/`recheck_match_row` 实测）：

| Definition（节选） | organelle | 结果 | 应为 |
|---|---|---|---|
| `Homo sapiens 16S rRNA methyltransferase (rsmA) gene, complete cds` | mitochondrion | 16s | 不应归类 |
| `Escherichia coli 16S rRNA methylase ArmA gene, complete cds` | - | 第 2 轮 16s | 不应归类 |
| `histone H3 lysine 4 demethylase gene, partial cds` | - | h3 | 不应归类 |
| `NADH dehydrogenase subunit 1 (ND1) gene and its flanking sequence, partial cds` | - | its1-its2（英文词 `its` 命中同义词 `ITS`） | 不应归类 |
| `Priapulus caudatus histone H3 gene, partial cds, and its upstream region` | - | its1-its2，h3 被吞掉 | h3 |
| `elongation factor-1 beta` | - | ef-1（EF-1β 不是 EF-1α） | 不应归类 |
| `Priapulus caudatus isolate CO2 16S ribosomal RNA gene, partial sequence; mitochondrial` | mitochondrion | `16s,cox2`（Conflict=True，但两列都会写入矩阵） | 16s |
| `…voucher COI-12 16S ribosomal RNA gene…` | mitochondrion | `16s,coi` | 16s |
| `…isolate CO3 cytochrome oxidase subunit I (COI)…` | mitochondrion | `coi,cox3` | coi |

- 说明：Definition 里恒含 `isolate X`/`voucher Y`，采集点常用 `CO1/CO2/CO3` 之类编码；organize 对多基因 gene_type 按逗号拆分，会把 16S 的登录号同时写入 cox2 列。未误配的反例见第 5 节。
- 复现：`scratch/c2_fp.py`、`scratch/c3_isolate.py`。真实数据无命中（见第 5 节）。
- 修复：匹配前从 Definition 中剔除 `(isolate|voucher|strain|clone|specimen|haplotype)\s+\S+` 与物种名；`its`、`co1/co2/co3` 这类缩写要求位于 gene 语境（如括号内或后接 `gene|region`），或改为大小写敏感；`16S rRNA` 增加负向前瞻 `(?!\s+(methyl|ase))`；`elongation factor-1` 不再接受后接 `beta|gamma|delta`；`its1-its2` 的优先返回改为仅在没有 18S/28S 关键词时生效。

### L-07 冲突解析丢基因，且结果随哈希种子变化

- 位置：`classify.py:670-677`（`_conflict_mito`）、`688-695`（`_conflict_nuclear`）：对 `list(genes)`（set）循环，命中第一个就 `resolved = result["resolved"]`（只含这一个基因）并返回。
- 现象：候选为 {12s, 16s} 且 Definition 同时含 “small subunit ribosomal” 与 “large subunit ribosomal” 时，两个基因都会触发冲突规则，保留哪个取决于 set 迭代顺序，即取决于 `PYTHONHASHSEED`；另一个基因被丢弃（`Original_match` 仍保留原始两个）。同一输入两次运行结果可能不同，破坏可重复性。
- 复现（`scratch/c4_nondet.py`）：Definition 为 `Priapulus caudatus mitochondrial small subunit ribosomal RNA and large subunit ribosomal RNA genes, partial sequence; mitochondrial`，organelle=mitochondrion：

```
seed 0: 16s True 16s conflicts with 'small subunit ribosomal' description
seed 1: 12s True 12s conflicts with 'large subunit ribosomal' description
seed 2: 16s ...   seed 3: 16s ...   seed 4: 12s ...   seed 5: 12s ...
```

- 修复：`for gene in sorted(genes)`；冲突规则只做“标记”（`Conflict=True`），不替换候选集合；或者保留全部候选并写入 `Conflict_reason`。

### L-08 mtgenome 无条件复制到各线粒体基因列；`--mtgenome_includes` 无效；多基因改判 mtgenome

- 位置：`organize.py:129-130`（`mito_children = config.get_mito_genes()`，忽略 `config.gene_includes["mtgenome"]`）；`organize.py:135-149`；`classify.py:650-654`（`>2` 个线粒体候选且长度>3000 → mtgenome）。
- 现象：
  1. 任何 gene_type 含 mtgenome 的记录（只需长度>3000 与关键词），其登录号被写入 coi/16s/12s/cob/cox2/cox3 六列，不检查该记录是否含有这些基因。README 写“复制到它覆盖的各基因列”，代码并没有“覆盖”判断。真实数据例：`FN689349.1`（14.7 kb，完整线粒体基因组）的特征表里没有任何 12S 注释，却出现在矩阵的 `12s` 列（其余 5 个基因有注释）。
  2. `--mtgenome_includes coi` 对输出毫无影响。
  3. 只含 COI、COII、COIII 的 3.5 kb 局部区段，被 classify 改判为 mtgenome，organize 再把它写进 16s/12s/cob。
  4. 同一标本若另有独立 COI 扩增子，`coi` 单元格变成 `C1.1;MT1.1`（扩增子与整个线粒体基因组混在一起），下游按列提序列时会取到整条基因组。
- 复现（`scratch/o2_mt.py`、`scratch/c12_reassign.py`）：

```
default
 species_voucher_new mtgenome coi        16s   12s   cob   cox2  cox3
 Sp_A_1              MT1.1    C1.1;MT1.1 MT1.1 MT1.1 MT1.1 MT1.1 MT1.1     # mtgenome 3200 bp + 独立 COI
 Sp_B_1              MT2.1    MT2.1      MT2.1 MT2.1 MT2.1 MT2.1 MT2.1     # mtgenome 3100 bp
CLI --mtgenome_includes coi            -> 输出与 default 完全相同

classify: mtgenome | orig: coi,cox2,cox3 | Mitochondrial multi-match (3) + Length>3000 -> reassigned to mtgenome
organize: mtgenome Z.1  coi Z.1  16s Z.1  12s Z.1  cob Z.1  cox2 Z.1  cox3 Z.1
```

- 修复：传播时读取 `config.gene_includes["mtgenome"]`；真正按序列特征表（gene/CDS/rRNA 注释）判断覆盖了哪些基因，至少对 `Length < 10000` 或定义含 `partial` 的 mtgenome 不传播，或把传播列单独标注（例如加后缀 `*`）；多基因改判 mtgenome 要求同时有 rRNA 基因或长度 ≥10 kb。

### L-09 organize `first_nonempty`：同一行内元数据来自不同记录，Conflict 标志丢失

- 位置：`organize.py:91-95`、`182-184`、`296-315`。每一列独立取第一个非空值。
- 现象：组内记录 1 的 `Conflict="False"`、记录 2 的 `Conflict="True"` 时，输出 `Conflict=False`，而 `Conflict_reason` 来自记录 2；`Original_match`、`Assignment_reason` 来自记录 1；`geo_loc_name` 来自记录 1，`country` 来自记录 2，二者可以互相矛盾。分类阶段的冲突警示在最终矩阵里被抹掉。
- 复现（`scratch/o1_org.py`）：

```
species_voucher_new  Sp_A_1
coi                  A1.1
16s / cox2           A2.1 / A2.1
Conflict             False                                   <- 记录 A2 为 True
Conflict_reason      Multiple candidate gene types: 16s, cox2
Original_match       coi                                     <- A2 的是 16s,cox2
geo_loc_name         Russia: White Sea                       <- 记录 A1
country              Norway                                  <- 记录 A2
```

- 真实数据现状：323 个标本 `Conflict` 全为 False（分类阶段 496 条无冲突），组内 `country/geo_loc_name/collection_date` 无分歧，仅 5 组 `lat_lon` 精度或位置不同（如 `66.52 N 33.18 E` 与 `66.55 N 33.10 E`，取首个）。
- 修复：`Conflict` 用 `any()`；`Conflict_reason`/`Original_match` 用各记录值拼接（带 LocusID）；地理字段从同一条“主记录”取（例如优先 mtgenome/信息最全的记录），或各字段多值时用 `;` 列出而不是丢弃。

### L-10 复用输出目录时陈旧文件；`if_recheck=False` 无 all 文件却 success=True

- 位置：`classify.py:1326-1371`（`classify()`）、`1214-1242`（CLI）。
- 现象：
  1. `if_recheck=False` 时从不生成 `assigned_genes_types_all.csv`，但返回 `StepResult(success=True, output_file=…all.csv, rows=0)`；若目录里留有上次的 all 文件，则返回旧文件及其行数。
  2. `conflicted_genes.csv`、`multiple_matched.csv` 只在本轮有冲突/多匹配时才写，否则保留上次内容；第 2 轮还会向旧的 `conflicted_genes.csv` 追加。
- 复现（`scratch/c8_api.py`、`scratch/c15_stale.py`）：

```
run1 (recheck=True)  : success True rows 2   # A.1 coi, B.1 coi
run2 (recheck=False, 输入只有 A.1): success True rows= 2 ... all.csv 仍含 B.1.1   <- 陈旧
fresh recheck=False  : success True 0 False c8/out3/assigned_genes_types_all.csv     <- 文件不存在
第二次输入无冲突后 conflicted_genes.csv 仍列出: ['OLD.1']；multiple_matched.csv 仍列出 ['OLD.1']
```

- 修复：每次运行开头清理本步骤的全部产物（或用时间戳子目录）；`if_recheck=False` 时把 round-1 结果同时写成 all 文件；`output_file` 存在性检查后再返回 success。

### L-11 `--normalize_columns` 把全部列名转小写，Step 4 必然失败

- 位置：`voucher.py:50-62`（`col_key` = `lower().replace(" ","_")`），`_pipeline.py` 传 `normalize_column_names=True`。
- 现象：`LocusID→locusid`、`ACCESSION→accession`、`Conflict→conflict`；`Organism` 与 `organism` 都变成 `organism`，后者被改名 `organism__dup1`。organize 的必需列 `LocusID` 找不到，流水线在 Step 4 失败。帮助文字与 USAGE 只说“空格→下划线”。
- 复现（`scratch/v3_normalize.py`）：

```
normalize_columns= False success= True
normalize_columns= True  success= False  Step 4 failed: .../organized_genes/organized_species_voucher.csv
columns: ['gene_type','conflict','match_source','original_match','conflict_reason','assignment_reason','locusid','accession','version','length',...]
```

- 修复：只替换空格、不改大小写；或 organize 用 `resolve_col` 做大小写不敏感解析。

### L-12 `g2t-voucher` CLI 默认值与 API/流水线及 USAGE 不一致

- 位置：`voucher.py:284-286`（CLI `--columns_to_combine` 默认 `specimen_voucher,isolate,clone,strain`），`:281`（`--fill_haplotype` 默认 True）；对照 `:82-83`（API 默认含 `culture_collection`）与 `:71`（`if_write_haplotype=False`）。USAGE 写的优先级：specimen_voucher > isolate > culture_collection > clone > strain > ACCESSION。
- 现象：同一输入，API/流水线得到 `CC-7`，CLI 得到 `H1`（haplotype）；culture_collection 在 CLI 路径被忽略，haplotype 作为文档未提的回填。两种路径的标本分组会不同。
- 复现（`scratch/v1_defaults.py`）：

```
api  A.1  culture_collection=CC-7 haplotype=H1  pse=CC-7  species_voucher_new=Priapulus_caudatus_CC-7
cli  A.1  culture_collection=CC-7 haplotype=H1  pse=H1    species_voucher_new=Priapulus_caudatus_H1
api  C.1  (无 cc, haplotype=H9)  pse=C   -> Priapulus_caudatus_C
cli  C.1                          pse=H9 -> Priapulus_caudatus_H9
```

- 同类（`scratch/x1_check.py` 已运行）：organize CLI 的 `--metadata_columns` 默认只有 15 列，`OrganizeConfig` 默认 26 列；对真实 reconciled 输入，`g2t-organize` 默认输出 37 列，流水线（`g2t.run`）输出 48 列，CLI 缺 `country collection_date isolate specimen_voucher host habitat isolation_source culture_collection clone strain note`（`organize.py:446-453` vs `44-52`）。
- 修复：CLI 默认值直接引用 dataclass/函数默认值；USAGE 同步。

### L-13 README 的“放宽长度”建议不完整；全被过滤或第 2 轮清空时 KeyError

- 位置：`classify.py:479-481`（`_match_gene_loop` 仍按 `length2_mtgenes/length2_ntgenes`=150:50000 判断），`946-957`（第 2 轮长度过滤，之后 `results=[]`），`887-905`/`985`（`pd.DataFrame([])` 无列）。README Limitations 3 与 USAGE 限制 3 均写“`--length_range2_all 1:1000000` 可让它们参与分类”。
- 现象：
  A) 只改 `--length_range2_all`，100 bp 的 COI 仍未匹配（理由 “Length 100 outside range 150:50000”），第 2 轮又按并集范围丢弃；需同时改 `--length2_mtgenes/--length2_ntgenes`。
  B) 第 2 轮长度过滤把所有未匹配行都滤掉，或第 1 轮全部记录都被全局长度过滤，`res_df` 无列，`res_df["gene_type"]` 抛 `KeyError`；CLI 直接 traceback，`classify()` 返回 `success=False` 且原因只在日志里。
- 复现（`scratch/c10_widen.py`、`scratch/c11_allfiltered.py`）：

```
A) README 建议 --length_range2_all 1:1000000 ; assigned: ['L.1']        # S.1(100 bp COI) 仍未分类
   unmatched: {'S.1': 'Length 100 outside range 150:50000', ...}
B) classify() 仅含 100 bp 未匹配行、全局范围 1:1000000 -> success = False
   CLI main -> KeyError 'gene_type'
   所有记录 <150 bp -> classify success = False | files: ['filtered_records.csv']
```

- 修复：`_match_gene_loop` 的全局范围改用 `global_length_range`；README 补全；空结果时构造带列名的空 DataFrame 再写文件；返回 `StepResult` 带 `error` 文本。

---

## 3. 低

### L-14 `itertuples` 改写含空格的列名
- `classify.py:874-875`、`961-962`：`row._asdict()` 把 `Assembly Method`、`Assembly Name`、`Sequencing Technology`、`Genome Coverage`、`Expected Final Version` 改名为 `_56…_60`；第 2 轮输入多了诊断列，编号变为 `_62…_66`，合并后同一字段分裂为两组列。
- 证据：真实 `assigned_genes_types_all.csv` 列尾为 `_56 _57 _58 _59 _60 _62 _63 _64 _65 _66`；其中 `_58` 有 480 个 “Sanger dideoxy sequencing”，对应 `final.csv` 的 `Sequencing Technology`（518 个非空）。
- 修复：用 `df.to_dict("records")` 代替 `itertuples/_asdict`。

### L-15 同义词以非字母数字字符开头时崩溃
- `classify.py:232`、`361`：`left = r'(?<=\s|^)'`，Python 不允许可变宽度 look-behind。YAML 或 `--path_dict` 里加 `(COI)`、`-cox1` 之类同义词，`_precompile_patterns()` 抛错，`load_path_dict` 内该调用在 try 之外，CLI 直接崩溃；写进内置 YAML 则 `import g2t.classify` 本身失败。
- 复现（`scratch/c6_regex.py`）：`'(coi)' EXC PatternError look-behind requires fixed-width pattern`，`'-cox1'` 同。
- 修复：`left = r'(?:(?<=\s)|^)'`。

### L-16 utils 区间解析边界
- `utils.py:79-97`，`classify.py:856`。
- `parse_interval('none'|'all'|'150-500'|'1,000:5,000'|'150:500:600')` 抛 `ValueError`；`length_in_range` 对 `'none'` 特判但对 `'all'` 不特判；`process_prematch` 直接对 `--length_range2_all` 调 `parse_interval`，所以 `--length_range2_all none` 与 `all` 都崩溃（已运行：`ValueError invalid literal for int() with base 10: 'none'` / `'all'`，`scratch/x1_check.py`），而 `--length2_mtgenes none` 却可用，不一致。
- `length_in_range('325 bp', …)`、`('100.0', '150:200')`、`None`、`NaN` 都静默返回 True（不可解析 = 在范围内）。`parse_interval('500:150')` 返回 (500,150) 不校验，等价于“全部过滤”。
- 复现：`scratch/u1_utils.py`。修复：统一一个 `parse_range()`，识别 none/all，校验 lo≤hi，不可解析抛错或返回 False。

### L-17 mtgenome 下限硬编码 3000
- `classify.py:491`（`length_val <= 3000`）、`653`、`730`（`length_val > 3000`）。`--length_range2_mtgenome 1000:500000` 的下界被覆盖；默认范围 `3000:500000` 含 3000，但 3000 bp 被硬编码拒绝。
- 复现（`scratch/c9_mt3000.py`）：范围设为 `1000:500000`，长度 2000 → `''`（`mtgenome: keyword matched but Length=2000<=3000`），3001 → `mtgenome`。
- 修复：删除硬编码，统一读配置。

### L-18 第 2 轮与基因提取的一致性
- `classify.py:719-721`：Topology=circular 直接判 mtgenome，不看长度/细胞器；900 bp 的 circular 质粒或 rRNA operon 记录 → mtgenome（仅标 Conflict，仍被分配）。
- `classify.py:723`：第 2 轮遍历 `GENE_DICT` 全部基因，忽略 `--mtgenes_list/--ntgenes_list`（配置 `mito={coi}, nuclear={28s}` 时，16S 记录第 1 轮未匹配、第 2 轮仍被判 16s）。
- `classify.py:1209`：`--which_gene_types_extract` 只对第 1 轮结果生成 `<gene>_extracted.csv`，第 2 轮分配的记录缺失（复现：all 中 coi 有 `['A.1','B.1']`，`coi_extracted.csv` 只有 `['A.1']`）。
- 复现：`scratch/c7_r2.py`、`scratch/c16_wgte.py`。

### L-19 非 taxon 的 db_xref 丢失
- `extract.py:546-550`：`db_xref` 只取第一个 `taxon:` 存 `TaxonID`，其余 `continue`；`db_xref` 列（在 BASE 列表中）永远为空。
- 真实数据：`batch_0003.gb` 有一条 `/db_xref="BOLD:CCANN086-07.COI-5P"`，`final.csv` 的 `db_xref` 非空数 0/548，BOLD 号丢失。
- 修复：非 taxon 的 xref 以 `; ` 连接写入 `db_xref`。

### L-20 stream 与非 stream 输出的列不一致
- `extract.py:1095-1097`（stream 用 BASE 列 + 预扫描键，固定列序）与 `:1153`（非 stream 用 `pd.DataFrame(list_of_dict)`，按首次出现顺序、缺失列直接缺失）。
- 复现（`scratch/e3_stream.py`，真实 3 个 gb 文件）：stream 61 列，非 stream 52 列；非 stream 缺 `host db_xref country culture_collection clone Class Order Family Genus`；公共列取值逐格相同、顺序不同。
- 影响（代码阅读，未运行）：非 stream 路径下，若整批数据没有 organelle 等限定词，列缺失，classify 的 `--organelle` 等过滤会 `KeyError`，而 stream 路径只会得到 0 行。修复：两种路径使用同一列表。

### L-21 多 source feature 与无 source
- `extract.py:579-582`（`break`）：只用第一个 source，第二个 source 的 organism/voucher/taxon 静默丢弃；没有 source 时 `organism`、`specimen_voucher` 等为空，`voucher.py` 的 `species_name_column="organism"` 不回退到注释行的 `Organism`，键里没有物种名。
- 复现（`scratch/e8_src.py`）：两个 source 的记录，`specimen_voucher=ZMMU:WS30980`、`TaxonID=549204`（第二个 source 的 `SYM1`、`999` 丢弃）；无 source 的记录 `Organism=Priapulopsis bicaudatus`，`organism=None`。
- 理论边界（GenBank 规范要求恰有一个 source），实际发生率低。

### L-22 空白/纯标点的 voucher 阻断回退
- `voucher.py:140-142`：`bfill` 只跳过 NaN；`" "`、`".."`、`"()"` 不是 NaN，选中后 `sanitize_string` 返回 `""`，`species_voucher_new` 退化为“物种名”，下一优先列（isolate）与 ACCESSION 回退都不再使用。
- 复现（`scratch/v2_edge.py`）：A/B/C 三条记录（specimen_voucher 分别为 `" "`、`".."`、`"()"`，isolate 为 I1/I2/I3）的 `species_voucher_new` 全为 `Priapulus_caudatus`，organize 会并成一行；`organism` 为空时 D/E 两个不同物种的 `X1` 合并为 `X1`。
- 修复：先对各候选列做 `sanitize_string`，空串视为缺失再 `bfill`；species 为空时回退 `Organism`。
- 备注：`sanitize_string` 把 `AB 1`、`AB.1`、`AB_1` 归一为同一键（同一次运行中三条记录并为 `Priapulus_caudatus_AB_1`），这是设计取舍，README Limitations 5 已提示“同号合并”。

### L-23 organize：未知基因丢弃与 UNKNOWN 合并
- `organize.py:107-116`：`gene_type` 不在 `gene_order` 的记录被静默丢弃；`organize.py:371-374`：`species_voucher_new` 为 NaN 的所有行并入同一个 `UNKNOWN` 组。
- 复现（`scratch/o3_edge.py`）：`gene_type=nd1` 的标本出现一行但所有基因单元格为空；`Sp X`（coi）与 `Sp Y`（16s）两个 NaN 键并成一行 `UNKNOWN | Sp X | coi=X1.1 | 16s=Y1.1`。
- 因 `g2t` 命令不传 `organize_extra`（范围外 `_cli.py:107-110`），用户在 `gene_dict.yaml` 增加新基因（README 鼓励）后，新基因在矩阵里静默消失。
- 修复：`gene_order` 默认从 `GENE_DICT` 键生成；对未知基因 `logger.warning` 并附加列；NaN 键改用 `ACCESSION` 作为单独标本。

### L-24 `assembly_failed` 死计数
- `extract.py:855-861,872-873`：`track.has_assembly_data` 与 `assembly_ok` 在 `callback` 之后同时赋值，异常发生在两者之前，`if … track.has_assembly_data and not track.assembly_ok` 永不成立。
- 复现（`scratch/e10_asmfail.py`）：回调抛异常 → `assembly_failed=0, assembly_extracted=0, assembly_no_data=0, metadata_failed=1`，汇总行 “Assembly coverage” 恒为 100%。

### L-25 杂项（均已运行确认）
- `classify.py:1074`：`'nad' in def_lower` 为子串匹配，`Canada`、`gonadotropin` 被归入 `NADH_dehydrogenase`（`scratch/c13_dictsync.py`）。仅影响 unmatched 报告的分类标签。
- `classify.py:1147`：CLI 的 `setup_logging()` 在当前目录写 `extract_methods.log`（mode `w`），不在输出目录，且每次调用重复添加 handler（`scratch/extract_methods.log`）。
- `voucher.py:143,150,156`：`infer_objects(copy=False)` 在 pandas 3 已有 `Pandas4Warning`，pandas 4 将报错；`pyproject` 写 `pandas>=1.5` 无上限。
- `gene_dict.yaml`：同义词 `large subunit ribosomal RNA` 同时在 `16s` 与 `28s`（`ribosomal RNA large subunit` 与 `ribosomal RNA large subunit gene` 同理）：第 1 轮靠 mito/nuclear 分组区分，第 2 轮无分组，任何此类定义都同时得到 `16s,28s`（`scratch/c1_dict.py`）。`cob` 下的 `cytochrome oxidase subunit b`、`coi` 下的 `cytochrome c oxidase gene` 过于笼统；`cox2/cox3` 缺 `COII/COIII` 缩写。

---

## 4. 已文档化的已知限制（未重复计为 bug）

- its1-its2 优先返回会吞掉跨区段 rRNA 记录的 18S/28S 部分（README Limitations 1；真实数据 9/175，如 AY210840）。L-06 中的 `its` 英文词是同一机制被“非 rRNA 记录”触发的新情形。
- 同一物种 voucher 字符串相同即合并（README Limitations 5）。
- 长度过滤默认 150–50,000 bp（README Limitations 3，且 L-13 补充了其建议不足）。

## 5. 检查过但未发现问题

- extract 的 Ref 字段：用独立的逐行解析器重新读取 548 条记录的 REFERENCE，对 `Ref1–3` × `Authors/Title/Journal/PubMed/Remark` 共 4940 个字段与 `final.csv` 逐一比对，0 差异（`Ref1PubMed` 去掉 `.0` 后，见 L-04）。`RefNTitle` 无错位（`scratch/e4_refs.py`）。
- `LocusID = record.id` 即 `accession.version`；`Version` 列仅存版本数字（547 个 `1`，1 个 `2`），两者并存，无拼接错误；真实数据 548 个 LocusID 唯一。缺 ACCESSION 行的记录 Biopython 用 LOCUS 名补齐，不报错。
- `Organism`（注释行）与 `organism`（source 限定词）在真实数据 548 条中完全一致。
- `--stream` 与非 stream 的 `final.csv` 在公共列上逐格相同；两种模式 `-oam/-oeam`（只装配/只元数据）均可运行。
- `Length` 列 “N bp”：在输入全为数字时 classify 解析正确（L-03 只在出现缺失行时出问题）。
- 真实数据分类审计（`g2t/markers/labeled_genes/assigned_genes_types_all.csv`，496 条）逐 gene_type 核对 Definition：coi 270（3 种标准说法）、28s 122、18s 44、16s 37（均带 `; mitochondrial` 且 organelle=mitochondrion）、h3 11、its1-its2 9（6 条 18S+ITS1、3 条 5.8S/ITS2/28S，属已知限制）、mtgenome 3。未发现误配。106 条 28s 的 voucher 名带 `28S_` 前缀，确为 28S；未匹配的 22 条全是 FOXA3/Hox/enolase/TSA；被过滤的 30 条全是 <150 bp 的 FOXA3/Hox/LINE 片段；`record_status.csv` 548 = 496 + 22 + 30；无冲突记录。
- 关键词边界反例（`scratch/c14_negatives.py`）：`COX11`、`cytochrome c oxidase subunit 10`、`cytochrome oxidase subunit IV`、`COIL`、`histone H3K27`、`H4`、`H2A`、`elongation factor 2`、`cytochrome b5`、`cytochrome b6-f` 均不误配；`subunit I` 不会匹配 `subunit II/III`（`\b` 保护）。
- `gene_dict.yaml` 与 `classify._BUILTIN_GENE_DICT` 的 13 个基因、全部同义词完全一致（pyyaml 缺失时的回退不会改变结果）。
- 第 1、2 轮结果合并：第 2 轮输入是第 1 轮未匹配行，两部分互不相交，按 `LocusID` 去重不会丢掉不同基因。
- voucher 在真实数据上：496 条 → 435 个键，按“小写去标点”归一后无碰撞；`pse` 取自 `specimen_voucher`（385）/`isolate`（98）/ACCESSION 回退（13）；`NaN` 物种名与 `safe_concat` 行为符合预期（仅 L-22 的空白/标点情形例外）。
- organize 在真实数据上：四种 `metadata_mode`（first_nonempty/advanced/per_gene/all）均成功；first_nonempty 的 13 个基因列与已发布矩阵一致；496 条 assigned 全部出现在矩阵，且只出现在其 gene_type 对应的列（mtgenome 传播除外，见 L-08）。per_gene 模式 496 行耗时约 30 s（O(n²)），无错误。
- `utils.sanitize_string`：NFKC、去引号/括号、空白与 `<>:./\|?*` 转 `_`、`NaN/None` 返回空串，均符合设计；`safe_concat` 对空值处理正确。
- `extract_assembly_*` 三种策略：真实数据 518 条 Sequencing Technology、2 条 Assembly Method、1 条 Assembly Name 均提取正确。
