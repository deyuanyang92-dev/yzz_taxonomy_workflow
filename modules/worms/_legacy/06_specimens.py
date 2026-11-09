"""06 标本: WoRMS Specimen 数据库中类群 (含下级) 的全部标本 -> specimens.tsv

输入: 类群名 (不依赖其他步骤)
输出: 02_原始数据/worms/specimens.tsv  每行 = 一份标本
来源 (WoRMS 网页, 无 REST):
  清单  aphia.php?p=speclist&pid=<AphiaID>&inc_sub=1&action=search&rSkips=N  (100 条/页; 过滤参数是 pid,
        用 tid/tName 会被忽略而返回全库 13 万条)
  详情  aphia.php?p=specdetails&id=<id>  <label>-><div> 全部字段原样保留 (列名前缀 'worms: ')
另解析: type_status, catalog_no, institution, latitude, longitude, depth_min_m, depth_max_m.
用法: python3 06_specimens.py <Taxon>
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, num, summary, write_tsv
from worms import WEB, aphia_id, client, html_text, label_pairs, pmap


def speclist(pid):
    c, rows, skip, total = client(), [], 0, None
    while True:
        h = c.http.get_text(WEB, params={"p": "speclist", "pid": pid, "inc_sub": 1, "action": "search", "rSkips": skip})
        if total is None:
            m = re.search(r"([\d ]+) matching records", h)
            total = int(m.group(1).replace(" ", "")) if m else 0
        items = re.findall(r'<li class="list-group-item">(.*?)</li>', h, re.S)
        for it in items:
            m = re.search(r"specdetails&(?:amp;)?id=(\d+)&(?:amp;)?tid=(\d+)", it)
            if m:
                ts, ident = re.search(r"<b>(.*?)</b>", it, re.S), re.search(r"identified as\s*(.*)$", it, re.S)
                rows.append({"specimen_id": m.group(1), "aphia_id": m.group(2),
                             "type_status_list": html_text(ts.group(1)) if ts else "",
                             "identified_as": html_text(ident.group(1)) if ident else ""})
        skip += 100
        if not items or skip >= total:
            return rows, total


def main(taxon):
    out = data_dir(taxon, "worms")
    pid = aphia_id(taxon)
    items, total = speclist(pid)
    dets = pmap(lambda r: label_pairs(client().specdetails_html(int(r["specimen_id"]))), items)
    rows = []
    for it, d in zip(items, dets):
        d = d or {}
        ident = d.get("Identification", "")
        lo = num(d.get("Depthshallow") or d.get("Depth"))
        hi = num(d.get("Depthdeep")) or lo
        rows.append({**it,
                     "type_status": ident.split(":")[0].strip() if ":" in ident else it["type_status_list"],
                     "catalog_no": d.get("Code/Catalog no.", ""), "institution": d.get("Museum", "").split(" - ")[0],
                     "latitude": num(d.get("Start latitude") or d.get("Latitude")),
                     "longitude": num(d.get("Start longitude") or d.get("Longitude")),
                     "depth_min_m": lo, "depth_max_m": hi,
                     **{f"worms: {k}": v for k, v in d.items()},
                     "specimen_url": f"{WEB}?p=specdetails&id={it['specimen_id']}", "fetch_error": "" if dets else "Y"})
    s = pd.DataFrame(rows)
    write_tsv(s, out / "specimens.tsv")
    summary("06_specimens", [f"{taxon} (AphiaID {pid}): {len(s)}/{total} specimens; names {s.aphia_id.nunique() if len(s) else 0}",
                             "type status: " + "; ".join(f"{k} {v}" for k, v in s.type_status.value_counts().items()) if len(s) else "",
                             f"coords {s.latitude.notna().sum() if len(s) else 0}; depth {s.depth_min_m.notna().sum() if len(s) else 0}",
                             f"-> {out / 'specimens.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
