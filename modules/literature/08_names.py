"""08 学名索引: WoRMS 环节动物属名表 -> 全文中的 属 + 种加词.

  python3 08_names.py <corpus> genera     遍历 WoRMS Annelida (882, 含星虫/螠) 到属级, 含非有效属
                                          -> discovery 同级 genera.tsv (缓存在 cache/worms_cache.sqlite)
  python3 08_names.py <corpus> index      全库逐页抽学名 -> 表 names; 每篇统计 -> 表 doc_names

  匹配: 属名在 WoRMS 表中 (首字母大写或全大写标题) + 可选 (亚属) + 小写种加词 (非停用词);
        "sp." / "spp." 记属级; 缩写 "T. forbesii" -> 同篇此前最近的 T 开头属名 (abbrev=1).
  OCR 变体 (Travista、TEAYISIA) 不在此处理, 查询时可用种加词兜底.
"""
import argparse
import re
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "lib"))
import litdb  # noqa: E402
from common import summary  # noqa: E402

ANNELIDA = 882
GENUS_RANK = 180
STOP = set("""and the from with was were are for not that this which also see but has have had all its other than
into from new near only both each more most some such very about after before between under over these those
der die das und von mit des den dem ist sind ein eine les des une est dans pour par sur avec del los las por con
para que como una sp spp gen nov var cf aff fig figs pl tab table page see vide nec non sensu auct after""".split())
NAME = re.compile(r"\b([A-Z][a-z]{2,}|[A-Z]{3,})(?:\s+\(([A-Z][a-z]+)\))?\s+([a-z]{3,}|[A-Z]{3,}|spp?\.)")
ABBR = re.compile(r"\b([A-Z])\.\s?(?:\(([A-Z][a-z]+)\)\s+)?([a-z]{3,})\b")

NAMES_SQL = """
CREATE TABLE IF NOT EXISTS names (
    doc_id INTEGER, page_no INTEGER, genus TEXT, epithet TEXT,  -- epithet '' = 属级 (sp./spp.)
    n INTEGER, abbrev INTEGER, PRIMARY KEY (doc_id, page_no, genus, epithet, abbrev));
CREATE INDEX IF NOT EXISTS names_ge ON names(genus, epithet);
CREATE INDEX IF NOT EXISTS names_ep ON names(epithet);
CREATE TABLE IF NOT EXISTS doc_names (
    doc_id INTEGER, genus TEXT, epithet TEXT, n_pages INTEGER, n INTEGER, PRIMARY KEY (doc_id, genus, epithet));
"""


def genera_path(corpus):
    return Path(litdb.corpus_cfg(corpus)["db"]).parent / "genera.tsv"


def fetch_genera(corpus):
    import worms
    c = worms.client()
    seen, out, todo, calls = set(), [], [ANNELIDA], 0
    while todo:
        kids = c.children(todo.pop(), marine_only=False, extant_only=False)
        calls += 1
        for k in kids:
            if k["AphiaID"] in seen:
                continue
            seen.add(k["AphiaID"])
            rank = k.get("taxonRankID") or 0
            if rank == GENUS_RANK:
                out.append((k["scientificname"], k["AphiaID"], k.get("status") or "", k.get("valid_name") or "",
                            k.get("family") or ""))
            elif rank < GENUS_RANK:
                todo.append(k["AphiaID"])
        if calls % 100 == 0:
            print(f"  {calls} 次请求, 属 {len(out)}", flush=True)
    p = genera_path(corpus)
    p.write_text("genus\taphia_id\tstatus\tvalid_name\tfamily\n" +
                 "".join("\t".join(map(str, r)) + "\n" for r in sorted(out)), encoding="utf-8")
    return [f"WoRMS Annelida 遍历 {calls} 次请求, 属 {len(out)} 个 "
            f"(有效 {sum(r[2] == 'accepted' for r in out)}) -> {p}"]


_GEN: set[str] = set()


def _init(genera):
    _GEN.update(genera)


def scan_doc(args):
    """子进程: 一篇文献按页序抽学名, 缩写回溯同篇最近属名."""
    doc_id, pages = args
    last, rows = {}, Counter()
    for page_no, text in pages:
        for g, _sub, ep in NAME.findall(text):
            g = g.capitalize()
            if g not in _GEN:
                continue
            ep = "" if ep.startswith("sp") and ep.endswith(".") else ep.lower()
            if ep in STOP:
                continue
            last[g[0]] = g
            rows[(page_no, g, ep, 0)] += 1
        for ini, _sub, ep in ABBR.findall(text):
            if ini in last and ep not in STOP:
                rows[(page_no, last[ini], ep, 1)] += 1
    return [(doc_id, pn, g, ep, n, ab) for (pn, g, ep, ab), n in rows.items()]


def index(corpus, workers):
    import pandas as pd
    gen = pd.read_csv(genera_path(corpus), sep="\t").genus.dropna()
    genera = {g for g in gen if re.fullmatch(r"[A-Z][a-z]{2,}", g)}
    con = litdb.connect(corpus)
    con.executescript("DROP TABLE IF EXISTS names; DROP TABLE IF EXISTS doc_names;" + NAMES_SQL)
    t0 = time.time()

    def docs():
        cur, buf = None, []
        for doc_id, pn, text in con.cursor().execute(
                "SELECT doc_id, page_no, text FROM pages WHERE text <> '' ORDER BY doc_id, page_no"):
            if doc_id != cur and buf:
                yield cur, buf
                buf = []
            cur = doc_id
            buf.append((pn, text))
        if buf:
            yield cur, buf

    n_docs = 0
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(genera,)) as ex:
        for rows in ex.map(scan_doc, docs(), chunksize=4):
            con.executemany("INSERT INTO names VALUES (?,?,?,?,?,?)", rows)
            n_docs += 1
            if n_docs % 500 == 0:
                con.commit()
                print(f"  {n_docs} 篇 {time.time() - t0:.0f}s", flush=True)
    con.execute("INSERT INTO doc_names SELECT doc_id, genus, epithet, count(DISTINCT page_no), sum(n)"
                " FROM names GROUP BY doc_id, genus, epithet")
    con.commit()
    n, n_sp = con.execute("SELECT count(*), count(DISTINCT genus || ' ' || epithet) FROM names").fetchone()
    con.close()
    return [f"属名表 {len(genera)} 个; 扫描 {n_docs} 篇, 名称-页记录 {n} 条, 不同名称 {n_sp} 个,"
            f" 用时 {time.time() - t0:.0f}s", f"备份 -> {litdb.backup(corpus)}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("step", choices=["genera", "index"])
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    summary(f"08_names {a.step}", fetch_genera(a.corpus) if a.step == "genera" else index(a.corpus, a.workers))


if __name__ == "__main__":
    main()
