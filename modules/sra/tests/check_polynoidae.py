"""sra 模块联网回归检查 (Polynoidae). 先跑: python3 yzz.py sra all Polynoidae
用法: python3 modules/sra/tests/check_polynoidae.py   全部 PASS 才算通过.
"""
import json
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "projects" / "Polynoidae" / "02_原始数据" / "sra"
R = ROOT / "projects" / "Polynoidae" / "04_处理数据" / "sra"
fails = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


m = json.loads((D / "manifest.json").read_text(encoding="utf-8"))
check("manifest ok (Experiment = esearch Count)", m["ok"] and m["experiments"] == m["esearch_count"])
check("experiments >= 495 (2026-10-27)", m["experiments"] >= 495)
check("runs >= 525", m["runs"] >= 525)
check("empty BioProject >= 51 (DRR 2026)", m["empty_bioproject"] >= 51)
t = pd.read_csv(D / "table.tsv", sep="\t", dtype=str, keep_default_na=False)
check("table rows == runs", len(t) == m["runs"])
check("every run has category_derived", (t["category_derived"] != "").all())
check("annotate merged (experiment_title filled >= 95%)", (t["experiment_title"] != "").mean() >= 0.95)
check("lineage merged (family filled for all)", (t["family"] == "Polynoidae").all())
skim = t[t["Run"] == "SRR37048088"]
check("SRR37048088 genome skimming -> shallow_WGS", len(skim) == 1 and skim.iloc[0]["category_derived"] == "shallow_WGS")
xl = sorted(R.glob("Polynoidae_SRA_*.xlsx"))[-1]
check("Excel has 11 sheets", len(load_workbook(xl, read_only=True).sheetnames) == 11)
check("run_list_default.txt non-empty", (D / "run_list_default.txt").read_text().strip() != "")
print(f"\n{len(fails)} FAIL" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
