"""回归检查: 记述原文抽取 (account_text.py). 用岩虫项目的两例 (2026-11-08 用户截图指出的问题).
  python3 modules/compilation/tests/check_account_text.py   -> 全 PASS 才能交付
"""
import importlib.util
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PROJ = Path("/mnt/p/岩虫属系统修订")
sp = importlib.util.spec_from_file_location("acc", HERE / "account_text.py")
A = importlib.util.module_from_spec(sp)
sp.loader.exec_module(A)
A.GENERA.update({"Marphysa", "Eunice", "Paucibranchia"})
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS" if cond else "FAIL"), name)


for x, want in [("The larger", False), ("The inner laterals", False), ("Material examined", False),
                ("Marphysa sinensis, sp. n.", True), ("Lysidice collaris Grube.", True), ("Eunice gracilis (Crossland).", True),
                ("Marphysa sinensis Monro, 1934", True)]:
    check(f"is_title({x!r}) == {want}", A.is_title(x) == want)

if (PROJ / "08_知识库/Marphysa_KB.sqlite").exists():
    con = sqlite3.connect(PROJ / "08_知识库/Marphysa_KB.sqlite")
    cases = [("R132_Liu_2017__LiuHutchingsSun2017_3NspMarphysaChina-Smaller.pdf", 13, 20, 227),
             ("X_Monro_1934_P.sinensis原始描述_WoRMS未挂__Monro, 1934-Polychaetes from the coast of China.pdf", 17, 19, 350)]
    for f, a, b, off in cases:
        kb = {p: (t, s) for p, t, s in con.execute("select page_no,text,source from pages where file=? and page_no between ? and ?", (f, a, b))}
        H = A.running_heads([t for (t,) in con.execute("select text from pages where file=?", (f,))])
        t, note = A.account(str(PROJ / "01_文献/01_描述文献" / f), a, b, "sinensis", off, kb, H)
        tag = f[:12]
        check(f"{tag}: starts at species heading", t.splitlines()[1].startswith("Marphysa sinensis"))
        check(f"{tag}: no running head / copyright", "Magnolia Press" not in t and "Downloaded by" not in t)
        check(f"{tag}: no comparison-table rows", "Pectinate chaetae - no. teeth" not in t and "Data source" not in t)
        check(f"{tag}: no empty page markers", not any(x.startswith("[p. ") and y.startswith("[p. ") for x, y in zip(t.splitlines(), t.splitlines()[1:])))
        check(f"{tag}: stops before next species", "Diopatra dentata" not in t and "Lysidice collaris" not in t)
    # 2026-11-08 抽查: Kinberg 1865 缩写属名标题 "N. corallina n."; Willey 1905 每行一个块
    for f, a, b, ep, off, first, absent in [
            ("R094_Kinberg_1865_BHL.pdf", 6, 7, "corallina", 558, "corallina", "gallapagensis"),
            ("R094_Kinberg_1865_BHL.pdf", 6, 7, "corallina", 558, "corallina", "nausicaa"),
            ("R104_Willey_1905__Willey, 1905, 211-324.pdf", 353, 353, "orientalis", -70, "orientalis", None)]:
        kb = {p: (t, s) for p, t, s in con.execute("select page_no,text,source from pages where file=? and page_no between ? and ?", (f, a, b))}
        if not kb:
            continue
        H = A.running_heads([t for (t,) in con.execute("select text from pages where file=?", (f,))])
        t, note = A.account(str(PROJ / "01_文献/01_描述文献" / f), a, b, ep, off, kb, H)
        body = [x for x in t.splitlines() if x and not x.startswith("[p. ")]
        check(f"{f[:12]}: first line has {first}", first in body[0].lower())
        if absent:
            check(f"{f[:12]}: previous species ({absent}) excluded", absent not in t.lower())
        else:
            paras = t.split("\n\n")
            check(f"{f[:12]}: lines joined into paragraphs (<= 1 blank per 3 lines)", len(paras) <= max(3, len(body) // 3))
sys.exit(0 if ok else 1)
