"""checklist 模块回归检查 (Polychaeta_nonmarine 项目). 改任何 checklist 脚本后运行, 全部 PASS 才算完成.

  python3 modules/habitat/tests/check_nonmarine.py
用户每指出一个错误, 在这里加一条检查.
"""
import importlib.util, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "projects" / "Polychaeta_nonmarine" / "02_原始数据" / "habitat"
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "modules" / "habitat"))
import pandas as pd  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def tsv(name):
    return pd.read_csv(D / name, sep="\t", dtype=str, keep_default_na=False)


# --- 01 seed parser (Glasby et al. 2009) ---
seed = tsv("seed.tsv")
check("seed: 197 entries (abstract of Glasby et al. 2009)", len(seed) == 197, len(seed))
check("seed: 26 family groups incl. Family Unknown", seed["glasby_family"].nunique() == 26, seed["glasby_family"].nunique())
fam = seed["glasby_family"].value_counts()
check("seed: Nereididae 61 / Aeolosomatidae 27 / Sabellidae 24 (abstract)",
      (fam.get("Nereididae"), fam.get("Aeolosomatidae"), fam.get("Sabellidae")) == (61, 27, 24), fam.head(3).to_dict())
check("seed: 'HIstriobdellidae' typo header parsed -> Histriobdellidae 11", fam.get("Histriobdellidae") == 11)
check("seed: every entry has Ecology/Distribution/Habitat",
      ((seed["ecology"] != "") & (seed["distribution"] != "") & (seed["habitat"] != "")).all())
row = seed[seed["glasby_name"] == "Nereis oligohalina (Rioja)"]
check("seed: entry split by page break between name and Ecology (Nereis oligohalina)",
      len(row) == 1 and row.iloc[0]["ecology"] == "FT")
row = seed[seed["glasby_name"].str.startswith("Namalycastis abiuma")]
check("seed: species group flag (N. abiuma)", len(row) == 1 and row.iloc[0]["species_group"] == "Y")

# --- wormsmatch.query_name ---
spec = importlib.util.spec_from_file_location("wm", ROOT / "modules" / "habitat" / "wormsmatch.py")
wm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wm)
check("query_name: parenthesised author is not a subgenus",
      wm.query_name("Namanereis littoralis (Grube)") == ("Namanereis littoralis", False))
check("query_name: subgenus kept", wm.query_name("Hediste (Hediste) diversicolor (Müller)")[0] == "Hediste (Hediste) diversicolor")
check("query_name: informal sp. -> genus", wm.query_name("Capitella sp. ‘Bayly’") == ("Capitella", True))

# --- 02 WoRMS match ---
sw = tsv("seed_worms.tsv")
errs = sw[sw["worms_note"].str.startswith("lookup error")]
check("worms: no lookup errors (cache contention / empty cached body)", len(errs) == 0, len(errs))
for n in ("Heteromastus filiformis (Claparède)", "Namalycastis intermedia Glasby"):
    r = sw[sw["glasby_name"] == n]
    check(f"worms: {n} matched (was empty cached response)", len(r) == 1 and r.iloc[0]["accepted_aphia_id"] != "")

# --- 07 build ---
cl = tsv("checklist.tsv")
check("build: first 5 columns after 序号 fixed", list(cl.columns[1:6]) == ["物种名", "科", "目", "生境类型", "参考文献"],
      list(cl.columns[1:6]))
check("build: habitat values valid", cl["生境类型"].isin(["纯淡水", "半盐水", "均可", "陆生"]).all(),
      cl["生境类型"].unique())
h = dict(zip(cl["物种名"].str.split().str[:2].str.join(" "), cl["生境类型"]))
check("build: N. hawaiiensis FW -> 纯淡水", h.get("Namalycastis hawaiiensis") == "纯淡水")
check("build: N. abiuma FT -> 均可", h.get("Namalycastis abiuma") == "均可")
check("build: Hrabeiella T -> 陆生 and every Hrabeiella row (seed and added) flagged not Polychaeta in WoRMS",
      h.get("Hrabeiella periglandulata") == "陆生"
      and cl[cl["物种名"].str.startswith("Hrabeiella")]["备注"].str.contains("不归入 Polychaeta").all())
check("build: added Aeolosomatidae rows also carry the WoRMS placement flag",
      cl[(cl["科"] == "Aeolosomatidae")]["备注"].str.contains("不归入 Polychaeta").all())
check("build: no species silently lost when two Glasby names share one WoRMS valid name",
      len(cl) + cl["Glasby名称"].str.count(r" \| ").sum() >= 197)
check("build: every row has a reference", (cl["参考文献"] != "").all())

import re  # noqa: E402
# --- 05 adjudication ---
adj = pd.read_csv(D / "extract" / "adjudicated.tsv", sep="\t", dtype=str, keep_default_na=False)
excluded = set(adj.loc[adj["habitat_cn"] == "排除", "species"])
add = tsv("additions.tsv")
seed_names = {wm.query_name(n)[0] for n in seed["glasby_name"]} | set(sw["accepted_name"])
only_excluded = excluded - set(add.loc[add["habitat_cn"] != "排除", "species"]) - seed_names   # seed species stay
# species name followed directly by its authority (capital letter or parenthesis), not by a subspecies epithet
leaked = [s for s in only_excluded if cl["物种名"].str.match(re.escape(s) + r" [A-Z(]").any()]
check("adjudication: species excluded in all their records are absent from the checklist", not leaked, leaked)
check("adjudication: aquarium salinity does not turn N. hawaiiensis into 均可 (Abe et al. 2017)",
      h.get("Namalycastis hawaiiensis") == "纯淡水")
check("build: genus-level records (spp. / bare genus) are not species rows",
      not cl["物种名"].str.match(r"^\S+ spp\.?$").any() and not cl["物种名"].str.match(r"^[A-Z][a-z]+$").any())

# --- 04 prefilter recall (validated 2026-10-11: taxon AND habitat lost 10 productive works) ---
import re  # noqa: E402
spec2 = importlib.util.spec_from_file_location("sm", ROOT / "modules" / "habitat" / "04_screen_merge.py")
sm = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(sm)
works = tsv("works.tsv")
judged = works[works["decision"].isin(["yes", "maybe", "no"]) & ~works["reason"].str.startswith("prefilter")]
gn = set(seed["glasby_name"].str.split().str[0]) | set(sw["genus"]) | set(add["species"].str.split().str[0])
gn = {n for n in gn if n and n[0].isupper() and len(n) > 3}
rx = re.compile(sm.TAX + "|" + "|".join(sorted(map(re.escape, gn), key=len, reverse=True)), re.I)
kept = sm.keep_mask(judged["title"] + " " + judged["abstract"], rx)
prod = set(add.loc[add["habitat_cn"] != "排除", "work_id"])
check("prefilter: no screened 'yes' work would be auto-rejected", not (~kept & (judged["decision"] == "yes")).any())
check("prefilter: no productive work (yielded records) would be auto-rejected", not (~kept & judged["id"].isin(prod)).any())

check("build: every species row starts with a scientific name (no descriptive text from abstracts)",
      cl["物种名"].str.match(r"^[A-Z][a-z]+(?: \([A-Z][a-z]+\))? (?:[a-z][a-z\-]+|sp\.|cf\.|aff\.|nr\.|indet\.|spp\.)").all(),
      cl.loc[~cl["物种名"].str.match(r"^[A-Z][a-z]+(?: \([A-Z][a-z]+\))? (?:[a-z][a-z\-]+|sp\.|cf\.|aff\.|nr\.|indet\.|spp\.)"), "物种名"].tolist()[:5])

fails = [r for r in results if not r[1]]
for name, ok, det in results:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  [{det}]"))
print(f"\n{len(results) - len(fails)}/{len(results)} PASS")
sys.exit(1 if fails else 0)
