"""15 文献映射表: 每个文件 -> 作者/年份/题名/期刊/DOI (按内容识别, 不靠文件名).

  用户 2026-10-22: "我这台电脑可能包含所有常见多毛文献了, 只是文件名可能不对 ... 所以我才需要搞个映射表".
  (例: create_pdf.pdf = 赫列勃维奇 1963 海南岛潮间带沙蚕科; 珠江多毛类.pdf = 沈寿彭 & 戚桑 1982)

  python3 15_biblio.py <corpus> auto [--workers N]   DOI -> Crossref; 无 DOI 的英文文献: 首页最大字号行作题名 -> Crossref 检索;
                                                    Crossref 题名须在首页原文中对上 (防把首页引用的他文 DOI 当本文)
  python3 15_biblio.py <corpus> prev                并入用户旧映射 (溪沙蚕属-review/data/catalog_papers, 2026-09)
  python3 15_biblio.py <corpus> pack [--batch 120]  未识别的按首页文字去重 -> biblio_batches/ 交子代理 (BIBLIO_PROMPT.md)
  python3 15_biblio.py <corpus> merge               合并子代理结果 + 同一论文多副本归并 -> <backup>/文库/文献映射表.xlsx

  表 biblio (doc_id 主键): doi, authors, year, title, journal, volume, issue, pages, doc_type, language,
                          source (crossref_doi / crossref_title / agent), confidence, paper_key, note
"""
import argparse
import hashlib
import json
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "lib"))
import litdb  # noqa: E402
from common import CACHE, summary  # noqa: E402

sys.path.insert(0, "/mnt/n/codex/WORMS")
from worms_taxonomy_app.http_client import CachedHttpClient  # noqa: E402

CR = "https://api.crossref.org/works"
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>,;()\[\]]+)", re.I)
CJK = re.compile(r"[一-鿿]")
SCHEMA = """
CREATE TABLE IF NOT EXISTS biblio (
    doc_id INTEGER PRIMARY KEY, doi TEXT, authors TEXT, year TEXT, title TEXT, journal TEXT, volume TEXT,
    issue TEXT, pages TEXT, doc_type TEXT, language TEXT, source TEXT, confidence TEXT, paper_key TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS biblio_key ON biblio(paper_key);
"""
COLS = ["doi", "authors", "year", "title", "journal", "volume", "issue", "pages", "doc_type", "language", "source",
        "confidence", "paper_key", "note"]
_local = threading.local()


def http():
    if not hasattr(_local, "c"):
        _local.c = CachedHttpClient(CACHE / "worms_cache.sqlite", delay_seconds=0.4)  # 2 线程约 5 次/秒 (Crossref 公共池限速)
    return _local.c


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def title_in_text(title, text):
    """Crossref 题名是否出现在首页文字中 (容 OCR/换行): 题名词 >= 80% 出现在首页."""
    tw = [w for w in norm(title).split() if len(w) > 2]
    if not tw:
        return False
    tx = set(norm(text).split())
    if sum(w in tx for w in tw) / len(tw) >= 0.8:
        return True
    compact = norm(title).replace(" ", "")[:40]  # Crossref 题名常粘连 ("ofOphryotrocha puerilisandO.")
    return len(compact) >= 20 and compact in norm(text).replace(" ", "")


def from_crossref(m):
    au = "; ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") for a in m.get("author", [])[:12])
    year = (m.get("issued", {}).get("date-parts") or [[None]])[0][0]
    return {"doi": m.get("DOI", "").lower(), "authors": au, "year": str(year or ""),
            "title": re.sub(r"<[^>]+>|\ufeff", "", " ".join(m.get("title") or [])).strip(), "journal": " ".join(m.get("container-title") or []),
            "volume": m.get("volume", ""), "issue": m.get("issue", ""), "pages": m.get("page", ""),
            "doc_type": m.get("type", ""), "language": m.get("language", "")}


def biggest_lines(path, n=3):
    """首页字号最大的几行 (原生数字 PDF 的题名通常是最大字号)."""
    import fitz
    try:
        with fitz.open(path) as d:
            spans = [(round(s["size"], 1), s["text"].strip()) for b in d[0].get_text("dict")["blocks"]
                     for ln in b.get("lines", []) for s in ln["spans"] if len(s["text"].strip()) > 3]
    except Exception:
        return ""
    if not spans:
        return ""
    top = sorted({sz for sz, _ in spans}, reverse=True)[:1]
    return " ".join(t for sz, t in spans if sz in top)[:300]


def identify(doc_id, cand, text, meta):
    """单篇: 先 DOI, 再题名检索 (cand = 首页最大字号行, 进程池预先算好; PyMuPDF 非线程安全); 返回 biblio 行或 None."""
    head = text[:6000]
    dois = []
    for src in (meta or "", head):
        for d in DOI_RE.findall(src):
            d = d.rstrip(".").lower()
            if d not in dois:
                dois.append(d)
    for d in dois[:4]:
        try:
            m = http().get_json(f"{CR}/{d}")["message"]
        except Exception:
            continue
        row = from_crossref(m)
        if title_in_text(row["title"], head):
            return {**row, "source": "crossref_doi", "confidence": "high", "note": ""}
    if CJK.search(head[:1500]) and len(CJK.findall(head[:1500])) > 100:
        return None  # 中文文献 Crossref 覆盖差 -> 子代理
    if len(norm(cand).split()) < 4:
        return None
    try:
        items = http().get_json(CR, params={"query.bibliographic": cand, "rows": 3})["message"]["items"]
    except Exception:
        return None
    for m in items:
        row = from_crossref(m)
        if SequenceMatcher(None, norm(row["title"]), norm(cand)).ratio() >= 0.85 and title_in_text(row["title"], head):
            return {**row, "source": "crossref_title", "confidence": "medium", "note": f"首页大字: {cand[:80]}"}
    return None


def _big(args):
    d, path = args
    return d, biggest_lines(path)


def auto(corpus, workers):
    from concurrent.futures import ProcessPoolExecutor
    con = litdb.connect(corpus)
    con.executescript(SCHEMA)
    src = Path(litdb.corpus_cfg(corpus)["source"])
    done = {r[0] for r in con.execute("SELECT doc_id FROM biblio")}
    docs = [(d, str(src / rel), meta) for d, rel, meta in
            con.execute("SELECT doc_id, relpath, pdf_meta FROM docs WHERE status='ok' AND kind='pdf'") if d not in done]
    texts = {}
    for d, _, _ in docs:
        texts[d] = "\n".join(t or "" for (t,) in con.execute(
            "SELECT text FROM pages WHERE doc_id=? AND page_no<=2 ORDER BY page_no", (d,)))
    with ProcessPoolExecutor(8) as ex:  # PyMuPDF 只在子进程里用 (线程里用曾触发 glibc pthread 断言崩溃)
        big = dict(ex.map(_big, [(d, p) for d, p, _ in docs], chunksize=8))
    t0, n_ok, by = time.time(), 0, {}
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(identify, d, big.get(d, ""), texts[d], m): d for d, _, m in docs}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            if r:
                r["paper_key"] = "doi:" + r["doi"] if r.get("doi") else ""
                con.execute(f"INSERT OR REPLACE INTO biblio (doc_id, {', '.join(COLS)}) VALUES (?{', ?' * len(COLS)})",
                            (futs[f], *[r.get(c, "") for c in COLS]))
                n_ok += 1
                by[r["source"]] = by.get(r["source"], 0) + 1
            if i % 200 == 0:  # 边跑边提交, 中断不丢
                con.commit()
                print(f"  {i}/{len(docs)} 识别 {n_ok}, {time.time() - t0:.0f}s", flush=True)
    con.commit()
    return [f"自动识别 {len(docs)} 篇: 成功 {n_ok} ({by}), 用时 {time.time() - t0:.0f}s",
            f"未识别 {len(docs) - n_ok} 篇 -> 下一步 pack 交子代理"]


def pack(corpus, batch):
    con = litdb.connect(corpus)
    con.executescript(SCHEMA)
    out = Path(litdb.corpus_cfg(corpus)["db"]).parent / "biblio_batches"
    out.mkdir(exist_ok=True)
    for f in out.glob("b*.jsonl"):
        f.unlink()
    done = {r[0] for r in con.execute("SELECT doc_id FROM biblio")}
    seen, items, groups = {}, [], {}
    for d, rel, orig, meta in con.execute("SELECT doc_id, relpath, coalesce(orig_path, relpath), pdf_meta FROM docs"
                                          " WHERE status='ok' ORDER BY doc_id"):
        if d in done:
            continue
        pg = list(con.execute("SELECT page_no, text FROM pages WHERE doc_id=? AND page_no<=3 ORDER BY page_no", (d,)))
        first = next((t for _, t in pg if t and len(t.strip()) > 200), pg[0][1] if pg else "") or ""
        key = hashlib.md5(re.sub(r"\W", "", first.lower())[:1500].encode()).hexdigest()
        if key in seen:  # 副本: 同首页文字 -> 共用一次识别
            groups[seen[key]].append(d)
            continue
        seen[key] = d
        groups[d] = [d]
        n_pages = con.execute("SELECT n_pages FROM docs WHERE doc_id=?", (d,)).fetchone()[0]
        items.append({"doc_id": d, "file": Path(orig).name, "folder": str(Path(orig).parent)[-80:], "pages": n_pages,
                      "pdf_meta": (meta or "")[:300],
                      "text": "\n".join(f"[p.{p}] {re.sub(r'[ \t]+', ' ', t or '')[:1500 if i == 0 else 300]}"
                                         for i, (p, t) in enumerate(pg))[:2200]})
    for i in range(0, len(items), batch):
        with open(out / f"b{i // batch:03d}.jsonl", "w", encoding="utf-8") as f:
            for it in items[i:i + batch]:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    (out / "groups.json").write_text(json.dumps({str(k): v for k, v in groups.items()}), encoding="utf-8")
    return [f"未识别 {sum(len(v) for v in groups.values())} 个文件, 按首页去重 {len(items)} 篇 -> "
            f"{-(-len(items) // batch)} 批 ({batch}/批) -> {out}", "子代理按 BIBLIO_PROMPT.md 输出 b*.out.tsv; 然后 merge"]


PREV = Path("/mnt/n/溪沙蚕属-review/data")  # 用户 2026-09 溪沙蚕属文献库: 195 论文 (Crossref + 人工核对)


def prev(corpus):
    """并入旧映射 catalog_papers (md5 + local_file -> 书目): 按大小初筛库内文件, 再算 md5 对上; 不覆盖 crossref_doi.
    (all_scan_v2 的 md5 列多为空 (当时 NOMD5), 不能用路径 -> md5)"""
    cat = pd.read_csv(PREV / "catalog_papers.tsv", sep="\t", dtype=str).fillna("")  # local_file = 改名后的现路径
    proj = PREV.parent
    by_md5, sizes = {}, {}
    for r in cat.itertuples():
        f = proj / r.local_file
        if r.md5 and r.local_file and f.exists():
            by_md5[r.md5] = r
            sizes.setdefault(f.stat().st_size, []).append(r.md5)
    con = litdb.connect(corpus)
    con.executescript(SCHEMA)
    src = Path(litdb.corpus_cfg(corpus)["source"])
    n = 0
    for d, rel, size in con.execute("SELECT doc_id, relpath, size FROM docs").fetchall():
        if size not in sizes:
            continue
        p = src / rel
        h = hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else ""
        r = by_md5.get(h)
        if r is None:
            continue
        cur = con.execute("SELECT source FROM biblio WHERE doc_id=?", (d,)).fetchone()
        if cur and cur[0] == "crossref_doi":
            continue
        vals = {"doi": r.doi.lower(), "authors": r.authors, "year": r.year, "title": r.title, "journal": r.source,
                "volume": r.volume, "issue": r.issue, "pages": r.page_range, "doc_type": r.doc_type,
                "language": r.language, "source": "prev_catalog", "confidence": r.confidence,
                "paper_key": "", "note": "溪沙蚕属文献库 2026-09"}
        con.execute(f"INSERT OR REPLACE INTO biblio (doc_id, {', '.join(COLS)}) VALUES (?{', ?' * len(COLS)})",
                    (d, *[vals[c] for c in COLS]))
        n += 1
    con.commit()
    return [f"旧映射 {len(by_md5)} 个文件 (md5), 对上库内 {n} 个文件 (crossref_doi 已识别的不覆盖)"]


def paper_key(r):
    if r.get("doi"):
        return "doi:" + r["doi"].lower()
    t = norm(r.get("title", ""))[:60] or re.sub(r"\s+", "", r.get("title", ""))[:30]
    return f"t:{t}|{r.get('year', '')}" if t else ""


def merge(corpus):
    cfg = litdb.corpus_cfg(corpus)
    con = litdb.connect(corpus)
    con.executescript(SCHEMA)
    out = Path(cfg["db"]).parent / "biblio_batches"
    groups = json.loads((out / "groups.json").read_text(encoding="utf-8")) if (out / "groups.json").exists() else {}
    n = 0
    for f in sorted(out.glob("b*.out.tsv")):
        for r in pd.read_csv(f, sep="\t", dtype=str, quoting=3, encoding="utf-8-sig").fillna("").to_dict("records"):
            for d in groups.get(str(r["doc_id"]), [r["doc_id"]]):
                vals = {c: r.get(c, "") for c in COLS}
                vals["source"] = "agent"
                con.execute(f"INSERT OR REPLACE INTO biblio (doc_id, {', '.join(COLS)}) VALUES (?{', ?' * len(COLS)})",
                            (int(d), *[vals[c] for c in COLS]))
                n += 1
    for d, *vals in con.execute(f"SELECT doc_id, {', '.join(COLS)} FROM biblio").fetchall():
        con.execute("UPDATE biblio SET paper_key=? WHERE doc_id=?", (paper_key(dict(zip(COLS, vals))), d))
    con.commit()
    df = pd.read_sql("SELECT b.*, d.relpath AS 文库路径, coalesce(d.orig_path, '') AS 原路径, d.n_pages FROM biblio b"
                     " JOIN docs d USING (doc_id)", con)
    papers = (df.groupby("paper_key", dropna=False)
              .agg(authors=("authors", "first"), year=("year", "first"), title=("title", "first"),
                   journal=("journal", "first"), volume=("volume", "first"), pages=("pages", "first"),
                   doi=("doi", "first"), source=("source", "first"), 文件数=("doc_id", "count"),
                   文件=("文库路径", lambda s: "\n".join(s)), doc_ids=("doc_id", lambda s: ",".join(map(str, s))))
              .reset_index().sort_values(["authors", "year"]))
    xlsx = Path(cfg["backup"]) / "文库" / "文献映射表.xlsx"
    with pd.ExcelWriter(xlsx) as w:
        papers.to_excel(w, sheet_name="论文 (多副本合并)", index=False)
        df.to_excel(w, sheet_name="文件 -> 论文", index=False)
    total = con.execute("SELECT count(*) FROM docs WHERE status='ok'").fetchone()[0]
    return [f"合并子代理结果 {n} 行; 已映射 {len(df)}/{total} 个文件 -> {len(papers)} 篇论文", f"-> {xlsx}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("step", choices=["auto", "prev", "pack", "merge"])
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--batch", type=int, default=120)
    a = ap.parse_args()
    lines = {"auto": lambda: auto(a.corpus, a.workers), "prev": lambda: prev(a.corpus), "pack": lambda: pack(a.corpus, a.batch),
             "merge": lambda: merge(a.corpus)}[a.step]()
    summary(f"15_biblio {a.step}", lines)


if __name__ == "__main__":
    main()
