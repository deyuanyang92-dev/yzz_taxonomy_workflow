# Mito annotation benchmark — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Knowledge base for core tools + frozen Metazoa-wide NC_ benchmark set + run/evaluate harness for ours / MitoZ / MITOS2 + first dev-set run and error report.

**Architecture:** New scripts in `temp_scripts/Mitoz-annotate/benchmark/` (sample → run → eval → report), each a small CLI with pure, unit-tested core functions. Large data under `projects/mito_benchmark/` (not git, never /tmp). Knowledge base as Markdown in `temp_scripts/Mitoz-annotate/knowledge/`, with a checker that enforces sources.

**Tech Stack:** Python 3 + Biopython, pytest, ruff, mypy; NCBI E-utilities (curl/urllib); existing conda envs found by `mito_env.py`.

**Spec:** `docs/superpowers/specs/2026-10-20-mito-annotation-benchmark-design.md`

**Out of scope (later plans):** optimisation rounds (§7, driven by Phase-1 errors), ML tRNA experiment (§4), reference-free QC (§5.6), test-set run.

## Global Constraints

- Truth = NCBI NC_ annotation (user 2026-10-20: "目前还是先根据nc注释吧").
- Taxa: all Metazoa phyla with RefSeq mitogenomes; quota 12 for big phyla, ≤6 others, ≈250 total; fixed seed `20261020`.
- Big phyla: Chordata, Arthropoda, Mollusca, Annelida, Cnidaria, Echinodermata, Nematoda, Platyhelminthes; within each, ≤2 records per order.
- dev/test split 1:1 by **genus** (no genus in both).
- Match rule: same normalised gene name + same strand + overlap ≥50 % of NCBI feature; boundary classes exact / ≤3 nt / >3 nt; "obvious error" coordinate threshold 30 nt.
- Inputs to every tool: bare sequence (source feature only), NCBI orientation, genetic code = majority CDS `transl_table`, topology from NCBI.
- MitoZ-unsupported phylum → status `unsupported`, counted in coverage, excluded from accuracy.
- Data dirs: `projects/mito_benchmark/{gb,bare,runs,eval}`; record list in git: `benchmark/sets/mito_bench_2026-10.tsv`.
- Every knowledge-base claim carries a source (URL, DOI, or `path:line`) + tool version + check date; unsupported claims marked `未确证`.
- Taxonomic content (headers, gene names) in English. Code style: match `benchmark/eval_trna.py` (plain functions, short docstrings).
- NCBI requests ≤3/s, retry with timeout.
- After any change to existing pipeline scripts: `python3 -m pytest -q tests/` and `python3 /mnt/n/yzz-分类工作流/modules/genbank/tests/check_mitoz.py` all PASS.
- Subagents: haiku for mechanical, sonnet for reading/search; prompts state "禁止再调用 Agent 开子代理" and "每完成一项就写入文件".

## Review Focus

1. Feature spanning the origin (join(15000..16500,1..200)) after lift-over from reoriented output → must map back to the same NCBI coordinates, not be dropped or split.
2. Tool crash / timeout / empty output → a row with status `failed` or `timeout` in per-record results, never silently missing.
3. NCBI tRNA without `/anticodon` (trnL/trnS ambiguous) → matched by amino acid only, flagged `name_unverifiable`, not counted as name error.
4. Record without any CDS `transl_table` → genetic code falls back to phylum default table and the row is flagged `code_assumed`.
5. Linear (`linear` in LOCUS) records → no rotation by our pipeline assumed; lift-over must handle identity mapping and the record goes into the `structure_stress` stratum.

Each is tested in the owning task (Tasks 3, 4, 5).

---

### Task 1: Knowledge-base skeleton + checker

**Files:**
- Create: `knowledge/INDEX.md`, `knowledge/tools/_TEMPLATE.md`, `knowledge/benchmark_findings.md`
- Create: `benchmark/check_knowledge.py`
- Test: `tests/test_check_knowledge.py`

**Interfaces:**
- Produces: `check_file(path: Path) -> list[str]` (problems; empty = OK); CLI `python3 benchmark/check_knowledge.py knowledge/` exits 1 on any problem.
- Template headings (exact, in order): `## Version checked`, `## What it does`, `## Algorithm & key source locations`, `## Defaults that matter`, `## Known bugs / issues`, `## Limitations by taxon`, `## Relevance to our pipeline`, `## References`.

- [ ] **Step 1: Write failing tests** in `tests/test_check_knowledge.py`:
  - `test_missing_heading` — file lacking `## Known bugs / issues` → problem list contains `"missing heading: ## Known bugs / issues"`.
  - `test_unsourced_bullet` — bullet `- MiTFi is single-core` under `## Algorithm & key source locations` → problem contains `"unsourced"`.
  - `test_sourced_bullets_ok` — bullets ending with `(mitoz/annotate/annotation.py:274)`, `(doi:10.1093/nar/gkz833)`, `(https://github.com/x/y/issues/12)`, or containing `未确证` → no problems.
  - `test_version_line_required` — `## Version checked` section without a `checked YYYY-MM-DD` → problem.
- [ ] **Step 2:** `python3 -m pytest -q tests/test_check_knowledge.py` → FAIL (module missing).
- [ ] **Step 3:** Implement `check_file`; a bullet is sourced if it matches `\(([\w./-]+:\d+|doi:\S+|https?://\S+)\)` or contains `未确证`. Bullets under `## What it does` and `## Relevance to our pipeline` are exempt. INDEX.md and benchmark_findings.md are exempt from headings.
- [ ] **Step 4:** Tests PASS; `ruff check benchmark/check_knowledge.py`; `mypy --ignore-missing-imports benchmark/check_knowledge.py`.
- [ ] **Step 5:** Commit `knowledge: skeleton and source checker`.

### Task 2: Core tool knowledge files

**Files:** Create `knowledge/tools/{mitoz,mitos2,mfannot,mitfi,arwen,aragorn,trnascan-se,table2asn,mitofinder}.md`; update `knowledge/INDEX.md`.

**Interfaces:** Consumes Task 1 template + checker.

- [ ] **Step 1:** Dispatch 3 sonnet subagents in parallel (MitoZ+MiTFi+table2asn; MITOS2+ARWEN+ARAGORN; MFannot+tRNAscan-SE+MitoFinder). Each reads: installed source (`/root/miniconda3/envs/*/lib/python*/site-packages/...`, `bin/`), GitHub repo + open/closed issues (search terms: tRNA, intron, genetic code, crash, wrong, start codon, linear), papers, docs. Writes one file per tool as soon as it is done. Prompt includes the template headings, source rule, "禁止再调用 Agent 开子代理", return ≤200-word summary.
- [ ] **Step 2:** Main thread spot-checks 3 claims per file against source (open the cited `path:line` / DOI).
- [ ] **Step 3:** `python3 benchmark/check_knowledge.py knowledge/` → exit 0.
- [ ] **Step 4:** INDEX.md lists each file with one-line scope and the open questions (`未确证` items).
- [ ] **Step 5:** Commit `knowledge: core tool notes (9 tools)`.

### Task 3: Sampling — frozen benchmark set

**Files:**
- Create: `benchmark/mito_sample.py`
- Test: `tests/test_mito_sample.py`
- Output: `benchmark/sets/mito_bench_2026-10.tsv`, `projects/mito_benchmark/gb/<acc>.gb`, `projects/mito_benchmark/bare/<acc>/<acc>.gbf`

**Interfaces:**
- `PHYLA: dict[str, int]` (phylum → quota) and `MITOZ_CLADE: dict[str, str | None]` (phylum → MitoZ `--clade` or None; values from `batch_mitoz.py:331`).
- `majority_code(rec: SeqRecord, phylum: str) -> tuple[int, bool]` (code, assumed).
- `evidence_tier(source_rec: SeqRecord) -> str` → `"A-transcriptome" | "A-longread" | "B"`.
- `annotation_method(rec: SeqRecord, source_rec: SeqRecord | None) -> str` → `"MITOS" | "MitoZ" | "MFannot" | "DOGMA" | "other:<text>" | "unknown"`.
- `structure_flags(rec: SeqRecord) -> list[str]` → subset of `["linear", "no_cox1", "multi_chromosome"]`.
- `pick(rows: list[dict], quota: int, seed: int) -> list[dict]` — prefer tier A, ≤2 per order.
- `split_by_genus(rows: list[dict], seed: int) -> None` — sets `row["split"]` to `"dev"`/`"test"`.
- TSV columns (exact order): `accession, source_accession, phylum, class, order, family, genus, species, genetic_code, code_assumed, topology, length, evidence_tier, annotation_method, refseq_created, structure_flags, mitoz_clade, split, retrieved`.

- [ ] **Step 1: Failing tests** (synthetic SeqRecords):
  - `test_majority_code` — CDS tables [5,5,5,4] → (5, False); no CDS → (phylum default, True) e.g. Annelida → (5, True).
  - `test_evidence_tier` — structured comment `Sequencing Technology :: PacBio Sequel` → `"A-longread"`; COMMENT containing `RNA-seq` → `"A-transcriptome"`; neither → `"B"`.
  - `test_annotation_method` — COMMENT `annotated with MITOS WebServer` → `"MITOS"`.
  - `test_structure_flags_linear` — `topology="linear"` → contains `"linear"`.
  - `test_split_no_genus_leak` — 20 rows, 6 genera → no genus in both splits; both splits non-empty; deterministic for same seed.
  - `test_pick_quota_and_order_cap` — rule: take ≤2 per order (tier A first, then random by seed); if still short of quota, fill from the remaining rows (tier A first). 3 orders × 10 rows, quota 12 → 6 after cap, filled to 12; 10 orders × 3 rows, quota 12 → 12 with no order >2.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement; network part `fetch_phylum(phylum: str, retmax: int) -> list[SeqRecord]` (esearch `"<phylum>[Organism] AND mitochondrion[Filter] AND complete genome[Title] AND refseq[Filter]"`, efetch `gbwithparts`, batches of 200, ≤3 req/s); source INSDC from COMMENT `The reference sequence is identical to X`; `refseq_created` = esummary `CreateDate` of the NC_ accession; taxonomy from `annotations["taxonomy"]`. CLI: `python3 benchmark/mito_sample.py --out projects/mito_benchmark --seed 20261020`.
- [ ] **Step 4:** Tests PASS; ruff, mypy clean. Run CLI for real; verify ≈250 rows, every phylum with ≥1 record present, both splits per big phylum, no genus leak (`awk` check).
- [ ] **Step 5:** Commit script, tests and TSV: `benchmark: Metazoa-wide NC_ sample set`.

### Task 4: Runner + lift-over to NCBI coordinates

**Files:**
- Create: `benchmark/mito_bench_run.py`
- Test: `tests/test_mito_bench_run.py`
- Output: `projects/mito_benchmark/runs/<tool>/<acc>/{final.gbf, status.json, log.txt}`

**Interfaces:**
- Consumes: TSV from Task 3; `mito_env.find(name, hint)` and `mito_env.mitos_refdir(...)`.
- `TOOLS = ("ours", "mitoz", "mitos2")`.
- `build_cmd(tool: str, row: dict, bare: Path, out: Path, threads: int) -> list[str] | None` — None when `tool=="mitoz"` and `row["mitoz_clade"]==""` (unsupported). `ours` = `batch_mitoz.py run` with current defaults; `mitoz` = `mitoz annotate` (no post-processing); `mitos2` = runmitos full mode, `-c <code> -r refseq89m`.
- `mitos_to_record(result_dir: Path, seq: Seq, acc: str) -> SeqRecord` — parse MITOS2 `result.bed`/`result.gff` into gene/CDS/rRNA/tRNA features (reuse `mito_trna.parse_mitos_bed` naming for tRNAs).
- `lift_to_ncbi(pred: SeqRecord, ncbi_seq: Seq) -> SeqRecord` — find rotation offset and strand by exact match of a 50-nt anchor (try forward, then reverse complement); remap every feature location (incl. CompoundLocation, origin-spanning). Raise `LiftError` if no unique anchor.
- `status.json`: `{"tool","accession","status": "ok"|"failed"|"timeout"|"unsupported","seconds": float,"step_seconds": {...},"error": str}`.
- CLI: `python3 benchmark/mito_bench_run.py --set benchmark/sets/mito_bench_2026-10.tsv --split dev --tools ours,mitoz,mitos2 --root projects/mito_benchmark --jobs 4 --threads 4 --timeout 3600`; skips records whose `status.json` exists (resume).

- [ ] **Step 1: Failing tests:**
  - `test_lift_identity` — pred == ncbi seq → features unchanged.
  - `test_lift_rotation_origin_span` — pred = ncbi seq rotated to start at ncbi position 1000; a feature at ncbi 900..1100 is `join(L-99..L, 1..101)` in pred → after lift: one location 900..1100 on ncbi, extracted sequence identical; and the reverse case (ncbi feature spanning ncbi origin) lifts to a CompoundLocation with identical extracted sequence.
  - `test_lift_reverse_complement` — pred is RC of ncbi → feature strand flipped and extracted sequence equal.
  - `test_build_cmd_unsupported` — row with empty `mitoz_clade` → `build_cmd("mitoz", ...) is None`.
  - `test_failed_tool_writes_status` — fake executable that exits 1 → `status.json` with `"status": "failed"` and non-empty `error`.
  - `test_timeout_status` — fake executable sleeping beyond `--timeout 1` → `"timeout"`.
  - `test_mitos_to_record` — small `result.bed` fixture with `cox1`, `rrnL`, `trnM_0(cat)` → three features, tRNA anticodon `cat`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Timing per step for `ours` read from batch_mitoz logs if present, else total only.
- [ ] **Step 4:** Tests PASS; ruff, mypy clean. Smoke run on 3 dev records (one Chordata, one Cnidaria, one linear if any) → 9 `status.json` files, Cnidaria `mitoz` = `unsupported`.
- [ ] **Step 5:** Commit `benchmark: runner with lift-over and resume`.

### Task 5: Evaluator

**Files:**
- Create: `benchmark/mito_bench_eval.py`
- Test: `tests/test_mito_bench_eval.py`
- Output: `projects/mito_benchmark/eval/<split>/{features.tsv, errors.tsv, summary.tsv, timing.tsv}`

**Interfaces:**
- Consumes: Task 3 TSV, Task 4 `final.gbf` + `status.json`; import `ALIAS`, `PRODUCT`, `PCG` from `benchmark/eval_features.py`; tRNA naming logic consistent with `benchmark/eval_trna.py`.
- `norm_features(rec: SeqRecord) -> list[Feat]` where `Feat = (kind: "PCG"|"rRNA"|"tRNA"|"intron", name: str, strand: int, start: int, end: int, anticodon: str)`.
- `match(truth: list[Feat], pred: list[Feat]) -> list[dict]` rows with `class` ∈ `exact | le3 | gt3 | missed | fp | strand_error | name_error | name_unverifiable`.
- `pcg_checks(rec: SeqRecord, code: int) -> list[dict]` → `internal_stop`, `bad_start`, `bad_stop` (incomplete T/TA stop accepted when followed by a feature).
- `obvious_errors(rows, pcg_rows, status) -> list[dict]` per spec §5.2 (missing PCG/rRNA, frameshift/internal stop, strand error, duplicate gene, name error, boundary >30 nt, table2asn ERROR/REJECT, failed/timeout).
- `summary.tsv` grouped by tool × kind × {all, phylum, evidence_tier, annotation_method, structure_stress, post_cutoff}; post_cutoff = `refseq_created` after refseq89m release date (date recorded in `knowledge/tools/mitos2.md`).
- CLI: `python3 benchmark/mito_bench_eval.py --set ... --split dev --root projects/mito_benchmark [--table2asn]` (table2asn via existing `ncbi_validate.py`).

- [ ] **Step 1: Failing tests:**
  - `test_exact_and_le3` — pred cox1 identical → exact; shifted 2 nt → le3; 10 nt → gt3.
  - `test_strand_error` — same span, opposite strand → strand_error (not missed+fp).
  - `test_trnL_name_error` — NCBI trnL anticodon `tag`, pred trnL anticodon `taa` → name_error.
  - `test_no_anticodon_unverifiable` — NCBI trnS without anticodon, pred trnS(tga) → name_unverifiable, counted as found.
  - `test_internal_stop` — CDS with in-frame TAA under code 5 → internal_stop.
  - `test_incomplete_stop_ok` — cox3 ending in `T` followed by tRNA → no bad_stop.
  - `test_unsupported_excluded` — status unsupported → no accuracy rows, counted in coverage.
  - `test_failed_is_obvious_error` — status failed → obvious error row `failed`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Tests PASS; ruff, mypy clean; run on the 3-record smoke output → non-empty TSVs.
- [ ] **Step 5:** Commit `benchmark: evaluator (accuracy, obvious errors, timing)`.

### Task 6: Install-difficulty measurement

**Files:**
- Create: `benchmark/install_bench.sh`, `benchmark/sets/install_2026-10.tsv`

**Interfaces:** TSV columns: `tool, platform, method, steps, manual_downloads, conda_envs, disk_gb, minutes, result, notes`.

- [ ] **Step 1:** Script runs, per tool (ours via `install.sh`; MitoZ; MITOS2; MitoFinder), a fresh `mambaorg/micromamba` container install following each tool's official instructions (from Task 2 knowledge files), timing with `date +%s`, size with `du -sh`; append one TSV row each.
- [ ] **Step 2:** macOS rows: `CONDA_OVERRIDE_OSX=13 mamba create --dry-run` for `osx-64` and `osx-arm64`; result `solvable`/`unsolvable: <pkg>`, method `dry-run (未实测)`.
- [ ] **Step 3:** Run; check every tool × {linux, osx-64, osx-arm64} row present.
- [ ] **Step 4:** Commit `benchmark: install difficulty table`.

### Task 7: First dev run + error report

**Files:**
- Modify: `benchmark/README.md` (Phase-1 section), `knowledge/benchmark_findings.md`, `README.md` (link), `/mnt/n/yzz-分类工作流/modules/genbank/REQUIREMENTS.md` (new row #39 for this benchmark, from user 2026-10-20)

- [ ] **Step 1:** Run Task 4 CLI on the full dev split in background (`--jobs 4 --threads 4`); resume until all rows have `status.json`.
- [ ] **Step 2:** Run Task 5 on dev (with `--table2asn`).
- [ ] **Step 3:** Cluster `errors.tsv` by (tool, error class, gene, phylum); for the top clusters of `ours`, write cause hypotheses into `benchmark_findings.md` with evidence or `未确证`.
- [ ] **Step 4:** Write the Phase-1 report (accuracy by kind / phylum / tier, coverage, timing, install table) into `benchmark/README.md`.
- [ ] **Step 5:** Full regression: `python3 -m pytest -q tests/` and `check_mitoz.py` PASS; `check_knowledge.py knowledge/` exit 0.
- [ ] **Step 6:** Commit `benchmark: phase-1 dev results`; present to user: top error clusters + proposed fixes (= input for the Phase-2 optimisation plan).
