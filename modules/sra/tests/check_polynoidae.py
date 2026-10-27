"""sra 模块联网回归检查 (Polynoidae). 先跑: python3 yzz.py sra all Polynoidae
用法: python3 modules/sra/tests/check_polynoidae.py   全部 PASS 才算通过.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "modules" / "sra"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tsv import read_tsv  # noqa: E402
from xlsx_read import Book  # noqa: E402

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
_, t = read_tsv(D / "table.tsv")
check("table rows == runs", len(t) == m["runs"])
check("every run has category_derived", all(r["category_derived"] for r in t))
check("annotate merged (experiment_title filled >= 95%)", sum(bool(r["experiment_title"]) for r in t) >= 0.95 * len(t))
check("lineage merged (family filled for all)", all(r["family"] == "Polynoidae" for r in t))
skim = [r for r in t if r["Run"] == "SRR37048088"]
check("SRR37048088 genome skimming -> shallow_WGS", len(skim) == 1 and skim[0]["category_derived"] == "shallow_WGS")
xl = sorted(R.glob("Polynoidae_SRA_*.xlsx"))[-1]
check("Excel has 11 sheets", len(Book(xl).sheetnames) == 11)
check("run_list_default.txt non-empty", (D / "run_list_default.txt").read_text().strip() != "")
print(f"\n{len(fails)} FAIL" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
