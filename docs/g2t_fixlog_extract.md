# g2t extract.py 修复日志（L-01/02/04/05/19/20/21/24）

仅修改 `vendor/gb2taxonomy/src/g2t/extract.py` 与新增 `vendor/gb2taxonomy/tests/test_extract_fixes.py`。
每项先在原代码上确认测试失败再修复；最终 29 项测试在原代码（git HEAD 的 extract.py，用 git archive 单独验证）上 24 项失败，其余 5 项为不应失败的对照/负例（通过）。

| 编号 | 改动 | 测试 |
|---|---|---|
| L-04 | `combine_and_save_final_csv`：metadata/assembly 两处 `read_csv` 改为 `dtype=str, keep_default_na=False`，左合并后 `fillna("")`；`extract()` 行数统计同样用 `dtype=str, keep_default_na=False`。`007`/`1E5`/大整数/`NA`/Ref1PubMed 不再被改写 | `TestL04NumericText::test_combine_preserves_leading_zeros_and_big_numbers`, `::test_end_to_end_final_csv_keeps_text[True/False]` |
| L-19 | `parse_source_feature`：第一个 `taxon:` 仍进 `TaxonID`；非 taxon 的 `db_xref`（BOLD:xxx 等，以及多余的 taxon:）以 `; ` 连接写入 `db_xref` 列 | `TestL19DbXref::test_parse_source_feature_keeps_non_taxon_xrefs`, `::test_taxon_only_leaves_db_xref_empty`, `::test_end_to_end_db_xref_column` |
| L-21 | `extract_metadata`：多个 source feature 时取第一个并 `logger.warning`（含 ACCESSION、个数）；无 source（或 source 无 /organism）时 `organism` 回退到 `record.annotations["organism"]` | `TestL21SourceFeature::test_multiple_sources_use_first_and_warn`, `::test_single_source_does_not_warn`, `::test_missing_source_falls_back_to_annotation_organism`, `::test_source_organism_wins_over_annotation` |
| L-24 | `_process_record_loop`：`track.has_assembly_data` 提前到 callback 之前赋值，callback 异常时 `assembly_failed` 真正计数，汇总里 Assembly coverage 不再恒为 100% | `TestL24AssemblyFailed::test_assembly_failure_is_counted_and_summarised`, `::test_successful_assembly_is_not_counted_as_failed` |
| L-02a | `_process_record_loop`：文件级解析异常记入 `record_errors`（phase=parse）；新增 `count_record_terminators`（`//` 行数）与 `FileResult.records_expected`，与实际解析数对账，不等则 `logger.warning` 并写入 error_message/record_errors；有任何解析问题的文件状态为 PARTIAL（已提取>0）或 FAILED（=0），绝不再是 SUCCESS；报告 JSON 增 `records_expected`，per-file 汇总打印 Note | `TestL02Failures::test_midfile_parse_error_is_not_success`, `::test_first_record_broken_is_failed`, `::test_truncated_download_is_flagged_by_terminator_count`, `::test_intact_file_reconciles_cleanly` |
| L-20 | 新增 `canonical_metadata_columns`（BASE 列 + 其余按字母序，与 stream 的 `prescan_fieldnames` 同序同集）；非 stream 路径写 metadata 时按此 reindex 并补空串，且 assembly.csv 也始终写出（无数据时仅表头，与 stream 一致），使 stream/非 stream 的 metadata.csv 与 final.csv 列集合、列序、取值全部一致（含 Assembly 5 列） | `TestL20ColumnParity::test_stream_and_memory_final_csv_have_same_columns_and_values`, `::test_metadata_csv_columns_match_too` |
| L-01 | worker 提到模块级 `_process_single_file_batch(file, base, *, ...)`，用 `functools.partial` 绑定参数；同名文件用 `_unique_batch_names` 加序号（`x`, `x_2`...）分目录；新增 `_merge_batch_outputs`：batch 结束后按输入顺序合并为 `output_dir/metadata.csv`、`assembly.csv`、`final.csv`（text 读入，列用 `canonical_metadata_columns`，与非 batch 同列同序同值），`process_batch_mode` 增 `metadata_output/assembly_output/final_output` 参数，`extract(batch=True)` 与 `main()` 均传入；结果按输入顺序汇总；`combine_and_save_final_csv` 增 `md_delimiter/asm_delimiter` 参数使自定义分隔符不再读错 | `TestL01Batch::test_batch_workers_run_and_final_csv_matches_non_batch[True/False]`（含同名文件、与非 batch `assert_frame_equal`）, `::test_extract_batch_true_produces_final_csv` |
| L-02b | `extract()`：无效文件 `logger.warning` 并以 INVALID 记入汇总；始终（含无文件/无有效文件/异常提前返回）写 `extraction_report.json`；有失败/部分/无效文件时 warning 列出每个文件状态与原因；仍 `success=True`，仅当没有任何 SUCCESS/PARTIAL 文件或 final 不存在时 `success=False` | `TestL02Failures::test_extract_warns_about_invalid_files_and_always_writes_report`, `::test_extract_reports_partial_file_but_stays_successful`, `::test_extract_all_files_failed_returns_failure_but_writes_report` |
| L-05 | `TaxonomyService`：ete3 不可用（find_spec 为空，或 import 抛 ImportError/ModuleNotFoundError，如 3.13 无 cgi）时启用 Entrez 回退并 `logger.warning` 说明，不再 `input()` 询问；`prefetch_entrez` 按 TaxonID 每批 ≤200 调 `Entrez.efetch(db="taxonomy")`，从 LineageEx(+自身) 取 Class/Order/Family/Genus，AkaTaxIds 一并映射；结果缓存到 `output_dir/taxonomy_cache.json`（重跑不再请求，失败不入缓存），网络失败 warning "Class/Order/Family/Genus will be empty for N TaxonID(s)" 且不中断；`Entrez.email`/`api_key` 取 `NCBI_EMAIL`/`NCBI_API_KEY`（未设则不改动），请求期间临时 `max_tries=2, sleep=2` 以便离线快速失败；`process_all_files`/`process_batch_mode` 开始处预取（worker 只读缓存） | `TestL05EntrezFallback::test_fallback_fills_ranks_and_caches`, `::test_rerun_uses_cache_without_requests`, `::test_requests_are_batched_at_most_200`, `::test_network_failure_warns_and_continues`, `::test_ete3_not_installed_falls_back_without_prompt` |

## 验证结果

- `tests/test_extract_fixes.py`：29 项（原代码上 24 项失败，其余为不应失败的对照/负例）；修复后 29 项全过，连续 3 次无抖动。
- 仓库根目录全量 `python3 -m pytest -q`：344 passed（含并行修改中的其他测试文件）。`ruff check tests/test_extract_fixes.py`：All checks passed。
- 真实数据回归：`g2t.extract(["…/Priapulidae/02_原始数据/genbank/gb/markers"], tmpdir)`（真实联网 Entrez，3 个 gb、548 条记录，新输出 `scratchpad/regress/out_fix_extract/final.csv`）对比修复前 `scratchpad/regress/out_old/gb_metadata/final.csv`（均按 `dtype=str, keep_default_na=False` 读入）：
  - 形状 548x61 vs 548x61，列名与列序完全相同，ACCESSION 顺序相同；
  - 仅 6 列有差异：`Ref1PubMed` 109 行（逐行核对仅为去掉尾部 `.0`，如 `32671913.0` -> `32671913`）；`Class/Order/Family/Genus` 各 548 行（原全空，新为 Priapulimorpha / Priapulimorphida / Priapulidae / Priapulopsis、Priapulus、Halicryptus，5 个 TaxonID 一次 Entrez 请求）；`db_xref` 1 行（MG421729：`BOLD:CCANN086-07.COI-5P`）；
  - 其余 55 列逐值完全相同。
  - 同目录重跑：日志无 Entrez 请求（读 `taxonomy_cache.json`）；`stream=False`、`batch=True,max_tasks=3`、CLI `--batch --stream` 三种模式的 final.csv 与 stream 输出逐值完全相同（`DataFrame.equals`）。
  - 548 条记录 `//` 计数与解析数一致，3 个文件全部 SUCCESS，无新增警告。

## 行为变化备注

- ete3 不可用时不再 `input()` 询问“Continue without taxonomy?”（已有 Entrez 回退）。
- `FileResult` 新增 `records_expected`，`extraction_report.json` 每个文件多一个 `records_expected` 字段。
- `process_batch_mode` / `combine_and_save_final_csv` 仅新增带默认值的参数，向后兼容。
- 解析数多于 `//` 数（末条无终止符，典型为下载被截断）也判为 PARTIAL 并告警。
- 未改动：PARTIAL 文件仍不会被 `main()` 归档到 `failed_extract/`（`get_failed_files` 仅含 FAILED/INVALID/EMPTY）；单条记录解析失败后仍不会继续解析同文件后续记录（只对账并告警，未改为按 `//` 切分逐条解析）。
