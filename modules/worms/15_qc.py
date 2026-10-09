"""15 质量检查 (转换层): WoRMS 数据中需要人工核对的问题 -> qc.tsv

输入: names.tsv, original_descriptions.tsv, types.tsv, localities.tsv, specimens.tsv (存在即用)
输出: 02_原始数据/worms/qc.tsv  每行 = 一个名称的一个问题
检查项:
  ENV_FLAG        WoRMS 标淡水/陆地, 但模式产地在海里或水深 >200 m (多为 WoRMS 录入错误)
  ORPHAN_SPECIES  WoRMS 'accepted' 种挂在非有效属下 (编目不一致)
  NO_ORIGINAL_DESC 有效种无原始文献
  LOW_LOCALITY    地名标准化把握低
  NO_VALID_NAME   非有效名没有指向有效名 (nomen nudum/dubium 等)
  COORD_ON_LAND   近似坐标 (地名/区域中心点) 落在陆地上 (Natural Earth 1:50m 陆地; 岸边点可能因分辨率误报)
  COORD_LOW       模式产地坐标只来自低可信度地理编码 (州级或水体中心点), 需核对或在 coordinates_override.tsv 中修正
用法: python3 15_qc.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv


def main(taxon):
    out = data_dir(taxon, "worms")
    n = read_tsv(out / "names.tsv")
    od = read_tsv(out / "original_descriptions.tsv", required=False)
    t = read_tsv(out / "types.tsv", required=False)
    loc = read_tsv(out / "localities.tsv", required=False)
    s = read_tsv(out / "specimens.tsv", required=False)
    q = []
    add = lambda r, check, detail: q.append({"aphia_id": r["aphia_id"], "scientific_name": r["scientific_name"],
                                             "authority": r["authority"], "status": r["status"], "check": check, "detail": detail})
    sp = n[n["rank"].isin(["Species", "Subspecies"])]
    acc_gen = set(n[(n["rank"] == "Genus") & (n.is_valid == "Y")].scientific_name)

    deep = {}
    if len(t):
        deep.update({a: float(v) for a, v in zip(t.aphia_id, t.type_depth_max_m) if v})
    if len(s):
        for a, v in zip(s.aphia_id, s.depth_max_m):
            if v:
                deep[a] = max(deep.get(a, 0), float(v))
    sea = set(loc[loc.region.str.contains("Ocean|Sea|Gulf|Bight|Strait|Bay", case=False) | (loc.water_body != "")].aphia_id) if len(loc) else set()
    for r in sp.to_dict("records"):
        if r["freshwater"] == "1" or r["terrestrial"] == "1":
            marine = r["aphia_id"] in sea or deep.get(r["aphia_id"], 0) > 200
            add(r, "ENV_FLAG", ("WoRMS flags freshwater/terrestrial but type locality is marine or >200 m deep - likely WoRMS data error"
                                if marine else "WoRMS flags freshwater/terrestrial - verify"))
        if r["is_valid"] == "Y" and r["rank"] == "Species" and acc_gen and r["genus"] not in acc_gen:
            add(r, "ORPHAN_SPECIES", f"accepted in WoRMS but placed in non-accepted genus {r['genus']}")
        if r["is_valid"] == "N" and not r["valid_name"]:
            add(r, "NO_VALID_NAME", f"{r['status']}; no accepted name in WoRMS")
    if len(od):
        odm = dict(zip(od.aphia_id, od.od_citation))
        for r in sp[(sp.is_valid == "Y") & (sp["rank"] == "Species")].to_dict("records"):
            if not odm.get(r["aphia_id"]):
                add(r, "NO_ORIGINAL_DESC", "no 'original description' source on this name or its original combination")
    if len(loc):
        low = set(loc[loc.confidence == "Low"].aphia_id)
        for r in sp[sp.aphia_id.isin(low)].to_dict("records"):
            add(r, "LOW_LOCALITY", "locality normalisation confidence Low - check manually")
    co = read_tsv(out / "coordinates.tsv", required=False)
    if len(co):
        low = dict(zip(co[co.coord_confidence == "Low"].aphia_id, co[co.coord_confidence == "Low"].coord_detail))
        for r in sp[sp.aphia_id.isin(low)].to_dict("records"):
            add(r, "COORD_LOW", f"low-confidence coordinate: {low[r['aphia_id']][:150]}")
    if len(co):
        try:
            import cartopy.io.shapereader as shpreader
            from shapely.geometry import Point
            from shapely.ops import unary_union
            from shapely.prepared import prep
            land = prep(unary_union(list(shpreader.Reader(shpreader.natural_earth("50m", "physical", "land")).geometries())))
            ap = co[(co.coord_lat != "") & (co.coord_lon != "") & co.coord_precision.str.startswith("approximate")]
            onland = {a: d for a, la, lo, d in zip(ap.aphia_id, ap.coord_lat, ap.coord_lon, ap.coord_detail)
                      if land.contains(Point(float(lo), float(la)))}
            for r in sp[sp.aphia_id.isin(onland)].to_dict("records"):
                add(r, "COORD_ON_LAND", f"approximate coordinate on land: {onland[r['aphia_id']][:140]}")
        except Exception as e:
            print(f"   (land check skipped: {e})")
    qc = pd.DataFrame(q, columns=["aphia_id", "scientific_name", "authority", "status", "check", "detail"])
    write_tsv(qc, out / "qc.tsv")
    summary("15_qc", [f"{len(qc)} issues: " + "; ".join(f"{k} {v}" for k, v in qc.check.value_counts().items()), f"-> {out / 'qc.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
