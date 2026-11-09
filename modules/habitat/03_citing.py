"""03 引文滚雪球: 从经典文献出发, 收集引用它的文献 (forward) 和新增 yes 文献的参考文献 (backward) -> 待筛表

来源: OpenAlex (cites:/referenced_works) ∪ Semantic Scholar (citations/references), 按 DOI / 标题去重.
状态文件: 02_原始数据/habitat/works.tsv (每篇一行; decision 由子代理筛选后经 04 写回)
每轮输出: 02_原始数据/habitat/screen/to_screen_round<N>.tsv (只含 decision 为空的新文献)

用法:
  python3 03_citing.py <Taxon>            第 1 轮: config.seeds_doi 的全部 forward 引用
  python3 03_citing.py <Taxon> --next     下一轮: 上一轮 yes 文献的 forward + backward (未展开过的)
  python3 03_citing.py <Taxon> --search   关键词检索臂: config.search_queries 在 OpenAlex 检索 (from_year 起), 记为 round S
  python3 03_citing.py <Taxon> --next --productive [--limit N]
                                          下一轮只展开带来新物种记录 (additions.tsv 中不在底本且未排除) 的文献,
                                          按新种数降序; 无 OpenAlex key 时用来节省额度
  python3 03_citing.py <Taxon> --status   各轮各决定计数
停止条件: 某轮新增 yes 为 0, 或新增 yes 文献不再带来新物种 (由 05 判断).
"""
import argparse, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import pandas as pd
from common import CACHE, data_dir, read_tsv, summary, write_tsv

OA = "https://api.openalex.org"
S2 = "https://api.semanticscholar.org/graph/v1"
COLS = ["id", "doi", "openalex", "s2", "year", "title", "venue", "abstract", "round", "via", "direction",
        "decision", "reason", "expanded"]
HTTP_CACHE = CACHE / "citation_http.json"
KEYFILE = Path(__file__).resolve().parents[2] / "config" / "openalex.json"   # {"api_key": "..."}; gitignored
OA_KEY = json.loads(KEYFILE.read_text()).get("api_key", "") if KEYFILE.exists() else ""
OA_DOWN = [False]
_cache = json.loads(HTTP_CACHE.read_text()) if HTTP_CACHE.exists() else {}
_last = [0.0]


def get(url, delay=1.1):
    if url in _cache:
        return _cache[url]
    if url.startswith(OA) and OA_DOWN[0]:
        return None
    real = url + (("&" if "?" in url else "?") + "api_key=" + OA_KEY if url.startswith(OA) and OA_KEY else "")
    for i in range(5):
        wait = delay - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(real, headers={"User-Agent": "yzz-checklist/1.0"}),
                                        timeout=60) as r:
                data = json.loads(r.read().decode())
            _cache[url] = data
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                _cache[url] = None
                return None
            if e.code == 429 and url.startswith(OA):
                OA_DOWN[0] = True
                print("!! OpenAlex 429: 无 API key 的每日额度已用完; 在 config/openalex.json 写 {\"api_key\": ...} "
                      "(免费注册 https://openalex.org), 本次改用 Semantic Scholar", file=sys.stderr)
                return None
            time.sleep(5 * (i + 1))
        except Exception:
            time.sleep(5 * (i + 1))
    return None


def save_cache():
    HTTP_CACHE.write_text(json.dumps(_cache))


def norm_doi(d):
    d = (d or "").lower().strip()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", d)


def key(doi, title, oa=""):
    if doi:
        return "doi:" + norm_doi(doi)
    if title:
        return "t:" + re.sub(r"[^a-z0-9]", "", title.lower())[:120]
    return "oa:" + oa


def oa_abstract(inv):
    if not inv:
        return ""
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in pos)


def oa_row(w):
    return {"doi": norm_doi(w.get("doi")), "openalex": (w.get("id") or "").rsplit("/", 1)[-1],
            "year": w.get("publication_year") or "", "title": w.get("display_name") or "",
            "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
            "abstract": oa_abstract(w.get("abstract_inverted_index"))}


def oa_work(doi=None, oa_id=None):
    url = f"{OA}/works/doi:{urllib.parse.quote(doi)}" if doi else f"{OA}/works/{oa_id}"
    return get(url, 0.2)


def oa_citing(oa_id):
    out, cursor = [], "*"
    while cursor:
        d = get(f"{OA}/works?filter=cites:{oa_id}&per-page=200&cursor={urllib.parse.quote(cursor)}", 0.2)
        if not d:
            break
        out += [oa_row(w) for w in d.get("results", [])]
        cursor = (d.get("meta") or {}).get("next_cursor")
    return out


def oa_refs(oa_id):
    w = oa_work(oa_id=oa_id)
    ids = [r.rsplit("/", 1)[-1] for r in (w or {}).get("referenced_works", [])]
    out = []
    for i in range(0, len(ids), 50):
        d = get(f"{OA}/works?filter=openalex:{'|'.join(ids[i:i + 50])}&per-page=50", 0.2)
        out += [oa_row(x) for x in (d or {}).get("results", [])]
    return out


def s2_list(doi, kind):
    fields = "title,year,venue,externalIds,abstract"
    out, off = [], 0
    while True:
        d = get(f"{S2}/paper/DOI:{urllib.parse.quote(doi)}/{kind}?fields={fields}&limit=500&offset={off}")
        if not d or not d.get("data"):
            break
        for x in d["data"]:
            p = x.get("citingPaper") or x.get("citedPaper") or {}
            if not p.get("title"):
                continue
            out.append({"doi": norm_doi((p.get("externalIds") or {}).get("DOI")), "s2": p.get("paperId") or "",
                        "year": p.get("year") or "", "title": p["title"], "venue": p.get("venue") or "",
                        "abstract": p.get("abstract") or ""})
        if d.get("next") is None:
            break
        off = d["next"]
    return out


def s2_search(q, year_from, cap):
    out, off = [], 0
    while off < cap:
        d = get(f"{S2}/paper/search?query={urllib.parse.quote(q)}&year={year_from}-&fields=title,year,venue,"
                f"externalIds,abstract&limit=100&offset={off}")
        if not d or not d.get("data"):
            break
        for p in d["data"]:
            out.append({"doi": norm_doi((p.get("externalIds") or {}).get("DOI")), "s2": p.get("paperId") or "",
                        "year": p.get("year") or "", "title": p.get("title") or "", "venue": p.get("venue") or "",
                        "abstract": p.get("abstract") or ""})
        off += 100
        if d.get("next") is None:
            break
    return out[:cap]


def flat(x):
    return re.sub(r"\s+", " ", str(x or "")).strip()


def crossref_search(q, year_from, cap):
    out, off = [], 0
    while off < cap:
        d = get(f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(q)}"
                f"&filter=from-pub-date:{year_from}-01-01&rows=100&offset={off}"
                f"&select=DOI,title,issued,container-title,abstract", 0.5)
        items = ((d or {}).get("message") or {}).get("items") or []
        if not items:
            break
        for x in items:
            out.append({"doi": norm_doi(x.get("DOI")), "title": (x.get("title") or [""])[0],
                        "year": ((x.get("issued") or {}).get("date-parts") or [[""]])[0][0] or "",
                        "venue": (x.get("container-title") or [""])[0],
                        "abstract": re.sub(r"<[^>]+>", " ", x.get("abstract") or "")})
        off += 100
    return out[:cap]


def add(works, rows, rnd, via, direction):
    new = 0
    for r in rows:
        r = {k: flat(v) for k, v in r.items()}
        k = key(r.get("doi"), r.get("title"), r.get("openalex", ""))
        if k in works:
            w = works[k]
            for f in ("abstract", "venue", "openalex", "s2", "doi"):
                if not w.get(f) and r.get(f):
                    w[f] = r[f]
            continue
        works[k] = {**{c: "" for c in COLS}, **r, "id": k, "round": rnd, "via": via, "direction": direction}
        new += 1
    return new


def expand(works, item, rnd):
    doi, oa_id = item.get("doi"), item.get("openalex")
    if doi and not oa_id:
        w = oa_work(doi=doi)
        oa_id = (w or {}).get("id", "").rsplit("/", 1)[-1]
        item["openalex"] = oa_id
    n = 0
    if oa_id:
        n += add(works, oa_citing(oa_id), rnd, item["id"], "forward")
    if doi:
        n += add(works, s2_list(doi, "citations"), rnd, item["id"], "forward")
    if rnd > 1:   # backward only for newly accepted works (the seed's own references are pre-2009 and in the seed)
        if oa_id:
            n += add(works, oa_refs(oa_id), rnd, item["id"], "backward")
        if doi:
            n += add(works, s2_list(doi, "references"), rnd, item["id"], "backward")
    item["expanded"] = "Y"
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("taxon")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--search", action="store_true")
    ap.add_argument("--productive", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    d = data_dir(a.taxon, "habitat")
    (d / "screen").mkdir(exist_ok=True)
    wpath = d / "works.tsv"
    df = read_tsv(wpath, required=False)
    works = {r["id"]: r for r in df.to_dict("records")} if len(df) else {}
    if a.status:
        if not works:
            print("尚无 works.tsv")
            return
        t = pd.DataFrame(works.values())
        print(t.groupby(["round", "decision"]).size().unstack(fill_value=0).to_string())
        return
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    if a.search:
        rnd, new = "S", 0
        for q in cfg.get("search_queries", []):
            cursor, got, cap = "*", 0, cfg.get("search_max_per_query", 300)
            while cursor and got < cap:
                url = (f"{OA}/works?search={urllib.parse.quote(q)}&filter=from_publication_date:"
                       f"{cfg.get('search_from_year', 2009)}-01-01&per-page=200&cursor={urllib.parse.quote(cursor)}")
                dd = get(url, 0.2)
                if not dd:
                    break
                res = dd.get("results", [])[:cap - got]
                got += len(res)
                new += add(works, [oa_row(w) for w in res], rnd, "search:" + q, "search")
                cursor = (dd.get("meta") or {}).get("next_cursor")
                if not dd.get("results"):
                    break
            # Crossref arm (no key needed; titles always, abstracts when deposited)
            y, cap = cfg.get("search_from_year", 2009), cfg.get("search_crossref_max", 100)
            new += add(works, crossref_search(q, y, cap), rnd, "search:" + q, "search")
            # Semantic Scholar arm only with a key or when not rate-limited
            if cfg.get("search_s2", False):
                new += add(works, s2_search(q, y, cfg.get("search_max_per_query", 300)), rnd, "search:" + q, "search")
            save_cache()
        save_cache()
        t = pd.DataFrame(works.values())[COLS]
        write_tsv(t, wpath)
        scr = t[(t["round"] == "S") & (t["decision"] == "")]
        write_tsv(scr[["id", "year", "title", "venue", "abstract", "direction"]], d / "screen" / "to_screen_roundS.tsv")
        summary("03_citing", [f"检索臂: {len(cfg.get('search_queries', []))} 个检索式, 新增 {new} 篇 -> screen/to_screen_roundS.tsv"])
        return
    if not a.next:
        rnd = 1
        todo = []
        for doi in cfg["seeds_doi"]:
            k = key(doi, "")
            works.setdefault(k, {**{c: "" for c in COLS}, "id": k, "doi": norm_doi(doi), "round": "0",
                                 "via": "seed", "decision": "seed", "title": doi})
            if works[k].get("expanded") != "Y":
                todo.append(works[k])
    else:
        rounds = [int(w["round"]) for w in works.values() if str(w["round"]).isdigit()]
        # yes works found by the search arm are expanded together with the next numbered round
        rnd = max(rounds) + 1
        pending = [w for w in works.values() if not w["decision"]]
        if pending:
            raise SystemExit(f"还有 {len(pending)} 篇未筛选 (decision 空): 先派子代理筛选并运行 04_screen_merge")
        if a.productive:
            add_ = read_tsv(d / "additions.tsv")
            seed = read_tsv(d / "seed_worms.tsv")
            known = set(seed["accepted_aphia_id"]) - {""}
            new = add_[(add_["habitat_cn"] != "排除") & ~add_["accepted_aphia_id"].isin(known)]
            rank = new.groupby("work_id")["species"].nunique().sort_values(ascending=False)
            todo = [works[i] for i in rank.index if i in works and works[i].get("expanded") != "Y"]
        else:
            todo = [w for w in works.values() if w["decision"] == "yes" and w.get("expanded") != "Y"]
        if a.limit:
            todo = todo[:a.limit]
    new = 0
    for i, w in enumerate(todo, 1):
        new += expand(works, w, rnd)
        if i % 20 == 0:
            save_cache()
    save_cache()
    t = pd.DataFrame(works.values())[COLS]
    write_tsv(t, wpath)
    scr = t[(t["round"].astype(str) == str(rnd)) & (t["decision"] == "")]
    write_tsv(scr[["id", "year", "title", "venue", "abstract", "direction"]], d / "screen" / f"to_screen_round{rnd}.tsv")
    summary("03_citing", [f"第 {rnd} 轮: 展开 {len(todo)} 篇, 新增 {new} 篇待筛 -> screen/to_screen_round{rnd}.tsv",
                          f"works.tsv 共 {len(t)} 篇"])


if __name__ == "__main__":
    main()
