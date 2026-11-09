"""10 物种档案: 查一个种 -> 相关文献页 -> 子代理逐篇抽取 -> 合并成 Excel.

  python3 10_dossier.py <corpus> retrieve "Travisia forbesii" [--groups 4]
      WoRMS 取有效名 + 异名 -> FTS 检索 (种加词 + 属名同页; OCR 变体靠同篇种加词兜底)
      -> 按首命中页文字去重副本 -> species/<种>/packets/<doc_id>.txt (命中页 + 后 1 页) + groups.json
  (retrieve 按 DOSSIER_PROMPT.md 模板写 species/<种>/PROMPT.md; 子代理按它抽取 -> out/<doc_id>.meta.json / .chars.tsv / .syn.tsv)
  python3 10_dossier.py <corpus> merge "Travisia forbesii"
      -> species/<种>/<种>_档案.xlsx: 文献记录 / 性状长表 / 性状矩阵 (性状 × 文献) / 异名录 / 待补

  抽取规则沿用课题的性状定义 (Travisia: 大连-臭海蛹-2026/08_知识库/性状定义与计数规则.md).
"""
import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "lib"))
import litdb  # noqa: E402
from common import summary  # noqa: E402

MORPH = re.compile(r"prostomi|setiger|chaetiger|branchi|segment|parapod|pygid|annulat|lobe|borsten|soies|kiemen|"
                   r"branchies|жабр|щетин|刚节|口前叶|鳃", re.I)
MAX_PAGES = 40


def sp_dir(corpus, species):
    return Path(litdb.corpus_cfg(corpus)["db"]).parent / "species" / species.replace(" ", "_")


def names_of(species):
    """WoRMS 有效名 + 全部异名 -> [(genus, epithet, 全名 + 命名人)]."""
    import worms
    c = worms.client()
    recs = [r for r in c.records_by_name(species, marine_only=False) if r.get("status") == "accepted"]
    if not recs:
        raise SystemExit(f"WoRMS 无有效名 {species}")
    acc = recs[0]
    out = [acc] + c.synonyms(acc["AphiaID"])
    res = []
    for r in out:
        parts = r["scientificname"].split()
        if len(parts) >= 2:
            res.append((parts[0], parts[-1] if len(parts) == 2 else parts[1], f"{r['scientificname']} {r.get('authority') or ''}"))
    return acc, res


def fts_term(word):
    """属名/种加词 -> FTS 前缀词; 种加词去掉 -i/-ii/-ae 词尾差异 (forbesi/forbesii)."""
    w = re.sub(r"[^a-z]", "", word.lower())
    return (w[:-1] if w.endswith("ii") else w[:7] if len(w) > 7 else w) + "*"


def retrieve(corpus, species, n_groups, rules_path=None):
    acc, names = names_of(species)
    con = litdb.connect(corpus)
    clauses = sorted({f"({fts_term(e)} AND {fts_term(g)})" for g, e, _ in names})
    q = " OR ".join(clauses)
    hits = con.execute("SELECT p.doc_id, p.page_no, p.text FROM pages_fts f JOIN pages p ON p.rowid = f.rowid"
                       " WHERE pages_fts MATCH ?", (q,)).fetchall()
    docs_hit = {d for d, _, _ in hits}
    ep_only = " OR ".join(sorted({fts_term(e) for _, e, _ in names}))
    hits += [h for h in con.execute("SELECT p.doc_id, p.page_no, p.text FROM pages_fts f JOIN pages p"
                                    " ON p.rowid = f.rowid WHERE pages_fts MATCH ?", (ep_only,)) if h[0] in docs_hit]
    bydoc = collections.defaultdict(dict)
    for d, p, t in hits:
        bydoc[d][p] = t
    paths = dict(con.execute("SELECT doc_id, relpath FROM docs"))
    out = sp_dir(corpus, species)
    (out / "packets").mkdir(parents=True, exist_ok=True)
    (out / "out").mkdir(exist_ok=True)
    rows, seen, sizes = [], {}, []
    for d, ps in sorted(bydoc.items(), key=lambda x: -len(x[1])):
        hp = sorted(ps)
        key = hashlib.md5(re.sub(r"\W", "", ps[hp[0]].lower())[:3000].encode()).hexdigest()
        dup = seen.setdefault(key, d)
        rows.append({"doc_id": d, "path": paths[d], "pages": hp, "morph": sum(len(MORPH.findall(t)) for t in ps.values()),
                     "dup_of": None if dup == d else dup})
        if dup != d:
            continue
        n_pages, meta = con.execute("SELECT n_pages, pdf_meta FROM docs WHERE doc_id=?", (d,)).fetchone()
        want = sorted(set(hp) | {p + 1 for p in hp if p + 1 <= n_pages}) if len(hp) <= 20 else hp
        parts = [f"# doc_id={d}\n# path={paths[d]}\n# pdf_meta={meta or ''}\n# pages_in_doc={n_pages}; 命中页={hp}\n"]
        for p in want[:MAX_PAGES]:
            src, t = con.execute("SELECT source, text FROM pages WHERE doc_id=? AND page_no=?", (d, p)).fetchone()
            parts.append(f"\n=== PDF p.{p} ({src}){' [命中]' if p in ps else ''} ===\n{t}")
        txt = "".join(parts)
        (out / "packets" / f"{d}.txt").write_text(txt, encoding="utf-8")
        sizes.append((d, len(txt)))
    groups, load = [[] for _ in range(n_groups)], [0] * n_groups
    for d, n in sorted(sizes, key=lambda x: -x[1]):
        i = load.index(min(load))
        groups[i].append(d)
        load[i] += n
    (out / "hits.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (out / "groups.json").write_text(json.dumps(groups), encoding="utf-8")
    rules = rules_path or "（本类群暂无性状规则文件：按原文性状逐条记录，character 用简短英文代码）"
    names_txt = "；".join(f"*{n}*" for _, _, n in names)
    prompt = Path(__file__).with_name("DOSSIER_PROMPT.md").read_text(encoding="utf-8")
    for k, v in {"species": species, "names": names_txt, "dir": str(out), "rules": rules}.items():
        prompt = prompt.replace("{" + k + "}", v)  # 模板含 JSON 花括号, 不用 str.format
    (out / "PROMPT.md").write_text(prompt, encoding="utf-8")
    (out / "names.json").write_text(json.dumps({"accepted": acc, "names": names}, ensure_ascii=False), encoding="utf-8")
    return [f"{acc['scientificname']} {acc.get('authority')} (AphiaID {acc['AphiaID']}); 名称 {len(names)} 个",
            f"命中 {len(rows)} 篇, 去副本后 {len(sizes)} 篇, 共 {sum(n for _, n in sizes)} 字 -> {out / 'packets'}",
            f"分 {n_groups} 组 (每组约 {max(load)} 字) -> groups.json; 下一步: 子代理按 PROMPT.md 抽取"]


def merge(corpus, species):
    import pandas as pd
    out = sp_dir(corpus, species)
    hits = {r["doc_id"]: r for r in json.loads((out / "hits.json").read_text(encoding="utf-8"))}
    want = [d for d, r in hits.items() if r["dup_of"] is None]
    metas, chars, syns, missing = [], [], [], []
    for d in want:
        mf = out / "out" / f"{d}.meta.json"
        if not mf.exists():
            missing.append(d)
            continue
        m = json.loads(mf.read_text(encoding="utf-8"))
        m.update(doc_id=d, path=hits[d]["path"], copies=sum(r["dup_of"] == d for r in hits.values()))
        metas.append(m)
        for kind, bucket in (("chars", chars), ("syn", syns)):
            f = out / "out" / f"{d}.{kind}.tsv"
            if f.exists() and f.stat().st_size:
                t = pd.read_csv(f, sep="\t", dtype=str, quoting=3, on_bad_lines="warn")
                bucket.append(t.assign(doc_id=d, source_short=t.get("source_short", m.get("short"))))
    meta = pd.DataFrame(metas)
    ch = pd.concat(chars, ignore_index=True) if chars else pd.DataFrame()
    sy = pd.concat(syns, ignore_index=True) if syns else pd.DataFrame()
    if len(sy):
        sy = sy.merge(meta[["doc_id", "short"]], on="doc_id", how="left")
    order = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}
    if len(ch):
        ch["_lv"] = ch.level.map(order).fillna(9)
        mat = (ch[ch.character.ne("note_general")].sort_values("_lv")
               .assign(cell=lambda x: x.value.fillna(x.raw_value).fillna("") + x.certainty.eq("推测").map({True: " ?", False: ""})
                       + " [" + x.pages.fillna("") + "]")
               .pivot_table(index="character", columns="source_short", values="cell",
                            aggfunc=lambda s: " | ".join(dict.fromkeys(s))))
        ch = ch.drop(columns="_lv")
    else:
        mat = pd.DataFrame()
    xlsx = out / f"{species.replace(' ', '_')}_档案.xlsx"
    with pd.ExcelWriter(xlsx) as w:
        meta.sort_values(["record_type", "level"]).to_excel(w, sheet_name="文献记录", index=False)
        ch.to_excel(w, sheet_name="性状长表", index=False)
        mat.to_excel(w, sheet_name="性状矩阵")
        sy.to_excel(w, sheet_name="异名录", index=False)
        pd.DataFrame({"doc_id": missing, "path": [hits[d]["path"] for d in missing]}).to_excel(w, sheet_name="待补", index=False)
    rt = meta.record_type.value_counts().to_dict() if len(meta) else {}
    return [f"文献 {len(meta)} 篇 (未抽 {len(missing)}): {rt}",
            f"性状记录 {len(ch)} 行, 异名录 {len(sy)} 条 -> {xlsx}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("step", choices=["retrieve", "merge"])
    ap.add_argument("species")
    ap.add_argument("--groups", type=int, default=4)
    ap.add_argument("--rules", help="性状定义与计数规则 .md (如 大连-臭海蛹-2026/08_知识库/性状定义与计数规则.md)")
    a = ap.parse_args()
    summary(f"10_dossier {a.step}", retrieve(a.corpus, a.species, a.groups, a.rules) if a.step == "retrieve"
            else merge(a.corpus, a.species))


if __name__ == "__main__":
    main()
