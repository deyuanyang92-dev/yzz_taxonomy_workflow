"""04 table: 按 Run 合并 RunInfo + annotate + 阶元, 派生数据类型, 输出总表 TSV 与 Excel.

用法: python3 yzz.py sra 04 <Taxon> [--rules rules.json]
输入: runinfo.tsv (必需), annotate.tsv, taxonomy.tsv, manifest.json (可缺)
输出: table.tsv, samples.tsv, species_summary.tsv; 04_处理数据/sra/<Taxon>_SRA_<date>.xlsx
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import pandas as pd  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from classify import (classify_runs, load_rules, ordered_categories,  # noqa: E402
                      summarize_samples, summarize_species)
from common import TODAY, data_dir, read_tsv, report_dir, summary, write_tsv  # noqa: E402
from excel import YELLOW, write_workbook  # noqa: E402
from parse import norm_taxid  # noqa: E402

CAT_SHEETS = ["shallow_WGS", "deep_WGS", "long_read_WGS", "RNA-Seq", "Hi-C"]
QC_CATS = ["WGS_PCR_suspect", "WGS_metagenomic", "low_data_WGS"]


def lines_of(path):
    return path.read_text(encoding="utf-8").split() if path.exists() else []


def merge(runinfo, annotate, taxonomy):
    t = runinfo.copy()
    if len(annotate):
        t = t.merge(annotate, on="Run", how="left", suffixes=("", "_annotate"))
    if len(taxonomy):
        t["_taxid"] = [norm_taxid(x) for x in t.get("TaxID", [""] * len(t))]
        tax = taxonomy.rename(columns={"TaxID": "_taxid"})
        t = t.merge(tax, on="_taxid", how="left", suffixes=("", "_taxonomy")).drop(columns="_taxid")
    assert len(t) == len(runinfo), "merge changed row count"
    return t.fillna("")


def qc_table(t, d, manifest):
    rows = []
    for _, r in t[t.get("category_derived", pd.Series(dtype=str)).isin(QC_CATS)].iterrows():
        rows.append({"issue": r["category_derived"], "Run": r["Run"], "detail": r["category_rule_derived"]})
    if "BioProject" in t:
        rows += [{"issue": "empty_BioProject", "Run": x, "detail": ""} for x in t.loc[t["BioProject"] == "", "Run"]]
    rows += [{"issue": "run_not_found", "Run": x, "detail": "not in NCBI SRA"} for x in lines_of(d / "runs_not_found.txt")]
    rows += [{"issue": "annotate_missing", "Run": x, "detail": "no SRA XML"} for x in lines_of(d / "annotate_missing.txt")]
    rows += [{"issue": "taxonomy_missing", "Run": "", "detail": f"TaxID {x}"} for x in lines_of(d / "taxonomy_missing.txt")]
    rows += [{"issue": "manifest", "Run": "", "detail": x} for x in manifest.get("problems", [])]
    return pd.DataFrame(rows, columns=["issue", "Run", "detail"])


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    p.add_argument("--rules")
    a, _ = p.parse_known_args(argv)
    d = data_dir(a.taxon, "sra")
    runinfo = read_tsv(d / "runinfo.tsv")
    annotate = read_tsv(d / "annotate.tsv", required=False)
    taxonomy = read_tsv(d / "taxonomy.tsv", required=False)
    mf = d / "manifest.json"
    manifest = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    rules = load_rules(a.rules)

    t = classify_runs(merge(runinfo, annotate, taxonomy), rules) if len(runinfo) else \
        runinfo.assign(category_derived=pd.Series(dtype=str), category_rule_derived=pd.Series(dtype=str))
    samples = summarize_samples(t) if len(t) else summarize_samples(pd.DataFrame())
    species = summarize_species(samples, taxonomy)
    write_tsv(t, d / "table.tsv")
    write_tsv(samples, d / "samples.tsv")
    write_tsv(species, d / "species_summary.tsv")

    sheets = {"Summary": species, "Samples": samples}
    for c in CAT_SHEETS:
        sheets[c] = samples[samples.category_derived == c]
    sheets["Other"] = samples[~samples.category_derived.isin(CAT_SHEETS)]
    sheets["Runs"] = t
    sheets["QC"] = qc_table(t, d, manifest)
    q = [("taxon", a.taxon)] + [(k, manifest.get(k, "")) for k in ("mode", "taxid", "term", "date", "esearch_count",
                                                                     "experiments")]
    q += [("runs", len(t)), ("rules", json.dumps(rules, ensure_ascii=False)), ("table_date", TODAY)]
    sheets["Query"] = pd.DataFrame(q, columns=["key", "value"]).astype(str)
    for name, df in sheets.items():                     # keep empty sheets present with headers
        if not len(df.columns):
            sheets[name] = pd.DataFrame(columns=["(empty)"])
    path = write_workbook(report_dir(a.taxon, "sra") / f"{a.taxon}_SRA_{TODAY}.xlsx", sheets)
    wb = load_workbook(path)
    for ws in wb.worksheets:
        for c in ws[1]:
            if str(c.value or "").endswith("_derived"):
                c.fill = YELLOW
    wb.save(path)

    counts = t["category_derived"].value_counts() if len(t) else pd.Series(dtype=int)
    top = ", ".join(f"{c} {counts[c]}" for c in ordered_categories(counts.index)[:6])
    summary("04_table", [f"{len(t)} run / {len(samples)} 样本×类型 / {len(species)} 个 TaxID",
                         f"run 数: {top or '无'}", f"QC {len(sheets['QC'])} 条", f"-> {path}"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
