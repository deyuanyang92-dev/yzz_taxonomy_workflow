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
  AUTH_OD_YEAR    命名人年份与原始文献年份不同 (缓存过期 -> --refresh 重跑, 或 WoRMS 内部不一致)
  TL_FROM_TITLE   模式产地文字与原始文献题目中的地名相同, 可能按题目概括 (须查原文)
  TL_OCEAN_ONLY   模式产地只有大洋名, 坐标为大洋中心点 (须查原文)
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
    # R2 命名人年份 vs 原始文献年份 (缓存过期或 WoRMS 内部不一致; 如 O. peresi 名称 1965, 原始文献 1966)
    if len(od):
        odr = {r["aphia_id"]: r for r in od.to_dict("records")}
        for r in sp[sp.is_valid == "Y"].to_dict("records"):
            o = odr.get(r["aphia_id"], {})
            yrs = {y.strip() for y in str(o.get("od_year", "")).split("||") if y.strip()}
            if r["year"] and yrs and not any(r["year"] in y for y in yrs):   # "1988 [1987]" 含 1988 不报
                add(r, "AUTH_OD_YEAR", f"authority year {r['year']} but original description year {'/'.join(sorted(yrs))} "
                                       "- WoRMS record may have changed (rerun with --refresh) or verify")
    # R3 模式产地文字出现在原始文献题目里 -> 可能按题目概括 (O. profunda: 'off New England' <- '...off New England to Bermuda...')
    # R6 模式产地只有大洋级 -> 坐标是大洋中心点, 须查原文
    OCEANS = {"atlantic ocean", "pacific ocean", "indian ocean", "arctic ocean", "southern ocean", "north atlantic ocean",
              "south atlantic ocean", "north pacific ocean", "south pacific ocean"}
    if len(t):
        title = {r["aphia_id"]: str(r.get("od_title", "")).lower() for r in od.to_dict("records")} if len(od) else {}
        tl = dict(zip(t.aphia_id, t.type_locality_text))
        for r in sp[sp.aphia_id.isin(tl)].to_dict("records"):
            text = tl[r["aphia_id"]]
            parts = [p.strip().rstrip(".") for p in text.split(",") if p.strip()]
            core = [p for p in parts if p.lower() not in OCEANS]
            ttl = title.get(r["aphia_id"], "")
            hit = [p for p in core if len(p.split()) >= 2 and p.lower() in ttl]
            if hit and all(p.lower() in ttl for p in core):   # 模式产地没有比题目更具体的地名才报 (Burwood Beach 等不报)
                add(r, "TL_FROM_TITLE", f"type locality '{text[:80]}' repeats the original-description title ('{hit[0]}') "
                                        "- may be taken from the title, verify against the original text")
            if parts and all(p.lower() in OCEANS for p in parts):
                add(r, "TL_OCEAN_ONLY", f"type locality only '{text[:60]}' - ocean centroid coordinate is misleading; check the original description")
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
