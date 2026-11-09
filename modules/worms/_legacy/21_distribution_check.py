"""21 分布记录 vs 模式产地: 每条 WoRMS 分布记录离模式产地多远 -> 广布种/远距记录待修订清单

目的 (用户 2026-11-09): 判断某种是否被记录为"广布种"; 远离模式产地的记录很可能是误鉴定或隐存种,
      值得修订或深入研究。
输入: names.tsv (名称 -> 有效名), distributions.tsv (05, 含每条来源 dist_source), coordinates.tsv (14, 模式产地坐标)
输出: 02_原始数据/worms/distribution_check.tsv    每行 = 一条分布记录 (已归到有效种)
      02_原始数据/worms/distribution_species.tsv  每行 = 一个有效种的汇总与判定
距离: 模式产地点到分布地理单元 (Marine Regions MRGID 边界框) 的最近距离; 点在框内 = 0。
      地理单元边界框对角线 > 3000 km (大洋、大海区) 且模式产地在其 2000 km 内: 粗略, 不判远近;
      离模式产地 > 2000 km 的大海区记录照样算 distant (如模式产地智利的种记录于新西兰 EEZ)。
类别: type locality | near (<= 500 km) | regional (500-2000 km) | distant (> 2000 km) | coarse region | no geometry
种级判定 (verdict):
  distant records    有 valid/unreviewed 状态的 distant 记录 -> 广布记录, 需核实鉴定 (候选误鉴定/隐存种)
  regional only      最远为 regional
  near TL only       非模式记录都在模式产地 500 km 内
  TL record only     WoRMS 只有模式产地记录
  TL rough (OD title) 模式产地坐标仅来自原始描述题目中的国名 (14 第 11 级), 距离仅供参考, 不判远距
  TL not located     模式产地无坐标, 无法判断
用法: python3 21_distribution_check.py <Taxon>
"""
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv
from worms import client, pmap

MR = "https://www.marineregions.org/rest/getGazetteerRecordByMRGID.json/{}/"
NEAR_KM, REGIONAL_KM, COARSE_KM = 500, 2000, 3000
ROUGH_BASIS = {"od_title_country_eez"}          # 14 步最粗一级 (原始描述题目中的国名), 不据此判远距


def sv(x):
    """单元格 -> str; NaN/None -> '' (NaN 是 float 且为真，直接 `or ''` 会漏)."""
    return x if isinstance(x, str) else ""


def hav_km(la1, lo1, la2, lo2):
    p = math.pi / 180
    a = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1, a)))


def mr_box(mrgid):
    """MRGID -> (minLat, maxLat, minLon, maxLon) 或 None (经 WoRMS 共用缓存)."""
    r = client().http.get_json(MR.format(mrgid))
    try:
        b = tuple(float(r[k]) for k in ("minLatitude", "maxLatitude", "minLongitude", "maxLongitude"))
    except (TypeError, KeyError, ValueError):
        if r and r.get("latitude") is not None:
            la, lo = float(r["latitude"]), float(r["longitude"])
            return (la, la, lo, lo)
        return None
    return b


def box_dist(la, lo, box):
    """点到边界框最近距离 (km); 框跨 180° 经线时按两段处理。返回 (距离, 框对角线 km)。"""
    s, n, w, e = box
    diag = hav_km(s, w, n, e) if w <= e else hav_km(s, w, n, e + 360)
    cl = min(max(la, s), n)
    if w <= e:
        cn = min(max(lo, w), e)
    else:   # 跨 180°
        cn = lo if (lo >= w or lo <= e) else (w if abs(lo - w) < abs(lo - e) else e)
    return hav_km(la, lo, cl, cn), diag


def classify(r):
    if sv(r.get("typeStatus")) or r.get("dist_type_locality") == "Yes":
        return "type locality"
    if pd.isna(r["dist_km"]):
        return "no geometry"
    if r["box_diag_km"] > COARSE_KM and r["dist_km"] <= REGIONAL_KM:
        return "coarse region"          # 大海区且模式产地在其内/附近: 不判远近; 离得远仍按距离判

    if r["dist_km"] <= NEAR_KM:
        return "near"
    return "regional" if r["dist_km"] <= REGIONAL_KM else "distant"


def main(taxon):
    out = data_dir(taxon, "worms")
    names = read_tsv(out / "names.tsv")
    dist = read_tsv(out / "distributions.tsv")
    coords = read_tsv(out / "coordinates.tsv")
    nm = names.set_index("aphia_id")
    valid = names[(names.aphia_id == names.valid_aphia_id) & names["rank"].isin(["Species", "Subspecies"])]
    vid = dist.aphia_id.map(lambda a: nm.valid_aphia_id.get(a, a))
    dist = dist.assign(recorded_as=dist.aphia_id.map(lambda a: nm.scientific_name.get(a, "")),
                       valid_aphia_id=vid, valid_name=vid.map(lambda a: nm.scientific_name.get(a, "")))
    dist = dist[dist.valid_aphia_id.isin(valid.aphia_id)]
    mrg = [(re.search(r"mrgid/(\d+)", sv(u)) or [None, ""])[1] for u in dist.locationID]
    ids = sorted({m for m in mrg if m})
    boxes = dict(zip(ids, pmap(mr_box, ids)))
    cc = coords.set_index("aphia_id")
    rows = []
    for (_, r), m in zip(dist.iterrows(), mrg):
        a = r["valid_aphia_id"]
        la, lo = (sv(cc.coord_lat.get(a)), sv(cc.coord_lon.get(a))) if a in cc.index else ("", "")
        d = diag = float("nan")
        box = boxes.get(m)
        if sv(r.get("decimalLatitude")) and sv(r.get("decimalLongitude")):
            box = (float(r["decimalLatitude"]),) * 2 + (float(r["decimalLongitude"]),) * 2
        if box and la and lo:
            d, diag = box_dist(float(la), float(lo), box)
        rows.append({**r.to_dict(), "mrgid": m or "", "tl_lat": la or "", "tl_lon": lo or "",
                     "tl_precision": cc.coord_precision.get(a, "") if a in cc.index else "",
                     "dist_km": round(d) if d == d else float("nan"), "box_diag_km": round(diag) if diag == diag else float("nan")})
    chk = pd.DataFrame(rows)
    chk["category"] = chk.apply(classify, axis=1)
    cols = ["valid_aphia_id", "valid_name", "recorded_as", "locality", "category", "dist_km", "box_diag_km", "recordStatus",
            "qualityStatus", "establishmentMeans", "dist_source", "dist_note", "tl_lat", "tl_lon", "tl_precision", "mrgid",
            "dist_url"]
    chk = chk[[c for c in cols if c in chk] + [c for c in chk if c not in cols]].sort_values(["valid_name", "dist_km"])
    write_tsv(chk, out / "distribution_check.tsv")

    sp = []
    for _, v in valid.iterrows():
        g = chk[chk.valid_aphia_id == v.aphia_id]
        nt = g[g.category != "type locality"]
        ok = nt[~nt.recordStatus.fillna("").isin(["doubtful", "inaccurate"])]
        far = ok[ok.category == "distant"]
        located = v.aphia_id in cc.index and sv(cc.coord_lat.get(v.aphia_id)) != ""
        rough = located and sv(cc.coord_basis.get(v.aphia_id)) in ROUGH_BASIS
        if not located:
            verdict = "TL not located"
        elif rough:
            verdict = "TL rough (OD title)"      # 模式产地坐标只是国家 EEZ 中心, 距离仅供参考, 不判远距
        elif len(far):
            verdict = "distant records"
        elif (ok.category == "regional").any():
            verdict = "regional only"
        elif len(ok):
            verdict = "near TL only"
        else:
            verdict = "TL record only"
        sp.append({"aphia_id": v.aphia_id, "valid_name": v.scientific_name, "authority": v.authority, "status": v.status,
                   "verdict": verdict, "n_records": len(g), "n_non_type": len(nt),
                   "n_distant": len(far), "max_km": nt.dist_km.max() if len(nt) else float("nan"),
                   "n_doubtful_inaccurate": int(nt.recordStatus.isin(["doubtful", "inaccurate"]).sum()),
                   "distant_localities": " | ".join(f"{x.locality} ({int(x.dist_km)} km)" for x in far.itertuples()),
                   "distant_sources": " | ".join(sorted({str(s) for s in far.dist_source.dropna()})),
                   "recorded_as_synonyms": " | ".join(sorted({x for x in g.recorded_as if x != v.scientific_name})),
                   "tl_precision": cc.coord_precision.get(v.aphia_id, "") if v.aphia_id in cc.index else "",
                   "tl_basis": sv(cc.coord_basis.get(v.aphia_id)) if v.aphia_id in cc.index else ""})
    sp = pd.DataFrame(sp).sort_values(["verdict", "n_distant", "max_km"], ascending=[True, False, False])
    write_tsv(sp, out / "distribution_species.tsv")
    vc = sp[sp.status == "accepted"].verdict.value_counts().to_dict()
    summary("21_distribution_check", [
        f"{len(chk)} records on {chk.valid_aphia_id.nunique()} valid species; categories {chk.category.value_counts().to_dict()}",
        f"accepted species verdicts ({int((sp.status == 'accepted').sum())}; other statuses kept in file): {vc}",
        f"-> {out / 'distribution_check.tsv'} ; {out / 'distribution_species.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
