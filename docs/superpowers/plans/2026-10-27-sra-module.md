# yzz `sra` Module Implementation Plan (rev 2: metadata only)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python3 yzz.py sra all <Taxon>` (or `--runs` / `--runinfo`) builds one SRA metadata master table (RunInfo + kingfisher-style annotation + lineage + derived data type), an Excel report, and a filtered run list for kingfisher. No downloading.

**Architecture:** yzz module `modules/sra/` with steps 01–05, each reading the previous TSV and writing its own. Module-local libraries: `eutils.py` (HTTP E-utilities with injectable transport, retries, identity), `parse.py` (pure parsers), `classify.py` (pure dataframe rules + summaries + selection).

**Tech Stack:** Python 3.13, pandas, defusedxml 0.7.1, urllib, openpyxl via `lib/excel.write_workbook`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-sra-module-design.md` (rev 2)

## Global Constraints

- Repo `/mnt/p/yzz-分类工作流`; steps `modules/sra/NN_name.py <Taxon>`; `main(argv, eutils=None) -> int` so tests inject a fake client; `argparse.parse_known_args`.
- Paths via `common.data_dir(taxon,"sra")`, `common.report_dir(taxon,"sra")`; TSV via `common.read_tsv`/`write_tsv`; end with `common.summary(step, lines)` (≤5 lines).
- Identity: env `NCBI_EMAIL`/`NCBI_API_KEY` override `config/ncbi.json`; never print the key; throttle 0.11 s with key, 0.35 s without.
- RunInfo columns/values untouched; derived columns end `_derived`; XML via `defusedxml.ElementTree`.
- `git add` explicit paths only (user has unrelated uncommitted edits). Trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tests: `python3 -m pytest -q modules/sra/tests`.

## Review Focus

1. Ambiguous / unknown taxon name → exit non-zero listing candidates (`test_resolve_taxid_ambiguous`, Task 1).
2. NCBI 200 response with error body (HTML, JSON `error`, XML `<ERROR>`) → retried, then non-zero exit, no output claiming success (`test_error_body_retried_then_fails`, Task 1).
3. `--runs` list containing withdrawn/unknown/blank/duplicate accessions → found runs processed, unknown listed in `runs_not_found.txt` and QC (`test_runs_not_found`, Task 1).
4. Web-downloaded RunInfo with Excel quirks (UTF-8 BOM, repeated header rows, TaxID as `46593.0`) → read correctly (`test_runinfo_file_quirks`, Task 1; `test_norm_taxid`, Task 3).
5. Taxon with zero runs → all steps finish, Excel shows 0 runs, empty run list (`test_empty_pipeline`, Task 4).

---

### Task 1: client + 01_runinfo

**Files:** create `modules/sra/eutils.py`, `modules/sra/parse.py`, `modules/sra/01_runinfo.py`, `modules/sra/tests/conftest.py` (FakeTransport: list of (substring, body) rules, records URLs; `tmp taxon` fixture `_test_sra` removed after), `modules/sra/tests/test_runinfo.py`, fixtures `fixtures/runinfo.csv` (BOM, a repeated header row, blank line, 2 runs sharing one Experiment).

**Interfaces:**
- `eutils.EutilsError(RuntimeError)`; `load_identity(root: Path) -> tuple[str|None,str|None]`
- `Eutils(email=None, api_key=None, transport=None, retries=5, sleep=time.sleep)`: `get(endpoint, params) -> str`; `esearch(db, term, retmax=0) -> dict(count:int, webenv:str, query_key:str, ids:list[str])` (always usehistory); `efetch_history(db, webenv, query_key, count, rettype, retmode, page=500) -> Iterator[str]`; `efetch_ids(db, ids, rettype="", retmode="xml") -> str`
- `resolve_taxid(eu, name) -> str` (numeric passthrough; 0 hits / >1 hits → EutilsError listing candidates)
- `parse.parse_runinfo(text: str) -> list[dict]` (strip BOM, drop blank and `Run=="Run"` rows)
- 01 CLI: `<Taxon> [--taxid ID] [--query CLAUSE] [--runs FILE] [--runinfo FILE] [--max-experiments 200000]`. Outputs `runinfo.tsv` (dedup by Run, original column order), `manifest.json` {taxon, mode, taxid, term, date, esearch_count, experiments, runs, not_found, ok, problems}, `runs_not_found.txt` when `--runs`.
- Modes: taxon → term `txid<id>[Organism:exp]` (+ ` AND (<query>)`), check unique Experiment == count else ok=false, exit 1; `--runs` → batches of 200 `A[accn] OR …` → runinfo; requested-but-absent → not_found; `--runinfo` → read file, no network.

- [ ] Step 1: tests `test_parse_runinfo_quirks`, `test_identity_env_overrides_config`, `test_resolve_taxid_ambiguous`, `test_error_body_retried_then_fails` (5 calls then EutilsError), `test_step01_taxon_invariant_ok`, `test_step01_invariant_mismatch` (exit 1, problems mention Experiment), `test_max_experiments_guard` (exit 2, no efetch), `test_runs_not_found`, `test_runinfo_file_quirks`.
- [ ] Step 2: run → FAIL. Step 3: implement. Step 4: run → PASS; live `python3 yzz.py sra 01 Polynoidae` ≥495 experiments ok.
- [ ] Step 5: commit `feat(sra): 01 runinfo (taxon / run list / web csv)`.

### Task 2: 02_annotate (kingfisher-style SRA XML)

**Files:** create `modules/sra/02_annotate.py`; modify `parse.py`; test `tests/test_annotate.py`; fixture `fixtures/sra_pkg.xml` (real EXPERIMENT_PACKAGE for SRR37048088 wrapped in `<EXPERIMENT_PACKAGE_SET>`, contact emails removed).

**Interfaces:**
- `parse.parse_sra_packages(xml: str) -> list[dict]`: one dict per RUN; keys `Run, experiment_title, design_description, study_title, study_abstract, study_links (json), organisation, organisation_department, organisation_country, sample_title, sample_alias, number_of_runs_for_sample`, plus every `SAMPLE_ATTRIBUTE` TAG→VALUE (skip tags with no VALUE; tag clashing with an existing key gets prefix `sample_`). No contact name/email.
- 02: Runs from `runinfo.tsv` → esearch `[accn]` batches of 200 (history) → `efetch_history(db="sra", rettype="", retmode="xml")` pages 200 → `annotate.tsv` keyed Run. Runs missing from XML → `annotate_missing.txt`; >1 % missing → exit 1.

- [ ] Step 1: tests `test_parse_sra_package` (experiment_title "Genome skimming dataset of Alentiana barnichae", study_title startswith "Phylogenomic studies of the genus Alentiana", collection_date "2019-06-09", no key containing "email"), `test_attribute_without_value_skipped`, `test_step02_keys_by_run`.
- [ ] Step 2–4: FAIL → implement → PASS; live on Polynoidae.
- [ ] Step 5: commit `feat(sra): 02 annotate from SRA XML`.

### Task 3: 03_taxonomy

**Files:** create `modules/sra/03_taxonomy.py`; modify `parse.py`; test `tests/test_taxonomy.py`; fixture `fixtures/taxonomy.xml` (one species-rank, one genus-rank taxon).

**Interfaces:** `parse.norm_taxid(s: str) -> str` ("46593.0"→"46593", ""→""); `parse.parse_taxonomy_xml(xml) -> list[dict]` keys `TaxID, rank_derived, phylum, class, order, family, genus, species` ("" when absent). 03 writes `taxonomy.tsv`; batches of 200 ids; ids not returned → QC file `taxonomy_missing.txt`.

- [ ] Step 1: tests `test_norm_taxid`, `test_parse_taxonomy_ranks` (genus-rank record species ""), `test_step03_dedup_ids` (two runs same TaxID → one request id).
- [ ] Step 2–4; commit `feat(sra): 03 lineage`.

### Task 4: rules + 04_table (merge, derived type, Excel)

**Files:** create `modules/sra/rules.json`, `modules/sra/classify.py`, `modules/sra/04_table.py`; tests `tests/test_classify.py`, `tests/test_table.py`.

**Interfaces:**
- `rules.json`: `{"low_max_gb":0.5,"shallow_max_gb":10,"long_platforms":["PACBIO_SMRT","OXFORD_NANOPORE"],"pcr_selections":["PCR","RT-PCR"],"metagenomic_sources":["METAGENOMIC","METATRANSCRIPTOMIC"]}` (short = any platform not long and not CAPILLARY).
- `classify.load_rules(path=None) -> dict`; `classify_runs(df, rules) -> df` adds `platform_type_derived, sample_key_derived, sample_total_Gb_derived, category_derived, category_rule_derived` per spec §5 (rule text e.g. `WGS & RANDOM & short & 1.84 Gb in [0.5,10) -> shallow_WGS`); `summarize_samples(df) -> df` (one row per sample_key×category: TaxID, ScientificName, BioProject, BioSample, category_derived, n_runs, total_Gb, Platform, LibraryLayout, runs `;`-joined, experiment_title, study_title, geo_loc_name, lat_lon, collection_date, specimen_voucher, isolate, tissue when present); `summarize_species(samples, taxonomy) -> df` (one row per TaxID: lineage + `<cat>_samples`, `<cat>_Gb`).
- 04 writes `table.tsv` (runinfo ⟵left⟶ annotate on Run ⟵left⟶ taxonomy on norm TaxID; assert rows == runinfo rows), `samples.tsv`, `species_summary.tsv`, and Excel `report_dir/<Taxon>_SRA_<date>.xlsx` with sheets `Summary, Samples, shallow_WGS, deep_WGS, long_read_WGS, RNA-Seq, Hi-C, Other, Runs, QC, Query`; header cells of `_derived` columns filled `lib/excel.YELLOW`.
- QC rows (`issue, Run, detail`): WGS_PCR_suspect, WGS_metagenomic, low_data_WGS, empty_BioProject, run_not_found, annotate_missing, taxonomy_missing, manifest problems.

- [ ] Step 1: tests `test_rule_pcr`, `test_rule_metagenomic`, `test_rule_long`, `test_thresholds` (0.49/0.5/9.99/10.0 → low/shallow/shallow/deep), `test_sample_sum_excludes_pcr`, `test_empty_biosample_uses_run`, `test_rnaseq_raw_and_long`, `test_rule_text`, `test_merge_preserves_rows`, `test_excel_sheets` (11 sheet names in order), `test_empty_pipeline`, `test_requires_inputs` (missing runinfo.tsv → SystemExit mentions runinfo.tsv).
- [ ] Step 2–4; live Polynoidae; commit `feat(sra): 04 master table and Excel`.

### Task 5: 05_select + docs + live acceptance

**Files:** create `modules/sra/05_select.py` (selection in `classify.select_samples`), `modules/sra/README.md`, `modules/sra/REQUIREMENTS.md`, `modules/sra/tests/check_polynoidae.py` (live, PASS/FAIL print style), `/root/.claude/skills/yzz-sra/SKILL.md`; modify repo `README.md` module list, `yzz.py` `__doc__` (sra usage line). Tests `tests/test_select.py`.

**Interfaces:** `classify.select_samples(samples, types: list[str], platforms: list[str]|None, layout: str, top: int, per: str="sample") -> df`; group (TaxID, BioProject, category_derived), sort total_Gb desc. 05 CLI per spec §7; writes `selected_<tag>.tsv`, `run_list_<tag>.txt` (all runs of selected samples, one per line); summary: samples, runs, total Gb, and the line `kingfisher get --run-identifiers-list <path> -m ena-ftp aws-http prefetch -f fastq.gz` as a hint.

- [ ] Step 1: tests `test_top_per_group`, `test_selected_sample_brings_all_runs`, `test_layout_filter`, `test_per_run_mode`, `test_sp_taxids_not_collapsed`.
- [ ] Step 2–4.
- [ ] Step 5: live `python3 yzz.py sra all Polynoidae && python3 modules/sra/tests/check_polynoidae.py` all PASS; `--runs` with 10 SRRs and `--runinfo` with the user's `/mnt/j/OneDrive/桌面/20260919桌面文件汇总/Nereidia_SraRunInfo_20260302_SraRunInfo.csv` run; `time python3 yzz.py sra all Annelida` < 15 min and PRJNA551036 all `WGS_PCR_suspect`; `python3 -m pytest -q modules/sra/tests tests`; `python3 yzz.py zh check modules/sra/README.md`.
- [ ] Step 6: commit `feat(sra): 05 select, docs, skill, live check`.
