"""literature 模块回归检查: python3 modules/literature/tests/check_literature.py  (全部 PASS 才算完成).

每条检查对应一次用户纠正或 QC 发现.
"""
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIT = Path("/root/yzz-literature")
CN = ROOT / "cache" / "cn_names.sqlite"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


# 11_cn_names: 用户 2026-10-21 "Claude 翻译拉丁名为中文存在重大问题"
cn = sqlite3.connect(CN)
for latin, want in [("Perinereis aibuhitensis", "双齿围沙蚕"), ("Travisia", "臭海蛹属"), ("Ophelia limacina", "粘海蛹"),
                    ("Levinsenia gracilis japonica", "日本赖氏异毛虫"), ("Opheliidae", "海蛹科")]:
    got = [r[0] for r in cn.execute("SELECT cn FROM names WHERE latin=?", (latin,))]
    check(f"中文名 {latin} = {want}", want in got, f"得到 {got}")
check("名录无 Travisia forbesii (不应编造中文名)",
      not cn.execute("SELECT 1 FROM names WHERE latin='Travisia forbesii'").fetchone())
check("异名可反查 (Namastoma livida -> 舌状蜈蚣藻)",
      bool(cn.execute("SELECT 1 FROM names WHERE cn='舌状蜈蚣藻' AND note LIKE '%Namastoma livida%'").fetchone()))
n_long = cn.execute("SELECT count(*) FROM names WHERE length(distribution) > 2000").fetchone()[0]
check("分布字段无失控续行 (儒艮吞并书末附录)", n_long == 0, f"{n_long} 条 > 2000 字")

# 07_fts
db = sqlite3.connect(f"file:{LIT / 'polychaeta.db'}?mode=ro", uri=True)
n = db.execute("SELECT count(DISTINCT p.doc_id) FROM pages_fts f JOIN pages p ON p.rowid=f.rowid"
               " WHERE pages_fts MATCH '\"Travisia forbesii\"'").fetchone()[0]
check("FTS: \"Travisia forbesii\" >= 100 篇", n >= 100, f"{n} 篇")
n = db.execute("SELECT count(*) FROM pages_cjk WHERE pages_cjk MATCH '异毛虫'").fetchone()[0]
check("FTS 中文 trigram: 异毛虫", n >= 1, f"{n} 页")

# 03/09: 只看封面漏判 (2026-10-21)
cand = {r["path"]: r["decision"] for r in csv.DictReader(open(LIT / "discovery" / "candidates.tsv", encoding="utf-8"),
                                                          delimiter="\t")}
for key in ["中国动物志_无脊椎动物_第三十三卷_环节动物门_多毛纲_（二）_沙蚕目.pdf", "Imajima 2009",
            "臭海蛹文献/臭海蛹科/Travisia forbesii Johnston, 1840.pdf"]:
    ds = [d for p, d in cand.items() if key in p and d != "duplicate"]
    check(f"候选 include: {key}", "include" in ds, f"{ds}")

# 10_dossier 试点: Jirkov 2001 对金标准 (Travisia_分类性状比较表.xlsx)
f = LIT / "species" / "Travisia_forbesii" / "out" / "1093.chars.tsv"
rows = list(csv.DictReader(open(f, encoding="utf-8"), delimiter="\t")) if f.exists() else []
val = {r["character"]: (r["value"] or "") for r in rows}
for ch, want in [("Toc", "23"), ("br_first", "3"), ("tl_depth", "3000"), ("colour", "pale pink")]:
    check(f"T. forbesii Jirkov2001 {ch} ~ {want}", want in val.get(ch, ""), val.get(ch, "缺"))

f = LIT / "species" / "Travisia_forbesii" / "out" / "5193.chars.tsv"
rows = list(csv.DictReader(open(f, encoding="utf-8"), delimiter="\t")) if f.exists() else []
val = {}
for r in rows:
    val.setdefault(r["character"], []).append(r["value"] or "")
for ch, want in [("pyg_lobes", "6"), ("size_L", "25.4"), ("colour", "olive-green"), ("chaetae", "smooth"),
                 ("mouth", "1"), ("prost", "conical")]:
    got = " | ".join(val.get(ch, []))
    check(f"T. forbesii Johnston1840 (L3) {ch} ~ {want}", want in got, got[:60] or "缺")

# 12_library: 原文件不动, 文库文件与原文件大小一致
plan = LIT / "library_plan.tsv"
import pandas as pd  # noqa: E402

if plan.exists():
    lib = pd.read_csv(plan, sep="\t")
    miss = [p for p in lib.orig_path if not Path(p).exists()]
    check("文库: 原文件全部仍在", not miss, f"{len(miss)} 个缺失")
    bad = [r.new_path for r in lib.itertuples() if not Path(r.new_path).exists()
           or Path(r.new_path).stat().st_size != r.size]
    check("文库: 副本存在且大小一致", not bad, f"{len(bad)} 个不符")

# 13_zh_reocr: 用户 2026-10-21 "沈寿彭和吴宝玲 1993 ... 你没有放进去" -> 中文扫描书被按英文 OCR, 中文搜不到
for kw, fname in [("背褶沙蚕", "沈 寿 彭 和吴宝玲 1993"), ("溪沙蚕", "中国动物志_无脊椎动物_第三十三卷_环节动物门_多毛纲_（二）_沙蚕目")]:
    n = db.execute("SELECT count(*) FROM pages_cjk k JOIN pages p ON p.rowid=k.page_rowid JOIN docs d USING (doc_id)"
                   " WHERE pages_cjk MATCH ? AND coalesce(d.orig_path, d.relpath) LIKE ?",
                   (f'"{kw}"', f"%{fname}%")).fetchone()[0]
    check(f"中文可检索: {kw} in {fname[:20]}", n >= 1, f"{n} 页")

# 12_library: 《中国海洋生物名录》(全门类) 不得归某一科 (曾被归龙介虫科)
if plan.exists():
    lib = pd.read_csv(plan, sep="\t")
    f = lib[lib.orig_path.str.contains("中国海洋生物名录", regex=False)].folder.tolist()
    check("文库: 中国海洋生物名录 归 _综合", f and all(x == "_综合" for x in f), f"{f}")

# 14_search: 用户 2026-10-21 纠正 -> 只引用中国序列/文献的不算中国海文献
sx = LIT / "search" / "溪沙蚕属" / "文献.xlsx"
if sx.exists():
    xl = pd.ExcelFile(sx)
    if "区域文献_A" in xl.sheet_names:
        a = xl.parse("区域文献_A")
        for k in ["Villalobos", "Wilson et al., 2023", "Alves et al., 2020", "Alves et al., 2023", "Alves et al., 2024"]:
            check(f"溪沙蚕属 中国海 A 不含 {k}", not a["文件"].str.contains(k, regex=False).any())
        check("溪沙蚕属 中国海 A 含 Wu et al. 1981 中国沙蚕科名录",
              a["文件"].str.contains("Wu et al., 1981", regex=False).any())
    else:
        check("溪沙蚕属 区域判定已合并", False, "无 区域文献_A 表")

# 用户 2026-10-22: "珠江多毛类不是就是沈那篇吗" / create_pdf.pdf = 赫列勃维奇 1963 -> 须在库且可检索
shen = db.execute("SELECT doc_id FROM docs WHERE coalesce(orig_path, relpath) LIKE '%珠江广州河段的淡水环节动物多毛类%'"
                  " OR coalesce(orig_path, relpath) LIKE '%珠江多毛类.pdf'").fetchall()
check("沈寿彭 & 戚桑 1982 已入库 (03 只认西文术语曾漏判)", len(shen) >= 1, f"{len(shen)} 个文件")
if shen:
    ids = ",".join(str(r[0]) for r in shen)
    n = db.execute(f"SELECT count(*) FROM pages WHERE doc_id IN ({ids}) AND text LIKE '%Namalycastis%'").fetchone()[0]
    check("沈寿彭 & 戚桑 1982 文字含 Namalycastis (知网文字层缺拉丁, latin 模式补 OCR)", n >= 1, f"{n} 页")
cb = db.execute("SELECT b.title, b.authors FROM biblio b JOIN docs d USING (doc_id)"
                " WHERE coalesce(d.orig_path, d.relpath) LIKE '%新建文件夹 (3)/create_pdf.pdf'").fetchall() \
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='biblio'").fetchone() else []
check("映射表: create_pdf.pdf -> 海南岛潮间带多毛类沙蚕科的研究 (赫列勃维奇 1963)",
      bool(cb) and "海南" in (cb[0][0] or ""), f"{cb[:1]}")

print(f"\n{sum(results)}/{len(results)} PASS")
sys.exit(0 if all(results) else 1)
