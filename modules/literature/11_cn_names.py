"""11 中文学名知识库: 解析刘瑞玉 (2008)《中国海洋生物名录》全书 -> 拉丁名 <-> 中文名 (全门类).

  python3 11_cn_names.py <corpus> build              解析库内名录 -> cache/cn_names.sqlite + outputs/中国海洋生物名录_中文名.xlsx
  python3 11_cn_names.py <corpus> lookup <名称...>   拉丁名或中文名查询 (属/种/科均可; 拉丁名容错: 大小写、亚属括号、-i/-ii)

  用途: 翻译学名时先查此库; 查不到保留拉丁名, 不自行意译 (用户 2026-10-21: Claude 意译学名错误严重).
  名录格式: 门/纲/目 "中文 Order LATIN"; 科 "(18) 蠕鳞虫科 Family Acoetidae Kinberg, 1858";
            属 "340) 赖氏异毛虫属 Genus Levinsenia Mesnil, 1879【异名】"; 种 "1046. 中文 拉丁名 命名人, 年份 分布" (分布可换行)
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

DB = ROOT / "cache" / "cn_names.sqlite"
XLSX = ROOT / "outputs" / "中国海洋生物名录_中文名.xlsx"
SOURCE = "刘瑞玉 (主编) 2008. 中国海洋生物名录. 科学出版社"
BOOK = "%Checklist_of_marine_biota_of_China_Seas%"

RANKS = ["Phylum", "Subphylum", "Superclass", "Class", "Subclass", "Infraclass", "Superorder", "Order", "Suborder",
         "Infraorder", "Superfamily", "Family", "Subfamily", "Tribe", "Genus", "Subgenus"]
HEAD = re.compile(r"^(?:\(?\d+\)\s*)?(\S+?)\s+(" + "|".join(RANKS) + r")\s+([A-Z][A-Za-z]+(?:\s+\([A-Za-z]+\))?)\s*(.*)$")
SP = re.compile(r"^(\d+)\.\s*(\S+)\s+([A-Z][a-z]+(?:\s+\([A-Z][a-z]+\))?(?:\s+[a-z][a-z-]+){1,2})\s*(.*)$")
AUTH = re.compile(r"^(.*?\b1[789]\d\d\)?|.*?\b20[0-2]\d\)?)\s*[，,;；]?\s*(.*)$")
SCHEMA = """
DROP TABLE IF EXISTS names;
CREATE TABLE names (latin TEXT, cn TEXT, rank TEXT, author TEXT, genus TEXT, family TEXT, family_cn TEXT,
                    "order" TEXT, class TEXT, phylum TEXT, phylum_cn TEXT, distribution TEXT, page INTEGER,
                    note TEXT, source TEXT);
CREATE INDEX names_latin ON names(latin COLLATE NOCASE);
CREATE INDEX names_cn ON names(cn);
"""
LEVEL = {"Phylum": "phylum", "Class": "class", "Order": "order", "Family": "family", "Genus": "genus"}


def split_author(rest):
    """'Imajima, 1973) 南海(SCS)...' -> ('(Imajima, 1973)', '南海...'); 无年份 -> ('', rest)."""
    m = AUTH.match(rest)
    return (m.group(1).strip(), m.group(2).strip()) if m else ("", rest.strip())


def parse(pages):
    ctx = {k: "" for k in ("phylum", "phylum_cn", "class", "order", "family", "family_cn", "genus")}
    rows, last = [], None
    for page_no, text in pages:
        for line in text.splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if not line or re.fullmatch(r"·?\s*\d+\s*·?", line):
                continue
            h = HEAD.match(line)
            if h:
                cn, rank, latin, rest = h.groups()
                syn = re.findall(r"【(.*?)】", rest)
                author, _ = split_author(re.sub(r"【.*?】", "", rest))
                latin = latin.title() if latin.isupper() else latin
                if rank in LEVEL:
                    ctx[LEVEL[rank]] = latin
                    if rank == "Phylum":
                        ctx.update(phylum_cn=cn, **{k: "" for k in ("class", "order", "family", "family_cn", "genus")})
                    elif rank == "Class":
                        ctx.update(order="", family="", family_cn="", genus="")
                    elif rank == "Order":
                        ctx.update(family="", family_cn="", genus="")
                    elif rank == "Family":
                        ctx.update(family_cn=cn, genus="")
                last = dict(latin=latin, cn=cn, rank=rank, author=author or rest[:80], distribution="", page=page_no,
                            note=("异名: " + "; ".join(syn)) if syn else "", **ctx)
                rows.append(last)
                continue
            s = SP.match(line)
            if s:
                _, cn, latin, rest = s.groups()
                author, dist = split_author(rest)
                rank = "Subspecies" if len(latin.split()) - ("(" in latin) == 3 else "Species"
                last = dict(latin=latin, cn=cn, rank=rank, author=author, distribution=dist, page=page_no, note="", **ctx)
                rows.append(last)
                continue
            if (last is not None and last["rank"] in ("Species", "Subspecies") and page_no - last["page"] <= 1
                    and len(last["distribution"]) < 1500):  # 分布换行接续; 限当页/次页, 防末种吞并书末附录
                last["distribution"] = (last["distribution"] + " " + line).strip()
    rows = rows[next((i for i, r in enumerate(rows) if r["rank"] == "Phylum"), 0):]  # 丢前言
    for r in rows:
        syn = re.findall(r"【(.*?)】", r["distribution"])
        if syn and r["rank"] in ("Species", "Subspecies"):
            r["note"] = "异名: " + "; ".join(syn)
            r["distribution"] = re.sub(r"【.*?】", "", r["distribution"]).strip()
    return rows


def build(corpus):
    import pandas as pd
    con = litdb.connect(corpus)
    doc = con.execute("SELECT doc_id FROM docs WHERE relpath LIKE ? ORDER BY doc_id LIMIT 1", (BOOK,)).fetchone()
    if not doc:
        raise SystemExit("库内未找到《中国海洋生物名录》(Checklist_of_marine_biota_of_China_Seas)")
    pages = con.execute("SELECT page_no, text FROM pages WHERE doc_id=? ORDER BY page_no", doc).fetchall()
    df = pd.DataFrame(parse(pages)).assign(source=SOURCE)
    out = sqlite3.connect(DB)
    out.executescript(SCHEMA)
    cols = ["latin", "cn", "rank", "author", "genus", "family", "family_cn", "order", "class", "phylum", "phylum_cn",
            "distribution", "page", "note", "source"]
    df[cols].to_sql("names", out, if_exists="append", index=False)
    out.commit()
    out.close()
    XLSX.parent.mkdir(exist_ok=True)
    with pd.ExcelWriter(XLSX) as w:
        df[cols].to_excel(w, sheet_name="全部名称", index=False)
        df.groupby("phylum_cn").size().rename("名称数").to_excel(w, sheet_name="按门统计")
    vc = df["rank"].value_counts()
    return [f"《中国海洋生物名录》doc {doc[0]}, {len(pages)} 页 -> {len(df)} 个名称: "
            + ", ".join(f"{k} {v}" for k, v in vc.items() if k in ("Phylum", "Class", "Order", "Family", "Genus",
                                                                    "Species", "Subspecies")),
            f"-> {DB}", f"-> {XLSX}"]


def norm(latin):
    s = re.sub(r"\([^)]*\)", " ", latin.lower())  # 去亚属
    return " ".join(w[:-1] if w.endswith("ii") else w for w in s.split())


def lookup(queries):
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT latin, cn, rank, author, family, family_cn, page, note FROM names").fetchall()
    for q in queries:
        if re.search(r"[一-鿿]", q):
            hits = [r for r in rows if q in r[1]]
        else:
            nq = norm(q)
            hits = [r for r in rows if norm(r[0]) == nq] or [r for r in rows if norm(r[0]).startswith(nq)]
            if not hits:  # 名录【】中的异名 -> 有效名的中文名
                hits = [r for r in rows if r[7] and nq in norm(r[7])]
        print(f"== {q}: {len(hits)} 条" + ("" if hits else "  (名录无此名: 保留拉丁名, 勿意译)"))
        for latin, cn, rank, author, fam, fam_cn, page, note in hits[:15]:
            syn = f"  (查询名为其异名: {note[:80]})" if note and norm(latin) != norm(q) and not norm(latin).startswith(norm(q)) else ""
            print(f"   {latin} {author}  =  {cn}   [{rank}; {fam_cn} {fam}; 名录 PDF p.{page}]{syn}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("step", choices=["build", "lookup"])
    ap.add_argument("names", nargs="*")
    a = ap.parse_args()
    if a.step == "build":
        summary("11_cn_names build", build(a.corpus))
    else:
        lookup(a.names)


if __name__ == "__main__":
    main()
