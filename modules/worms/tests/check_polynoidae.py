"""worms 模块回归检查 (金标准 = 用户指出过的问题; 每次改脚本后必须全部通过)

用法: python3 modules/worms/tests/check_polynoidae.py      (需先跑过 yzz.py worms all Polynoidae 与 20_region_subset)
新增用户纠错时: 在 CHECKS 末尾加一条, 注明日期与来源.
"""
import glob, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "projects/Polynoidae/02_原始数据/worms"
r = lambda f: pd.read_csv(D / f, sep="\t", dtype=str, keep_default_na=False)
n, c, s, o, t = r("names.tsv"), r("coordinates.tsv"), r("specimens.tsv"), r("original_descriptions.tsv"), r("types.tsv")
aid = lambda nm: n[n.scientific_name == nm].aphia_id.iloc[0]
row = lambda df, nm: df[df.aphia_id == aid(nm)].iloc[0]
china = sorted(glob.glob(str(ROOT / "projects/Polynoidae/04_处理数据/worms/Polynoidae_china_20*.xlsx")))[-1]
A = pd.read_excel(china, sheet_name="A_type_locality", dtype=str)
B = pd.read_excel(china, sheet_name="B_candidates", dtype=str)


def near(nm, lat, lon, tol):
    x = row(c, nm)
    return x.coord_lat != "" and abs(float(x.coord_lat) - lat) <= tol and abs(float(x.coord_lon) - lon) <= tol


def on_land(lat, lon):
    import cartopy.io.shapereader as shp
    from shapely.geometry import Point
    from shapely.ops import unary_union
    land = unary_union(list(shp.Reader(shp.natural_earth("50m", "physical", "land")).geometries()))
    return land.contains(Point(float(lon), float(lat)))


CHECKS = [
    # (说明, 函数)  -- 2026-10-08 用户纠错
    ("原始文献不是 WoRMS citation: Admetella longilamella OD = Kupriyanova et al. 2026, 本种页码 160-163",
     lambda: "Kupriyanova" in row(o, "Admetella longilamella").od_citation and "160-163" in row(o, "Admetella longilamella").od_pages_for_taxon),
    ("OD 结构化: DOI 与 link 分开", lambda: row(o, "Admetella longilamella").od_doi_url.startswith("https://doi.org/10.3853/")
     and "journals.australian.museum" in row(o, "Admetella longilamella").od_link),
    ("转属名 OD 回退原始组合: Harmothoe torbeni -> Lagisca torbeni (Kirkegaard 1995)",
     lambda: "Kirkegaard" in row(o, "Harmothoe torbeni").od_citation),
    ("标本全量: Polynoidae 485 条", lambda: len(s) == 485),
    ("Nu aakhu 标本: IA TYPE 1836, 4498 m, 2015-04-07, Note 两行",
     lambda: (lambda x: x.catalog_no == "IA TYPE 1836" and x.depth_min_m.startswith("4498") and x["worms: Begindate"] == "2015-04-07"
              and "Station no: 117" in x["worms: Note"])(s[s.aphia_id == aid("Nu aakhu")].iloc[0])),
    ("Eulagisca uschakovi 模式产地记录 = 'Antarctic Ocean, off MacRobertson Land', 坐标在 Mac. Robertson Land 附近",
     lambda: "MacRobertson" in row(t, "Eulagisca uschakovi").type_locality_text and near("Eulagisca uschakovi", -69.5, 65, 4)),
    ("Benhamipolynoe antipathicola (New Zealand) 有模糊坐标且在新西兰周边海上",
     lambda: near("Benhamipolynoe antipathicola", -41, 174, 12) and not on_land(row(c, "Benhamipolynoe antipathicola").coord_lat, row(c, "Benhamipolynoe antipathicola").coord_lon)),
    ("没有国家级陆地中心点", lambda: not c.coord_detail.str.contains(r"\((?:Nation|Country|Sovereign)", regex=True).any()),
    ("Parahalosydna chinensis ('China') 坐标在海上", lambda: not on_land(row(c, "Parahalosydna chinensis").coord_lat, row(c, "Parahalosydna chinensis").coord_lon)),
    ("West Indies 不被算到东半球 (MR 东西界填反)", lambda: float(row(c, "Hermenia verruculosa").coord_lon) < -50),
    ("厦门多鳞虫 4 种 (species_lists_add_CG_comments.xlsx) 全部在 A 或 B",
     lambda: all(((A.scientific_name == x).any() or (B.scientific_name == x).any())
                 for x in ["Lepidasthenia ocellata", "Lepidonotus minutus", "Parahalosydna chinensis", "Parahalosydnopsis hartmanae"])),
    ("Matsushima (日本) 不因 'Matsu' 进入中国名单", lambda: not (A.scientific_name == "Lepidonotus dentatus").any()),
    ("Treadwell 1926 'Fiji, Samoa, China and Japan' 两种进入 B", lambda: all((B.scientific_name == x).any() for x in ["Harmothoe villosa", "Halosydna oculata"])),
    ("WoRMS freshwater 误标 3 个深海种在 QC", lambda: (r("qc.tsv").check == "ENV_FLAG").sum() >= 3),
    # 2026-10-08 陆地检查发现的 bug
    ("Nominatim 不匹配酒店/商店 ('Best Western Hotel', '221 West Coast')",
     lambda: not c.coord_detail.str.contains(r"Hotel|Best Western|West Coast, 72", regex=True).any()),
    ("不用洲/淡水生态区/TDWG 陆地分区", lambda: not c.coord_detail.str.contains(r"\((?:Continent|Freshwater|TDWG)", regex=True).any()),
    ("近似坐标不在陆地 (已移到最近海上)", lambda: (r("qc.tsv").check == "COORD_ON_LAND").sum() == 0),
    ("经纬度成对 (WoRMS 有只填纬度的记录)", lambda: ((c.coord_lat != "") == (c.coord_lon != "")).all()),
    ("'Pacific Ocean' 的模糊坐标不落在东海/南海 (代表点算法)", lambda: not (lambda x: 3 < float(x.coord_lat) < 41 and 105 < float(x.coord_lon) < 131)(row(c, "Bathyvitiazia pallida"))),
    ("加州/婆罗洲/太平洋等不进入中国 A 表", lambda: not A.scientific_name.isin(["Eucranta anoculata", "Polynoe kampeni", "Lepidonotopodium plicata", "Bathyvitiazia pallida"]).any()),
    ("非模式标本 (Nontype) 不用作模式产地坐标", lambda: not c.coord_detail.str.contains(r"^Nontype", regex=True).any()),
    ("只有国家名的模式产地也有 EEZ 坐标 (China / France / Ivory Coast / Morocco / Argentina)",
     lambda: all(row(c, x).coord_lat != "" for x in ["Halosydna nebulosa", "Harmothoe pentactae", "Harmothoe pokoui", "Polynoe microphthalma", "Eucranta notialis"])),
    ("有 WoRMS 地理记录却无坐标的, 只能是确实无法定位的 (Unknown / 原作者未知产地 / 'South Seas')",
     lambda: set(pd.merge(c[c.coord_lat == ""], t[(t.type_locality_text != "") | (t.specimen_geounits != "")], on="aphia_id").scientific_name)
             <= {"Thormora jukesii", "Lepidonotus (Thormora) jukesi", "Thormora jukesi", "Macellicephala australis",
                 "Harmothoe setosissima", "Laenilla setosissima", "Polynoe setosissima"}),
]

fail = 0
for desc, fn in CHECKS:
    try:
        ok = bool(fn())
    except Exception as e:
        ok, desc = False, f"{desc}  [error: {e}]"
    fail += not ok
    print(("PASS " if ok else "FAIL ") + desc)
print(f"\n{len(CHECKS) - fail}/{len(CHECKS)} passed")
sys.exit(1 if fail else 0)
