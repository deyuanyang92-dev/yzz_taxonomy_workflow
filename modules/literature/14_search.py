"""14 按类群检索文献: 属/种 (拉丁或中文) -> 库内全部相关文献 (含异名、中文名简繁) -> Excel; 可按区域判定.

  python3 14_search.py <corpus> find 溪沙蚕属 [--region 中国]
      名称: 中文 -> 11_cn_names 知识库 -> 拉丁; WoRMS 取属下全部种 + 各种异名 (老文献多用 Lycastis abiuma 等);
            异名属 (Lycastis) 须与种加词同页才算, 防牵出无关种; 中文名用知识库 + 繁体.
      输出 <db 目录>/search/<名称>/文献.xlsx: 每篇 (副本合并) 命中页、提及名称、地名窗口、首页标题.
      --region: 学名前后 ±400 字窗口内出现区域地名 -> 地名同窗; 窗口行像 GenBank 表或参考文献 -> 疑似仅引用;
            并生成 packets/ + groups.json + PROMPT.md (模板 SEARCH_REGION_PROMPT.md), 由子代理读片段判定 A 本文有该区域材料/记录 / B 仅引用 / C 无关
            (用户 2026-10-21 纠正: Alves 2020-2024、Villalobos-Guerrero 2024、Wilson 2023 只引用中国序列/文献, 不是中国海文献).
  python3 14_search.py <corpus> merge 溪沙蚕属
      合并子代理判定 (packets_out/*.tsv) -> 文献.xlsx 加 判定 列 + 区域文献 工作表.
"""
import argparse
import collections
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "lib"))
import litdb  # noqa: E402
from common import summary  # noqa: E402

CJK = re.compile(r"[一-鿿]")
TRAD = str.maketrans("蚕虫须鳞节头齿鳃刚环纲门属种类叶毛缨栉丝锥异长圆双", "蠶蟲鬚鱗節頭齒鰓剛環綱門屬種類葉毛纓櫛絲錐異長圓雙")
REGIONS = {
    "中国": r"China|Chinese|South China Sea|East China Sea|Yellow Sea|Bohai|Hong ?Kong|Taiwan|Formosa|Hainan|Guangdong|"
            r"Guangxi|Fujian|Xiamen|Amoy|Zhejiang|Shandong|Qingdao|Jiangsu|Shanghai|Beibu|Tonkin|Nansha|Xisha|Pearl River|"
            r"Yangtze|Changjiang|Shenzhen|Zhanjiang|中国|南海|东海|黄海|渤海|台湾|臺灣|香港|海南|广东|廣東|广西|福建|厦门|"
            r"廈門|浙江|山东|江苏|上海|北部湾|南沙|西沙|珠江|长江|深圳|湛江|九龙江|漳江|红树林",
}
CITE_LINE = re.compile(r"\b[A-Z]{1,2}_?\d{5,8}\b|\(\d{4}\)\s*[A-Z][^.]{3,}\.\s*[A-Z][a-z]+.*\d+\s*[:(]|"
                       r"\b\d{1,4}\s*[:–-]\s*\d{1,4}\.?\s*$|doi\.org|https?://")
WIN = 400


def fts_term(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    return (w[:-1] if w.endswith("ii") else w[:7] if len(w) > 7 else w) + "*"


def resolve(query):
    """查询 -> (拉丁名, 级别, 中文名列表)."""
    cn = sqlite3.connect(ROOT / "cache" / "cn_names.sqlite")
    if CJK.search(query):
        rows = cn.execute("SELECT latin, rank, cn FROM names WHERE cn=?", (query,)).fetchall()
        if not rows:
            raise SystemExit(f"中文名 {query} 不在名录知识库 (11_cn_names); 请改用拉丁名")
        latin, rank, _ = rows[0]
    else:
        latin, rank = query, "Genus" if len(query.split()) == 1 else "Species"
    genus = latin.split()[0]
    pat = (genus + "%") if rank == "Genus" else latin
    cns = [r[0] for r in cn.execute("SELECT DISTINCT cn FROM names WHERE latin LIKE ?", (pat,))]
    alias = ROOT / "cache" / "cn_alias.tsv"  # 历史中文译名 (名录未收), 如 Namalycastis abiuma = 单叶沙蚕/缘目沙蚕
    if alias.exists():
        a = pd.read_csv(alias, sep="\t", dtype=str)
        cns += a[a.latin.str.startswith(genus if rank == "Genus" else latin)].cn_alias.tolist()
    return latin, rank, cns


def names_for(latin, rank):
    """WoRMS: 属 -> 属异名 + 属下全部种 (含非有效) + 各有效种异名; 种 -> 自身 + 异名."""
    import worms
    c = worms.client()
    acc = [r for r in c.records_by_name(latin, marine_only=False) if r.get("status") == "accepted"]
    if not acc:
        raise SystemExit(f"WoRMS 无有效名 {latin}")
    a = acc[0]
    genera, binomials = {latin.split()[0]}, set()
    if rank == "Genus":
        genera |= {s["scientificname"].split()[0] for s in c.synonyms(a["AphiaID"])}
        for k in c.children(a["AphiaID"], marine_only=False, extant_only=False):
            binomials.add(k["scientificname"])
            if k.get("status") == "accepted":
                binomials |= {s["scientificname"] for s in c.synonyms(k["AphiaID"])}
    else:
        binomials = {latin} | {s["scientificname"] for s in c.synonyms(a["AphiaID"])}
    return a, sorted(genera), sorted(b for b in binomials if len(b.split()) >= 2)


def find(corpus, query, region, n_groups=3):
    latin, rank, cns = resolve(query)
    acc, genera, binomials = names_for(latin, rank)
    con = litdb.connect(corpus)
    genus_q = " OR ".join(fts_term(g) for g in genera) if rank == "Genus" else ""
    syn_q = " OR ".join(sorted({f"({fts_term(b.split()[0])} AND {fts_term(b.split()[-1])})" for b in binomials
                                if b.split()[0] not in genera or rank != "Genus"}))
    q = " OR ".join(x for x in (genus_q, syn_q) if x)
    hits = con.execute("SELECT p.doc_id, p.page_no, p.text FROM pages_fts f JOIN pages p ON p.rowid=f.rowid"
                       " WHERE pages_fts MATCH ?", (q,)).fetchall()
    cn_terms = sorted({t for c in cns for t in (c, c.translate(TRAD)) if len(t) >= 3})
    for t in cn_terms:
        hits += con.execute("SELECT p.doc_id, p.page_no, p.text FROM pages_cjk k JOIN pages p ON p.rowid=k.page_rowid"
                            " WHERE pages_cjk MATCH ?", (f'"{t}"',)).fetchall()
    # 页内定位用正则: 属名 (宽) + 异名二名 + 中文名
    name_re = re.compile("|".join([rf"\b{re.escape(g)}\b" for g in genera]
                                  + [re.escape(b.split()[0]) + r"\s+" + re.escape(b.split()[-1][:-1]) for b in binomials]
                                  + [re.escape(t) for t in cn_terms]), re.I)
    reg = re.compile(REGIONS[region]) if region else None
    by = collections.defaultdict(dict)
    for d, p, t in hits:
        by[d][p] = t
    meta = {d: (rel, orig) for d, rel, orig in con.execute("SELECT doc_id, relpath, coalesce(orig_path, relpath) FROM docs")}
    rows, seen = [], {}
    out = Path(litdb.corpus_cfg(corpus)["db"]).parent / "search" / query.replace(" ", "_")
    if (out / "packets").exists():
        for f in (out / "packets").glob("*.txt"):  # 重跑: 清旧包
            f.unlink()
    (out / "packets").mkdir(parents=True, exist_ok=True)
    for d, ps in sorted(by.items(), key=lambda x: -len(x[1])):
        pages = sorted(ps)
        key = hashlib.md5(re.sub(r"\W", "", ps[pages[0]].lower())[:2000].encode()).hexdigest()
        if key in seen:
            rows[seen[key]]["副本数"] += 1
            rows[seen[key]]["副本路径"] += "\n" + meta[d][0]
            continue
        seen[key] = len(rows)
        found = collections.Counter()
        wins, near, cite_only = [], set(), True
        for p in pages:
            t = ps[p]
            for m in name_re.finditer(t):
                found[re.sub(r"\s+", " ", m.group(0))] += 1
                lo, hi = max(0, m.start() - WIN), m.end() + WIN
                w = t[lo:hi]
                if reg:
                    for r in reg.finditer(w):
                        near.add(r.group(0))
                        line = w[max(0, w.rfind("\n", 0, r.start())):w.find("\n", r.end()) if "\n" in w[r.end():] else None]
                        if not CITE_LINE.search(line):
                            cite_only = False
                if not wins or p != wins[-1][0] or lo > wins[-1][2]:
                    wins.append([p, lo, hi])
                else:
                    wins[-1][2] = hi
        first = con.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page_no LIMIT 1", (d,)).fetchone()[0] or ""
        row = {"doc_id": d, "文件": Path(meta[d][1]).name, "命中页数": len(pages), "页码": ",".join(map(str, pages[:30])),
               "提及名称": "; ".join(f"{k} ({v})" for k, v in found.most_common(8)),
               "首页": re.sub(r"\s+", " ", first[:200]), "副本数": 0, "文库路径": meta[d][0], "副本路径": "",
               "原路径": meta[d][1]}
        if reg:
            row["地名同窗"] = " ".join(sorted(near)[:8])
            row["疑似仅引用"] = bool(near) and cite_only
            if near:  # 只有地名同窗的才需子代理判定
                parts = [f"# doc_id={d}\n# 文件={meta[d][1]}\n# 首页: {re.sub(chr(10), ' ', first[:800])}\n"]
                for p, lo, hi in wins[:15]:
                    parts.append(f"\n=== PDF p.{p} ===\n{ps[p][lo:hi]}")
                (out / "packets" / f"{d}.txt").write_text("".join(parts), encoding="utf-8")
        rows.append(row)
    df = pd.DataFrame(rows)
    (out / "names.json").write_text(json.dumps({"query": query, "latin": latin, "aphia": acc["AphiaID"],
                                                "genera": genera, "binomials": binomials, "cn": cn_terms},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    df.to_excel(out / "文献.xlsx", index=False)
    lines = [f"{query} = {latin} (AphiaID {acc['AphiaID']}); 属名 {genera}; 二名 {len(binomials)} 个; 中文 {cn_terms}",
             f"命中 {len(by)} 篇, 合并副本后 {len(df)} 篇 -> {out / '文献.xlsx'}"]
    if reg:
        (out / "packets_out").mkdir(exist_ok=True)
        prompt = Path(__file__).with_name("SEARCH_REGION_PROMPT.md").read_text(encoding="utf-8")
        for k, v in {"region": region, "taxon": f"{query} ({latin})", "dir": str(out)}.items():
            prompt = prompt.replace("{" + k + "}", v)
        (out / "PROMPT.md").write_text(prompt, encoding="utf-8")
        sizes = sorted(((int(f.stem), f.stat().st_size) for f in (out / "packets").glob("*.txt")), key=lambda x: -x[1])
        groups, load = [[] for _ in range(n_groups)], [0] * n_groups
        for d, n in sizes:
            i = load.index(min(load))
            groups[i].append(d)
            load[i] += n
        (out / "groups.json").write_text(json.dumps(groups), encoding="utf-8")
        n_near = int((df["地名同窗"] != "").sum())
        lines.append(f"{region}: 地名同窗 {n_near} 篇 (其中疑似仅引用 {int(df['疑似仅引用'].sum())}) -> packets/ 待子代理判定")
    return lines


def merge(corpus, query):
    out = Path(litdb.corpus_cfg(corpus)["db"]).parent / "search" / query.replace(" ", "_")
    df = pd.read_excel(out / "文献.xlsx")
    res = pd.concat([pd.read_csv(f, sep="\t", dtype=str) for f in sorted((out / "packets_out").glob("*.tsv"))],
                    ignore_index=True)
    res["doc_id"] = res.doc_id.astype(int)
    df = df.merge(res, on="doc_id", how="left")
    with pd.ExcelWriter(out / "文献.xlsx") as w:
        df[df["判定"] == "A"].to_excel(w, sheet_name="区域文献_A", index=False)
        df[df["判定"] == "B"].to_excel(w, sheet_name="仅引用_B", index=False)
        df.to_excel(w, sheet_name="全部命中", index=False)
    vc = df["判定"].fillna("未判(无地名同窗)").value_counts().to_dict()
    return [f"判定: {vc}", f"-> {out / '文献.xlsx'}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("step", choices=["find", "merge"])
    ap.add_argument("query")
    ap.add_argument("--region", choices=sorted(REGIONS))
    ap.add_argument("--groups", type=int, default=3, help="子代理组数")
    a = ap.parse_args()
    summary(f"14_search {a.step}", find(a.corpus, a.query, a.region, a.groups) if a.step == "find" else merge(a.corpus, a.query))


if __name__ == "__main__":
    main()
