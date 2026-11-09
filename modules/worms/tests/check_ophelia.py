"""第三金标准: Ophelia (粘海蛹新种稿件 ZooKeys 218447 核对, 2026-10-31 用户与原始文献逐条核实)

每条对应 REQUIREMENTS 第 8 节一个需求; 先跑 `python3 yzz.py worms all Ophelia --refresh`.
  R1/R2 O. peresi 命名人年份随 WoRMS 更新为 1966 (缓存过期会留 1965), 且 AUTH_OD_YEAR 不误报 "1988 [1987]"
  R3    O. profunda 'off New England' 来自 Hartman 1965 题目 (原文 Bermuda) -> TL_FROM_TITLE
  R4    O. translucens 模式产地取自类群外原始组合 Pseudophelia translucens (Zlarin)
  R6    O. borealis / rathkei / celtica 模式产地只有 'Atlantic Ocean' -> TL_OCEAN_ONLY
  不报  O. elongata 有比题目更具体的地名 (Burwood Beach) -> 不得报 TL_FROM_TITLE
用法: python3 modules/worms/tests/check_ophelia.py   (全部 PASS 退出码 0)
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "projects/Ophelia/02_原始数据/worms"
rd = lambda f: pd.read_csv(D / f, sep="\t", dtype=str, keep_default_na=False)
n, t, q = rd("names.tsv"), rd("types.tsv"), rd("qc.tsv")
name = lambda sp: n[n.scientific_name == sp].iloc[0]
tl = lambda sp: t[t.aphia_id == name(sp).aphia_id].iloc[0].type_locality_text
flags = lambda sp: set(q[q.scientific_name == sp].check)

checks = [
    ("R1 peresi authority 1966", name("Ophelia peresi").authority.endswith("1966")),
    ("R2 no AUTH_OD_YEAR for peresi", "AUTH_OD_YEAR" not in flags("Ophelia peresi")),
    ("R2 no false AUTH_OD_YEAR for '1988 [1987]'", "AUTH_OD_YEAR" not in flags("Ophelia amoureuxi")),
    ("R3 profunda TL_FROM_TITLE", "TL_FROM_TITLE" in flags("Ophelia profunda")),
    ("R3 elongata not TL_FROM_TITLE", "TL_FROM_TITLE" not in flags("Ophelia elongata")),
    ("R4 translucens TL Zlarin via original combination", "Zlarin" in tl("Ophelia translucens")),
    *[(f"R6 {sp} TL_OCEAN_ONLY", "TL_OCEAN_ONLY" in flags(f"Ophelia {sp}")) for sp in ("borealis", "rathkei", "celtica")],
]
for label, ok in checks:
    print(("PASS " if ok else "FAIL ") + label)
sys.exit(0 if all(ok for _, ok in checks) else 1)
