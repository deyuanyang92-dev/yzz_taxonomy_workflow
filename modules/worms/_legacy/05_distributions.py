"""05 分布记录 (提取层): WoRMS Documented distribution 全部记录 (含非模式记录) -> distributions.tsv

只照搬 WoRMS 记录值, REST AphiaDistributionsByAphiaID 每个字段原样保留.
输入: names.tsv (种级名称)
输出: 02_原始数据/worms/distributions.tsv  每行 = 一个名称的一条分布记录
字段 (WoRMS 原名): locality, locationID (Marine Regions MRGID), higherGeography, higherGeographyID, recordStatus,
      typeStatus (模式产地标记), establishmentMeans, invasiveness, occurrence, decimalLatitude, decimalLongitude,
      qualityStatus, sourceID, sourceReference ... (WoRMS 返回什么就保留什么)
补充 (2026-11-09): REST 不给每条分布的来源文献。网页 taxdetails 里每条分布有 id (aphia_ct_dr_<id>)，
      详情页 aphia.php?p=distribution&id=<id> 有 Source / Note / Type locality / Geounit。
      逐条抓取后按 locality 与 REST 记录配对，新增列:
      dist_id, dist_geounit, dist_source (记录出处文献), dist_note, dist_type_locality, dist_url。
      网页有而 REST 无的记录也保留 (rest_missing=Y)。
用法: python3 05_distributions.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import clean, data_dir, read_tsv, summary, write_tsv
import re

from worms import WEB, client, label_pairs, pmap

SP = {"Species", "Subspecies", "Variety", "Forma"}


def one(aid):
    return [{"aphia_id": aid, **{k: clean(v) for k, v in d.items()}} for d in (client().distributions(int(aid)) or [])]


TRAIL = re.compile(r"\s*\([^()]*\)\s*$")


def _strip(x):
    """'Madagascar (Nation) ( doubtful )' -> 'Madagascar' (all trailing parentheses)."""
    x = str(x or "").strip()
    while TRAIL.search(x):
        x = TRAIL.sub("", x).strip()
    return x


def _norm(x):
    return _strip(x).lower()


def web_details(aid):
    """taxdetails 页 -> 每条分布的 id -> 详情页字段."""
    c = client()
    page = c.taxdetails_html(int(aid)) or ""
    ids = list(dict.fromkeys(re.findall(r"aphia_ct_dr_(\d+)", page)))
    out = []
    for i in ids:
        d = label_pairs(c.http.get_text(WEB, params={"p": "distribution", "id": i}))
        g = d.get("Geounit", "")
        st = re.search(r"\(\s*(doubtful|inaccurate|valid|questionable)\s*\)", g, re.I)
        out.append({"aphia_id": str(aid), "dist_id": i, "dist_geounit": g,
                    "dist_status_web": st.group(1).lower() if st else "",
                    "dist_source": d.get("Source", ""), "dist_note": d.get("Note", ""),
                    "dist_type_locality": d.get("Type locality", ""),
                    "dist_url": f"{WEB}?p=distribution&id={i}"})
    return out


def attach_web(d, web):
    """REST 行与网页详情按 (aphia_id, locality) 顺序配对; 配不上的网页记录追加为 rest_missing=Y."""
    pool = {}
    for w in web:
        pool.setdefault((w["aphia_id"], _norm(w["dist_geounit"])), []).append(w)
    rows, last = [], {}
    for r in d.to_dict("records"):
        key = (str(r["aphia_id"]), _norm(r.get("locality")))
        if pool.get(key):
            w = last[key] = pool[key].pop(0)
        else:   # REST 重复行 (同名同地多条) 共用该地已配上的网页详情
            w = {**last[key], "dist_shared": "Y"} if key in last else {}
        rows.append({**r, **{k: v for k, v in w.items() if k != "aphia_id"}})
    for ws in pool.values():
        for w in ws:
            rows.append({**w, "locality": _strip(w["dist_geounit"]), "rest_missing": "Y",
                         "recordStatus": w.get("dist_status_web") or "valid",
                         "typeStatus": "holotype" if w["dist_type_locality"] == "Yes" else ""})
    return pd.DataFrame(rows)


def main(taxon):
    out = data_dir(taxon, "worms")
    n = read_tsv(out / "names.tsv")
    ids = list(n[n["rank"].isin(SP)].aphia_id)
    res = pmap(one, ids)
    d = pd.DataFrame([x for r in res if r for x in r])
    if not len(d):
        d = pd.DataFrame(columns=["aphia_id", "locality", "typeStatus"])
    d["aphia_id"] = d["aphia_id"].astype(str)
    web = [x for r in pmap(web_details, ids) if r for x in r]
    d = attach_web(d, web)
    src = d.get("dist_source", pd.Series(dtype=str)).fillna("") != ""
    write_tsv(d, out / "distributions.tsv")
    ts = d.get("typeStatus", pd.Series(dtype=str)).fillna("") != ""
    coords = d.get("decimalLatitude", pd.Series(dtype=str)).fillna("") != ""
    summary("05_distributions", [f"{len(d)} distribution records on {d.aphia_id.nunique()} names (type-status {int(ts.sum())}, "
                                 f"other {int((~ts).sum())}); with coordinates {int(coords.sum())}; with source {int(src.sum())}; "
                                 f"web-only {int((d.get('rest_missing', pd.Series(dtype=str)) == 'Y').sum())}; failed {sum(r is None for r in res)}",
                                 f"-> {out / 'distributions.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
