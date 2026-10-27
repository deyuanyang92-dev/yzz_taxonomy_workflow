# yzz `sra` Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python3 yzz.py sra all <Taxon>` inventories a taxon's NCBI SRA resources (RunInfo + experiment/project titles + BioSample attributes + lineage), derives data categories (shallow/deep/long-read WGS, RNA-Seq, Hi-C…), exports an Excel report and a download list; `sra 08` downloads with kingfisher.

**Architecture:** New yzz module `modules/sra/` with numbered single-purpose steps that read the previous step's TSV and write their own (repo convention). Shared code in three module-local libraries: `eutils.py` (HTTP E-utilities client, retries, identity), `parse.py` (pure parsers), `classify.py` / `select.py` (pure dataframe logic). All network access goes through one injectable transport so tests run offline.

**Tech Stack:** Python 3.13, pandas, openpyxl (via `lib/excel.write_workbook`), defusedxml 0.7.1 (installed), urllib (no edirect on this machine), pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-sra-module-design.md`

## Global Constraints

- Repo root: `/mnt/p/yzz-分类工作流`. Steps: `modules/sra/NN_name.py <Taxon>`; paths only via `common.data_dir(taxon, "sra")` / `common.report_dir(taxon, "sra")`; finish with `common.summary(step, lines)` (≤5 lines); TSV via `common.read_tsv` / `common.write_tsv` (all `dtype=str`).
- Each step parses its own args with `argparse.parse_known_args` (unknown args from `all` are ignored, same as genbank).
- NCBI identity: env `NCBI_EMAIL` / `NCBI_API_KEY` override `config/ncbi.json` (`{"email","api_key"}`). Never hard-code, never print the key. Rate: 0.11 s between requests with key, 0.35 s without.
- NCBI raw columns are never modified or renamed. Every derived column name ends in `_derived`.
- Excel headers English; README/summaries Chinese; no U+3000.
- Taxon query is always `txid<id>[Organism:exp]` (never free text, never BioProject expansion).
- Invariant for step 01: unique `Experiment` count == esearch Count (db=sra counts experiments); runs ≥ that.
- WGS thresholds live in `modules/sra/rules.json`: `low_max_gb` 0.5, `shallow_max_gb` 10.
- XML parsed only with `defusedxml.ElementTree`.
- Do not commit the user's unrelated working-tree changes (`.gitignore`, `CLAUDE.md`); `git add` explicit paths only. Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run tests from repo root: `python3 -m pytest -q modules/sra/tests`.

## Review Focus

1. Taxon name not found or ambiguous (homonyms across kingdoms, typos) → step 01 exits non-zero listing candidate taxids with their lineage; never silently picks one. (Task 1 test `test_resolve_taxid_ambiguous`.)
2. NCBI returns HTTP 200 with an error body (HTML page, `{"error":...}`, `<ERROR>`) or a short page → treated as failure, retried, then step exits non-zero and leaves no `runinfo.tsv` claiming success. (Task 1 test `test_error_body_is_retried_then_fails`.)
3. Taxon with zero SRA records → every step completes, writes empty-but-headed TSVs, Excel says "0 runs"; no crash downstream. (Task 5 test `test_classify_empty`, Task 6 test `test_export_empty`.)
4. Very large taxon (e.g. Metazoa, millions of runs) → step 01 stops before downloading when esearch Count > `--max-experiments` (default 200000) and tells the user to pass a larger value. (Task 1 test `test_max_experiments_guard`.)
5. BioSample numeric-ID collision: `efetch db=biosample&id=SAMD01936330` returns human `SAMN01936330` (verified 2026-10-27) → step 03 must resolve accessions via `esearch term=<acc>[accn]` and drop/QC any returned record whose accession differs from the requested one. (Task 3 test `test_biosample_accession_mismatch_dropped`.)

**Deferred (spec marks optional / phase 2):** `--since auto` incremental fetch, `--coverage` estimated coverage from assembly size, response cache in `cache/sra/`.

---

### Task 1: E-utilities client, parsers for RunInfo, step 01_runinfo

**Files:**
- Create: `modules/sra/eutils.py`, `modules/sra/parse.py`, `modules/sra/01_runinfo.py`
- Test: `modules/sra/tests/test_runinfo.py`, `modules/sra/tests/conftest.py`, `modules/sra/tests/fixtures/runinfo_page1.csv` (5 rows incl. one repeated header line and one blank line, 2 runs sharing one Experiment)

**Interfaces:**
- Produces (`eutils.py`):
  - `class EutilsError(RuntimeError)`
  - `load_identity(root: Path) -> tuple[str|None, str|None]` (email, api_key)
  - `class Eutils(email=None, api_key=None, transport: Callable[[str], str] | None = None, retries=5, sleep=time.sleep)`
    - `get(endpoint: str, params: dict) -> str` — builds URL on `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`, adds email/api_key/tool=`yzz-sra`, throttles, retries with backoff `2**i` s; a body that starts with `<!DOCTYPE html`, contains `"error":` at top level of JSON, or contains `<ERROR>` raises internally and is retried.
    - `esearch(db: str, term: str, history=True, retmax=0) -> dict` keys `count:int, webenv:str, query_key:str, ids:list[str]`
    - `efetch_history(db, webenv, query_key, count, rettype, retmode="text", page=500) -> Iterator[str]`
    - `esummary_history(db, webenv, query_key, count, page=500) -> Iterator[dict]` (parsed JSON `result` minus `uids`)
    - `efetch_ids(db, ids: list[str], retmode="xml") -> str`
    - `esummary_ids(db, ids: list[str]) -> dict`
  - `resolve_taxid(eu: Eutils, name: str) -> str` — esearch db=taxonomy `"<name>"[Scientific Name]`; 0 hits → `EutilsError("未找到类群 …")`; >1 → `EutilsError` whose message lists each candidate `taxid  name  lineage-tail`. A purely numeric `name` is returned as is.
- Produces (`parse.py`): `parse_runinfo(text: str) -> list[dict]` — csv.DictReader; drops blank rows and rows where `Run == "Run"`.
- Produces (files): `data_dir/runinfo.tsv` (all NCBI columns, deduped by `Run`, original column order), `data_dir/manifest.json` keys `taxon, taxid, term, date, esearch_count, experiments, runs, empty_bioproject, ok:bool, problems:list[str]`.

- [ ] **Step 1: Write failing tests** in `test_runinfo.py` using a `FakeTransport` (conftest fixture: maps URL substrings → response bodies, records calls):
  - `test_parse_runinfo_drops_header_and_blank` — fixture file → 4 runs, no row with `Run=="Run"`.
  - `test_identity_env_overrides_config` — tmp config `{"email":"a@x","api_key":"K1"}`, env `NCBI_API_KEY=K2` → `("a@x","K2")`.
  - `test_resolve_taxid_ambiguous` — fake esearch returns 2 ids → raises `EutilsError`, message contains both ids.
  - `test_error_body_is_retried_then_fails` — transport always returns `<!DOCTYPE html>…`; `sleep` stubbed; `get` raises `EutilsError` after exactly 5 calls.
  - `test_step01_invariant_ok` — run `01_runinfo.main(["_t", "--taxid", "46593"])` with fake count 3 and pages giving 3 unique Experiments / 4 runs → exit 0, `manifest["ok"] is True`, tsv has 4 rows.
  - `test_step01_invariant_mismatch` — count 4 but only 3 Experiments → exit 1, manifest `ok False`, `problems` mentions `Experiment`.
  - `test_max_experiments_guard` — count 300000, default guard → exit 2 before any efetch call; message contains `--max-experiments`.
  Steps take `main(argv, eutils=None) -> int` so tests inject `Eutils(transport=fake, sleep=lambda s: None)`. Use taxon `_test_sra` and delete `projects/_test_sra` in a fixture teardown.

- [ ] **Step 2: Run** `python3 -m pytest -q modules/sra/tests/test_runinfo.py` → FAIL (module not found).

- [ ] **Step 3: Implement** `eutils.py`, `parse.parse_runinfo`, `01_runinfo.py`. CLI: `<Taxon> [--taxid ID] [--query CLAUSE] [--max-experiments 200000] [--ena]`. Term = `txid<id>[Organism:exp]` + (` AND (<query>)` if given). Write `runinfo.tsv` only after the invariant check; on mismatch still write it but `ok=false` and exit 1. `--ena`: GET `https://www.ebi.ac.uk/ena/portal/api/search?result=read_run&query=tax_tree(<id>)&fields=run_accession&format=tsv&limit=0`, write `ena_diff.tsv` columns `run, in_ncbi, in_ena` (only differences). Summary lines: taxid+name, experiments/runs, empty BioProject count, ENA diff if any.

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Live smoke** `python3 yzz.py sra 01 Polynoidae` → summary shows ≥495 experiments, ≥525 runs, `ok`.

- [ ] **Step 6: Commit** `git add modules/sra/eutils.py modules/sra/parse.py modules/sra/01_runinfo.py modules/sra/tests && git commit -m "feat(sra): step 01 runinfo via taxid subtree with count invariant"`

### Task 2: step 02_details (experiment + BioProject titles)

**Files:**
- Create: `modules/sra/02_details.py`; Modify: `modules/sra/parse.py`
- Test: `modules/sra/tests/test_details.py`, fixture `fixtures/esummary_sra.json` (one item; real shape: keys `uid, expxml, runs, extlinks, createdate, updatedate`; `expxml` is HTML-escaped XML fragment without a root, e.g. `<Summary><Title>Genome skimming dataset of Alentiana barnichae</Title>…</Summary><Experiment acc="SRX31994618" …/><Study acc="SRP671674" name="Phylogenomic studies of the genus Alentiana…"/>…<Library_descriptor><LIBRARY_NAME>MBM-286815</LIBRARY_NAME>…`)

**Interfaces:**
- Consumes: `Eutils.esearch`, `Eutils.esummary_history`, `Eutils.esummary_ids`; `manifest.json["term"]`.
- Produces: `parse_expxml(item: dict) -> dict` keys `Experiment, experiment_title, study_title, library_name, library_construction_protocol, center_name` (wrap fragment in `<r>…</r>` after `html.unescape`); `parse_bioproject_summary(item: dict) -> dict` keys `ProjectID, project_title, project_description`.
- Produces files: `experiment.tsv` (key `Experiment`), `bioproject.tsv` (key `ProjectID` = runinfo's numeric `ProjectID`; esummary db=bioproject needs the numeric UID, accessions fail — verified).

- [ ] **Step 1: Failing tests** `test_parse_expxml` (title == "Genome skimming dataset of Alentiana barnichae", Experiment == "SRX31994618", library_name == "MBM-286815"); `test_step02_writes_both_tables` (fake transport; experiment.tsv rows == unique Experiment in runinfo; missing experiments listed in summary, exit 0 with warning when ≤1 % missing, exit 1 above).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Re-run the esearch with `manifest["term"]` (history), page esummary 500; BioProject esummary in batches of 200 ProjectIDs.
- [ ] **Step 4: Run** → PASS; live `python3 yzz.py sra 02 Polynoidae`.
- [ ] **Step 5: Commit** `feat(sra): step 02 experiment and bioproject titles`.

### Task 3: step 03_biosample

**Files:**
- Create: `modules/sra/03_biosample.py`; Modify: `modules/sra/parse.py`
- Test: `modules/sra/tests/test_biosample.py`, fixture `fixtures/biosample.xml` (two `<BioSample accession=…>` records with `<Attributes>`; one attribute lacking `harmonized_name`)

**Interfaces:**
- Produces: `parse_biosample_xml(xml: str) -> list[dict]` — each dict: `BioSample` (accession attr), `biosample_title`, `biosample_organism`, `biosample_taxid`, plus one key per attribute = `harmonized_name` or else `attribute_name` (raw text; duplicate keys joined with ` | `).
- Produces file: `biosample.tsv` keyed `BioSample`; `biosample_missing.txt` (requested but not returned or mismatched).

- [ ] **Step 1: Failing tests** `test_parse_biosample_attributes` (harmonized key used; fallback attribute_name used); `test_biosample_accession_mismatch_dropped` (request `SAMD01936330`, fake returns record `accession="SAMN01936330"` → not in output, listed in missing).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Unique non-empty `BioSample` from runinfo; batches of 100: `esearch db=biosample term="A[accn] OR B[accn] …" retmax=100` → UIDs → `efetch_ids("biosample", uids)`; keep only records whose accession ∈ requested batch. Summary: n requested / n got / n missing.
- [ ] **Step 4: Run** → PASS; live step on Polynoidae.
- [ ] **Step 5: Commit** `feat(sra): step 03 biosample attributes with accession check`.

### Task 4: step 04_taxonomy

**Files:**
- Create: `modules/sra/04_taxonomy.py`; Modify: `modules/sra/parse.py`
- Test: `modules/sra/tests/test_taxonomy.py`, fixture `fixtures/taxonomy.xml` (2 `<Taxon>`: one rank species, one rank genus)

**Interfaces:**
- Produces: `parse_taxonomy_xml(xml: str) -> list[dict]` keys `TaxID, tax_name, rank_derived, phylum, class, order, family, genus, species, lineage` (ranks from `LineageEx` plus the taxon itself; missing → "").
- Produces file: `taxonomy.tsv` keyed `TaxID`.

- [ ] **Step 1: Failing tests** `test_parse_taxonomy_ranks` (species record fills genus+species; genus-rank record has species ""); `test_taxid_float_string` — runinfo TaxID `"46593.0"` is normalised to `"46593"` before querying (helper `norm_taxid(s: str) -> str` in `parse.py`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Unique TaxIDs, `efetch_ids("taxonomy", batch of 200)`. QC list: taxids whose lineage does not contain the manifest taxid → `taxonomy_outside_taxon.txt`.
- [ ] **Step 4: Run** → PASS; live on Polynoidae.
- [ ] **Step 5: Commit** `feat(sra): step 04 lineage from NCBI taxonomy`.

### Task 5: rules + step 05_classify

**Files:**
- Create: `modules/sra/rules.json`, `modules/sra/classify.py`, `modules/sra/05_classify.py`
- Test: `modules/sra/tests/test_classify.py`

**Interfaces:**
- `rules.json`: `{"low_max_gb": 0.5, "shallow_max_gb": 10, "short_platforms": ["ILLUMINA","BGISEQ","DNBSEQ","ION_TORRENT","ABI_SOLID","LS454","ELEMENT","ULTIMA"], "long_platforms": ["PACBIO_SMRT","OXFORD_NANOPORE"], "pcr_selections": ["PCR","RT-PCR"], "metagenomic_sources": ["METAGENOMIC","METATRANSCRIPTOMIC"]}`
- `load_rules(path: Path | None = None) -> dict`
- `platform_type(platform: str, rules) -> str` → `short|long|other`
- `classify_runs(runs: pd.DataFrame, rules) -> pd.DataFrame` — adds `platform_type_derived, sample_key_derived` (BioSample or Run if empty), `sample_total_Gb_derived` (float, 3 dp), `category_derived`, `category_rule_derived`. Rule order exactly spec §6 (1 WGS_PCR_suspect, 2 WGS_metagenomic, 3 long_read_WGS, 4 low_data_WGS, 5 shallow_WGS, 6 deep_WGS, 7 long_read_RNA, 8 LibraryStrategy raw). Rules 1–2 evaluated per run first; those runs excluded from sample totals. Total groups by (`sample_key_derived`, `LibraryStrategy`, `platform_type_derived`). Comparison case-insensitive. Rule text format: `WGS & RANDOM & short & 1.84 Gb in [0.5,10) -> shallow_WGS`.
- `summarize_samples(runs_classified: pd.DataFrame) -> pd.DataFrame` one row per (`sample_key_derived`, `category_derived`): `TaxID, ScientificName, BioProject, BioSample, category_derived, n_runs, total_Gb, Platform` (unique joined `;`), `LibraryLayout`, `runs` (`;`-joined).
- `summarize_species(samples: pd.DataFrame, taxonomy: pd.DataFrame) -> pd.DataFrame` one row per `TaxID`: lineage columns + for each category present `<cat>_samples`, `<cat>_Gb`.
- Files: `runs_annotated.tsv` (runinfo + experiment cols + taxonomy cols + derived; merge on keys, assert `len` unchanged), `samples.tsv`, `species_summary.tsv`.

- [ ] **Step 1: Failing tests** (build small DataFrames inline):
  - `test_rule_pcr_wgs` — WGS/PCR/ILLUMINA 0.08 Gb → `WGS_PCR_suspect`.
  - `test_rule_metagenomic` → `WGS_metagenomic`.
  - `test_rule_long_read` — PACBIO_SMRT WGS → `long_read_WGS`.
  - `test_thresholds` — sample totals 0.49 / 0.5 / 9.99 / 10.0 Gb → low_data / shallow / shallow / deep.
  - `test_sample_sum_excludes_pcr_runs` — same BioSample: one RANDOM run 3 Gb + one PCR run 20 Gb → RANDOM run is `shallow_WGS` with total 3.0.
  - `test_empty_biosample_uses_run` — BioSample "" → sample_key == Run.
  - `test_rnaseq_kept_raw` — RNA-Seq ILLUMINA → `RNA-Seq`; RNA-Seq PACBIO → `long_read_RNA`.
  - `test_rule_text` — contains `1.84 Gb in [0.5,10) -> shallow_WGS`.
  - `test_merge_preserves_rows` — step 05 on fixture TSVs (experiment table missing one Experiment) → runs_annotated rows == runinfo rows.
  - `test_classify_empty` — headed empty runinfo → three headed empty TSVs, exit 0.
  - `test_step05_requires_inputs` — no runinfo.tsv → SystemExit message contains `runinfo.tsv`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** CLI `<Taxon> [--rules PATH]`. Summary: counts per category (top 5).
- [ ] **Step 4: Run** → PASS; live on Polynoidae.
- [ ] **Step 5: Commit** `feat(sra): derived data categories and summaries`.

### Task 6: step 06_export

**Files:**
- Create: `modules/sra/06_export.py`
- Test: `modules/sra/tests/test_export.py`

**Interfaces:**
- Consumes: `runs_annotated.tsv`, `samples.tsv`, `species_summary.tsv`, `biosample.tsv`, `manifest.json`, QC files from 01–04, `rules.json`; `lib/excel.write_workbook(path, sheets, freeze, shade)`.
- Produces: `report_dir/<Taxon>_SRA_<YYYY-MM-DD>.xlsx` with sheets in order `Summary, Samples, shallow_WGS, deep_WGS, long_read_WGS, RNA-Seq, Hi-C, RAD-Seq, AMPLICON, Other, Runs, BioSample, QC, Query`. `Samples` and per-category sheets join BioSample columns `geo_loc_name, lat_lon, collection_date, tissue, specimen_voucher, isolate` when present, plus `experiment_title, project_title`. `Other` = every category not named in a sheet. `QC` columns `issue, Run, BioSample, detail` with issues `WGS_PCR_suspect, WGS_metagenomic, low_data_WGS, empty_BioProject, biosample_missing, taxid_outside_taxon, ena_diff, invariant` (from manifest problems). `Query` = key/value rows: taxon, taxid, term, date, esearch_count, runs, rules JSON.

- [ ] **Step 1: Failing tests** `test_export_sheets` (fixture TSVs → workbook has the 14 sheet names in order; `Runs` row count == runs_annotated rows); `test_export_empty` (empty inputs → workbook exists, `Query` shows runs 0); `test_formula_text_kept` (an experiment_title `=cmd` stays a string cell, via write_workbook).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** Derived column headers shaded: pass `shade` is row-based in write_workbook, so instead set header fill for columns ending `_derived` after writing (open with openpyxl, `YELLOW` from `lib/excel`). **Step 4: Run** → PASS; live on Polynoidae, open file list of sheets.
- [ ] **Step 5: Commit** `feat(sra): Excel report`.

### Task 7: step 07_select (download list)

**Files:**
- Create: `modules/sra/select.py`, `modules/sra/07_select.py`
- Test: `modules/sra/tests/test_select.py`

**Interfaces:**
- `select_samples(samples: pd.DataFrame, categories: list[str], platforms: list[str] | None, layout: str, top: int, per: str = "sample") -> pd.DataFrame` — filter `category_derived ∈ categories`; `platforms=None` → keep all; `layout` in `PAIRED|SINGLE|ALL` (match any run's layout in the sample); group (`TaxID`, `BioProject`, `category_derived`); sort `total_Gb` desc; keep `top`. `per="run"` explodes to runs first and applies the same on run size (old behaviour).
- CLI `07_select.py <Taxon> [--category shallow_WGS,deep_WGS,RNA-Seq] [--platform …] [--layout PAIRED] [--top 3] [--per sample|run] [--tag default]`.
- Files: `selected_<tag>.tsv` (selected sample rows), `run_list_<tag>.txt` (one Run per line, all runs of selected samples). Summary: samples, runs, total Gb.

- [ ] **Step 1: Failing tests** `test_top_per_group` (4 samples same TaxID/BioProject/category, Gb 1,5,3,2, top 3 → 5,3,2); `test_selected_sample_brings_all_runs` (sample with 2 runs → both in run list); `test_layout_filter`; `test_per_run_mode`; `test_unidentified_species_not_collapsed` (two different `sp.` TaxIDs same BioProject → both kept).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(sra): download list selection`.

### Task 8: step 08_download, doctor, dispatcher changes

**Files:**
- Create: `modules/sra/08_download.py`, `modules/sra/doctor.py`, `modules/sra/ALL_SKIP` (content: `08`)
- Modify: `yzz.py` (in `main`: before unpacking `module, sel, taxon`, if `argv[1:2] == ["doctor"]` and `MODULES/argv[0]/"doctor.py"` exists → run it; when `sel == "all"`, drop steps whose prefix is listed in `MODULES/module/ALL_SKIP`; add both to the `__doc__` usage text)
- Test: `modules/sra/tests/test_download.py`, `modules/sra/tests/fake_kingfisher.py`

**Interfaces:**
- `build_kingfisher_cmd(kingfisher: str, run: str, outdir: Path, methods: list[str], threads: int, fmt: str, md5: bool) -> list[str]` → `[kingfisher, "get", "-r", run, "-m", *methods, "-f", fmt, "--output-directory", str(outdir), "--download-threads", str(threads)] + (["--check-md5sums"] if md5 else [])`. Flag names are from the user's 2025 script `batch_download_using_kingfisherv20250220.py`; when kingfisher is installed, confirm with `kingfisher get -h` and adjust here only.
- `is_complete(run: str, outdir: Path, fmt: str) -> bool` — `run.<fmt>` or `run_1.<fmt>`+`run_2.<fmt>` exist and are non-empty.
- CLI `08_download.py <Taxon> [--tag default] [--outdir DIR (default data_dir/fastq)] [--kingfisher PATH] [-j 4] [--threads 4] [-f fastq.gz] [--methods aws-http prefetch ena-ftp] [--no-md5]`. Parallel with ThreadPoolExecutor, results consumed; failures → `download_failed_<tag>.txt`; exit 1 if any failed.
- `doctor.py`: prints found/missing + version for `kingfisher`, `fasterq-dump`, `prefetch`, `aria2c`, `ascp`, and whether NCBI identity is configured (never prints key value); exit 0 always.

- [ ] **Step 1: Failing tests** with `fake_kingfisher.py` (writes `<run>_1.fastq.gz`/`_2` unless run id ends with `9`, then exits 1): `test_cmd_shape`; `test_skip_complete` (pre-existing files → fake not called for that run); `test_failed_runs_listed` (run ending 9 → in failed file, exit 1); `test_all_skips_download` (unit-test helper `select_steps(module: str, sel: str) -> list[Path]` extracted from `yzz.main`: `select_steps("sra","all")` has no `08_download.py`; `select_steps("sra","08")` is exactly `[08_download.py]`; `select_steps("genbank","all")` unchanged); `test_doctor_runs` (exit 0, output has `kingfisher`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS, plus existing repo tests `python3 -m pytest -q tests` still PASS.
- [ ] **Step 5: Commit** `feat(sra): kingfisher download, doctor, dispatcher ALL_SKIP` (`git add yzz.py modules/sra/...` explicitly).

### Task 9: docs, skill, regression check, acceptance

**Files:**
- Create: `modules/sra/README.md` (usage block + step table like `modules/genbank/README.md`; the rule list from spec §6; evidence table from spec §2 summarized in ≤6 lines), `modules/sra/REQUIREMENTS.md` (requirements from spec §3 with status), `modules/sra/tests/check_polynoidae.py` (live; PASS/FAIL print style of `modules/genbank/tests/check_mitoz.py`), `/root/.claude/skills/yzz-sra/SKILL.md` (when to use: 用户提到 SRA、浅层/genome skimming、转录组/全基因组原始数据盘点、RunInfo、kingfisher; commands; report only summary + paths).
- Modify: repo `README.md` module list; `yzz.py` `__doc__` if not done.

- [ ] **Step 1:** Write `check_polynoidae.py` checks: manifest ok; experiments ≥495; runs ≥525; `empty_BioProject` QC rows ≥51; Excel has 14 sheets; every `category_derived` non-empty; `run_list_default.txt` non-empty.
- [ ] **Step 2:** `python3 yzz.py sra all Polynoidae && python3 modules/sra/tests/check_polynoidae.py` → all PASS.
- [ ] **Step 3:** Acceptance `time python3 yzz.py sra all Annelida` → <15 min; then `python3 -I -c` one-liner on `runs_annotated.tsv`: all 2304 runs of `PRJNA551036` have `category_derived == WGS_PCR_suspect`.
- [ ] **Step 4:** `python3 yzz.py zh check modules/sra/README.md modules/sra/REQUIREMENTS.md` (BOM/LF notices for .md are acceptable, matching the repo's other .md files; no U+3000, no mojibake); `python3 -m pytest -q modules/sra/tests tests`; `ruff check modules/sra` if ruff installed.
- [ ] **Step 5: Commit** `docs(sra): README, requirements, skill, live regression check`.
