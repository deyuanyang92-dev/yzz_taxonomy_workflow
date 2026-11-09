"""14 坐标 (转换层): 每个种级名称一个"最佳模式产地坐标" + 来源/精度/可信度 -> coordinates.tsv

思路沿用 codex/WORMS 坐标决策引擎 (证据分级, 不覆盖出处) 与臭海蛹 01_build_type_localities.py
(original = 原始资料给出的坐标; approximate = 按地名定位的中心点, 作图时应区别显示).

优先级 (取第一个可用):
  1 manual_override              人工修正表 02_原始数据/worms/coordinates_override.tsv (aphia_id, lat, lon, basis)   original/High
  2 worms_specimen               WoRMS 标本页坐标 (本名称或其原始组合; Holotype>Lectotype>Neotype>Syntype>Paratype)  original/High
  3 type_text_coordinates        模式产地/模式数据文本中写明的坐标 (严格解析: 度分秒须带 N/S/E/W; 十进制须成对)     original/High
  4 worms_type_distribution      WoRMS 模式分布记录坐标 (来自 Marine Regions 地名库, 为地名中心点)                  approximate/Medium
  5 geocode_locality             标准化地名 (13) -> Nominatim 结构化查询, 限定国家 ISO                              approximate/Medium|Low
  6 geocode_water_body           标准化水体名 (13) -> Marine Regions 地名库中心点                                  approximate/Low
  7 geocode_country_eez          国家 -> 该国 EEZ 中心点 (落在海里; 不用陆上国家中心)                                approximate/Low
  8 specimen_geounit(_eez)       标本 Geounit (WoRMS 地名) -> EEZ 或该地名中心点                                    approximate/Low
  (7 之前) worms_place_name     WoRMS 地名记录各段在 Marine Regions 精确匹配 (如 'Philippine Exclusive Economic Zone')  approximate/Low
  10 worms_type_distribution_area  模式分布记录自带 MRGID 的区域代表点                                          approximate/Low
  10b worms_type_distribution_area  模式分布记录无 MRGID (网页补抓) 时按地名匹配                               approximate/Low
  10c od_text_*                 compilation 05 原始描述原文的模式产地 (WoRMS 无时用; 原文写明经纬度时优先于 WoRMS 近似点)
                                 od_text_coordinates original/High; od_text_locality / od_text_country_eez approximate/Low
  11 od_title_country_eez        WoRMS 无任何模式产地信息时: 原始描述题目中的国名 -> 该国 EEZ 中心点 (很粗)       approximate/Very low
  原则: 优先 WoRMS 模式产地信息; 不用非模式分布记录. 11 级仅作粗略参考, 21 步不据此判远距 (2026-11-09 用户要求粗略给出).
  9 geocode_ocean_region         大洋/海区 -> Marine Regions 海区中心点                                             approximate/Low
  中心点一律用边界框自算 (跨 180° 经线正确; Marine Regions 自带中心点在此类区域会错, 如新西兰 EEZ 给出 71.7°E).
  worms_only_* = 只用 WoRMS 信息得到的坐标; od_* = 原始描述原文定位 (compilation 05).
  od_country_match = WoRMS 坐标是否在原文国家 EEZ 框 (外扩 5°) 内 (N 须核实).
  od_vs_coord_km = 原文 (地名/经纬度级) 与 WoRMS 坐标相距 (km); 汇总与判定见 22_tl_verify (如 M. teretiuscula: Schmarda 原文 Ceylon, WoRMS Zanzibar).
  coord_uncertainty_km = Marine Regions precision 或 Nominatim 边界框半对角线, 表示坐标的模糊程度.
  只有完全没有地理信息时才留空。
有效名自身无证据时, 回退到原始组合 (同一模式); 不使用次异名的证据 (不同模式)。
缓存: cache/geocode_cache.json (Nominatim 1 次/秒, 重跑不重复请求).
用法: python3 14_coordinates.py <Taxon>
"""
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import CACHE, data_dir, read_tsv, summary, write_tsv

UA = "yzz-taxonomy-workflow/0.1 (academic research)"
GEO = CACHE / "geocode_cache.json"
TYPE_RANK = ["holotype", "lectotype", "neotype", "syntype", "cotype", "paratype", "paralectotype", "allotype", "topotype"]
OCEAN_RE = re.compile(r"^\s*(the\s+)?((north|south|east|west|central|northern|southern|eastern|western|tropical|equatorial)[\s-]*)*"
                      r"(pacific|atlantic|indian|arctic|southern|antarctic)(\s+ocean)?\s*$", re.I)
COARSE_RE = re.compile(r"\b(province|basin|realm|ecoregion|abyssal|bathyal|eez|exclusive economic zone)\b", re.I)
PLACE_CATS = {"place", "natural", "boundary", "waterway", "water"}   # 只接受地名类; 不接受酒店/商店/道路等 (曾匹配到 'Best Western Hotel')


def land_type(pt):
    """Marine Regions 中纯陆地/淡水类区域 (洲、淡水生态区、TDWG 陆地分区) -> 不用作海洋物种坐标."""
    pt = pt or ""
    return pt in ("Continent",) or "Freshwater" in pt or pt.startswith("TDWG") or "Terrestrial" in pt

# ---------- 严格坐标解析 ----------
# 度可带小数并可带负号 ('-2.9°S, 151.1°E'，M. zanolae 2026-11-09 曾被读成 9°S 1°E)；符号由半球字母决定
DMS = r"(?<![\d.,])-?(\d{1,3}(?:[.,]\d+)?)\s*[°º˚]\s*(?:(\d{1,2}(?:[.,]\d+)?)\s*['′’`]\s*)?(?:(\d{1,2}(?:[.,]\d+)?)\s*[\"″”]\s*)?"


def _dms(deg, mi, se, hemi):
    v = float(deg.replace(",", ".")) + float((mi or "0").replace(",", ".")) / 60 + float((se or "0").replace(",", ".")) / 3600
    return -v if hemi in "SWsw" else v


def text_coords(text):
    """返回 (lat, lon, 文本片段) 或 None. 度分秒必须带半球字母; 十进制必须成对且≥2位小数."""
    t = text or ""
    lat = re.search(DMS + r"\s*([NS])\b", t)
    lon = re.search(DMS + r"\s*([EW])\b", t)
    if lat and lon:
        a, b = _dms(*lat.groups()), _dms(*lon.groups())
        if abs(a) <= 90 and abs(b) <= 180:
            return round(a, 5), round(b, 5), f"{lat.group(0)} {lon.group(0)}"
    m = re.search(r"(-?\d{1,2}\.\d{2,})\s*[,;/]\s*(-?\d{1,3}\.\d{2,})", t)
    if m and abs(float(m.group(1))) <= 90 and abs(float(m.group(2))) <= 180:
        return float(m.group(1)), float(m.group(2)), m.group(0)
    return None


def countries_in(text):
    """原文中出现的全部国家 ISO2 (集合); 不排除 'of X' (题目 'Eunicemorpha of Argentina, Chile...' 要算进去)."""
    try:
        import pycountry
    except ImportError:
        return set()
    t = text if isinstance(text, str) else ""
    return {c.alpha_2 for c in pycountry.countries
            for nm in {c.name, getattr(c, "common_name", c.name)} if re.search(r"\b" + re.escape(nm) + r"\b", t)}


# 国名作水体名的一部分时不算国名: 'Gulf of Mexico'、'Sea of Japan'、'South China Sea' (2026-11-09 马来西亚种被判成中国);
# 'south of China'、'coast of Brazil' 仍算
WATER_BEFORE = re.compile(r"\b(gulf|sea|bay|strait|straits|ocean|golfe|golfo|mer|mar)\s+(of\s+|de\s+|du\s+)?(the\s+)?$", re.I)
WATER_AFTER = re.compile(r"^\s+(sea|ocean|basin|strait|current|trench|rise|shelf)\b", re.I)


# 模糊匹配不得用的词: 'West Indies' 曾被认成 India, M. brevitentaculata 定到德里 (2026-11-09 原文复查发现)
NOT_COUNTRY = {"Indies", "Antilles", "Indiens", "Guinea"}


def _water_part(t, m):
    return bool(WATER_BEFORE.search(t[: m.start()]) or WATER_AFTER.search(t[m.end():]))


# 老文献 (19 世纪德/法/拉丁文原始描述) 中的国名旧称/外语名 -> ISO2 (2026-11-09: Schmarda 1861 'Ceylon', 'Jamaica')
COUNTRY_ALIASES = {"Ceylon": "LK", "Ceylan": "LK", "Siam": "TH", "Burma": "MM", "Birma": "MM", "Persia": "IR",
                   "Chili": "CL", "Brasilien": "BR", "Brésil": "BR", "Brasil": "BR", "Mexiko": "MX", "Mexique": "MX",
                   "Japon": "JP", "Australien": "AU", "Australie": "AU", "Neuseeland": "NZ", "Nouvelle-Zélande": "NZ",
                   "Philippinen": "PH", "Ägypten": "EG", "Egypte": "EG", "Indien": "IN", "Inde": "IN", "Peru": "PE",
                   "Panamá": "PA", "Venezuela": "VE", "Kuba": "CU", "Jamaika": "JM", "Jamaïque": "JM", "Madagaskar": "MG"}
# 岛屿/地区旧称 -> (ISO2, 查询地名): 不是国名, 但能定国家并作 Nominatim 查询
PLACE_ALIASES = {"Madeira": ("PT", "Madeira"), "Azoren": ("PT", "Azores"), "Azores": ("PT", "Azores"),
                 "Zanzibar": ("TZ", "Zanzibar"), "Sansibar": ("TZ", "Zanzibar"), "Natal": ("ZA", "KwaZulu-Natal"),
                 "Cape of Good Hope": ("ZA", "Cape of Good Hope"), "Cap der guten Hoffnung": ("ZA", "Cape of Good Hope"),
                 "Kap der guten Hoffnung": ("ZA", "Cape of Good Hope"), "Canarias": ("ES", "Canary Islands"),
                 "Canary Islands": ("ES", "Canary Islands"), "Kanarischen Inseln": ("ES", "Canary Islands"),
                 "Tobago": ("TT", "Tobago"), "Trinidad": ("TT", "Trinidad"), "St. Thomas": ("VI", "Saint Thomas"),
                 "Porto Rico": ("PR", "Puerto Rico"), "Tahiti": ("PF", "Tahiti"), "Colombo": ("LK", "Colombo"), "Sri Lanka": ("LK", "Sri Lanka"), "Formosa Island": ("TW", "Taiwan")}


def _country_names():
    import pycountry
    out = {}
    for c in pycountry.countries:
        for nm in {c.name, getattr(c, "common_name", c.name)}:
            out[nm] = (c.alpha_2, nm, None)
    for a, iso in COUNTRY_ALIASES.items():
        out.setdefault(a, (iso, pycountry.countries.get(alpha_2=iso).name, None))
    for a, (iso, q) in PLACE_ALIASES.items():
        out[a] = (iso, pycountry.countries.get(alpha_2=iso).name, q)
    return out


def infer_country(text):
    """原文 -> (国名, ISO2, [Nominatim 查询串...])；找不到返回 ('', '', [])。

    最先出现的国名优先；'Gulf of Mexico' / 'Sea of Japan' 这类水体名不算国名。
    也认旧称/外语名 (COUNTRY_ALIASES: Ceylon, Chili...) 和岛屿旧称 (PLACE_ALIASES: Madeira, Zanzibar...);
    都找不到时容 OCR 错 1 字 (Schmarda 1861 OCR 'Cevlon' = Ceylon): 首字母大写、>= 6 字母的词与名称相似度 >= 0.83
    ('Colombo' 与 Colombia 为 0.80, 不算); 形容词 (-ian/-ean/-ese/-ish/-ic) 不参与。
    查询串: 国名之后的地名段由细到粗 + 国名 ('Sao Francisco Beach, Sao Sebastio, Sao Paulo, Brazil')，
            以及国名之前紧邻的一段 + 国名 ('Lima, Peru')；岛屿旧称先查 '岛名, 国名'。"""
    try:
        names = _country_names()
    except ImportError:
        return "", "", []
    t = text if isinstance(text, str) else ""          # NaN (空单元格) 是 float 且为真 —— 曾让整个种的地理编码失败
    best = None
    for alias, (iso_, off, place) in names.items():
        for m in re.finditer(r"\b" + re.escape(alias) + r"\b", t):
            if _water_part(t, m):
                continue
            if best is None or m.start() < best[2].start():
                best = (off, iso_, m, place)
            break
    if not best:                                       # OCR 容错
        import difflib
        for m in re.finditer(r"\b[A-Z][a-zäöüé]{5,}\b", t):
            if _water_part(t, m) or re.search(r"(ian|ean|ese|ish|ic)$", m.group()) or m.group() in NOT_COUNTRY:
                continue                               # 形容词 'West Indian' 不是 India/Indien
            hit = difflib.get_close_matches(m.group(), [a for a in names if len(a) >= 6 and " " not in a], n=1, cutoff=0.83)
            if hit:
                iso_, off, place = names[hit[0]]
                best = (off, iso_, m, place)
                break
    if not best:
        return "", "", []
    nm, iso, m, place = best
    clause_start = max(t.rfind(" or ", 0, m.start()), t.rfind(";", 0, m.start()))
    before = [x.strip() for x in t[clause_start + 1 if clause_start >= 0 else 0: m.start()].split(",") if x.strip()]
    after_txt = re.split(r"\s+or\s+|;", t[m.end():])[0]
    after = [re.sub(r"\(.*?\)", "", x).strip() for x in after_txt.split(",")]
    after = [x for x in after if x and not re.search(r"\d", x) and re.search(r"[A-Za-z]{3,}", x)]   # 丢掉 '.'、'S c li' 等 OCR 碎片
    qs = []
    rev = list(reversed(after))
    for k in range(len(rev)):                                     # 由细到粗: 拼写错的最细地名不至于整条失败
        qs.append(", ".join(rev[k:] + [nm]))
    if before and not OCEAN_RE.match(before[-1]) and len(before[-1].split()) <= 4:   # 长短语 (德文整句) 不作查询
        qs.append(f"{before[-1]}, {nm}")
    if place:
        qs.insert(0, f"{place}, {nm}")
    return nm, iso, qs


# ---------- 中心点与不确定度 ----------
def _hav_km(la1, lo1, la2, lo2):
    import math
    p = math.pi / 180
    a = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1, a)))


def bbox_centre(s_, n_, w_, e_):
    """边界框中心; 跨 180° 经线 (w > e) 时正确处理. 返回 (lat, lon, 半对角线 km)."""
    s_, n_, w_, e_ = map(float, (s_, n_, w_, e_))
    if w_ > e_:
        # 两种可能: 真跨 180° (如新西兰 EEZ 160.6 -> -171.2) 或 Marine Regions 把东西界填反 (如 West Indies -59.3 / -88.5);
        # 取跨度小的解释 (跨 180°: e+360-w; 填反: w-e)
        if (e_ + 360 - w_) <= (w_ - e_):
            e_ += 360
        else:
            w_, e_ = e_, w_
    lat, lon = (s_ + n_) / 2, (w_ + e_) / 2
    lon = lon - 360 if lon > 180 else lon
    return round(lat, 4), round(lon, 4), round(_hav_km(s_, w_, n_, e_) / 2)


PREFIX_RE = re.compile(r"^\s*((off|near|nr\.?|around|at|in|from|vicinity of|between|outside|inside|"
                       r"(north|south|east|west|ne|nw|se|sw|northeast|northwest|southeast|southwest)(ern)?\s+(of|part of|coast of)?)\s+)+", re.I)


def clean_place(x):
    """'off Mac. Robertson Land (station 5)' -> 'Mac. Robertson Land'"""
    x = re.sub(r"\(.*?\)", "", x or "")
    x = PREFIX_RE.sub("", x).strip(" ,;.")
    return re.sub(r"\s+", " ", x)


def mr_point(res):
    """Marine Regions 记录 -> (lat, lon, 不确定度 km). 有边界框则自算中心 (MR 自带中心点在跨 180° 区域会错)."""
    span = None
    if res.get("minLongitude") is not None:
        w_, e_ = float(res["minLongitude"]), float(res["maxLongitude"])
        span = min(e_ + 360 - w_, w_ - e_) if w_ > e_ else (e_ - w_)
    if res.get("minLatitude") is not None and span is not None and span < 350 or res.get("latitude") is None and span is not None:
        lat, lon, unc = bbox_centre(res["minLatitude"], res["maxLatitude"], res["minLongitude"], res["maxLongitude"])
        return lat, lon, round(res["precision"] / 1000) if res.get("precision") else unc
    return res["latitude"], res["longitude"], round(res["precision"] / 1000) if res.get("precision") else ""


GEO_REF = {}


def area_point(res):
    """区域记录 -> (lat, lon, 不确定度 km): 优先多边形内部代表点 (保证在区域内, 如 EEZ 在海上), 否则边界框中心."""
    lat, lon, unc = mr_point(res)
    g = GEO_REF.get("geo")
    if g is not None and res.get("MRGID"):
        p = g.rep_point(res["MRGID"])
        if p:
            return p[0], p[1], unc
    return lat, lon, unc


def nom_unc(res):
    b = res.get("boundingbox")
    return round(_hav_km(float(b[0]), float(b[2]), float(b[1]), float(b[3])) / 2) if b else ""


# ---------- 地理编码 (缓存) ----------
class Geo:
    def __init__(self):
        self.c = json.loads(GEO.read_text()) if GEO.exists() else {}
        self.last, self.n = 0.0, 0

    def _get(self, url, gap):
        wait = gap - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        for i in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40) as r:
                    return json.loads(r.read() or b"null")
            except Exception as e:
                if "404" in str(e) or "204" in str(e):
                    return None
                time.sleep(3 * (i + 1))
        return None

    def cached(self, k, fn):
        if k not in self.c:
            self.c[k] = fn()
            self.n += 1
            if self.n % 20 == 0:
                self.save()
        return self.c[k]

    def nominatim(self, q, iso):
        def run():
            p = {"q": q, "format": "jsonv2", "limit": 5, "accept-language": "en"}
            if iso:
                p["countrycodes"] = iso.lower()
            return self._get("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(p), 1.1) or []
        res = [x for x in (self.cached(f"nom2|{iso}|{q}", run) or []) if x.get("category") in PLACE_CATS]   # 严格: 无地名类结果 = 未找到
        return res[0] if res else None

    def marine_regions(self, name, like=False):
        def run():
            u = (f"https://www.marineregions.org/rest/getGazetteerRecordsByName.json/{urllib.parse.quote(name)}/"
                 f"?like={'true' if like else 'false'}&fuzzy=false")
            return [x for x in (self._get(u, 0.5) or []) if x.get("latitude") is not None or x.get("minLatitude") is not None]
        res = self.cached(f"mr{'~' if like else ''}|{name}", run)
        return res if isinstance(res, list) else ([res] if res else [])

    def eez(self, country, iso=""):
        """国家 -> 该国 EEZ 的 Marine Regions 记录. 查 EEZ 图层 territory1 = 国家名, 失败再按 ISO3 (iso_ter1);
        优先正式 EEZ (排除 Joint regime / Overlapping claim). 不靠猜 EEZ 名称 ('Chinese', 'Ivorian' ...)."""
        def wfs(filt):
            u = ("https://geo.vliz.be/geoserver/MarineRegions/wfs?service=WFS&version=1.0.0&request=GetFeature"
                 "&typeName=MarineRegions:eez&propertyName=mrgid,geoname,territory1,iso_ter1&outputFormat=application/json"
                 "&cql_filter=" + urllib.parse.quote(filt))
            return [f["properties"] for f in ((self._get(u, 0.5) or {}).get("features") or [])]

        def run():
            props = wfs("territory1='" + country.replace("'", "''") + "'") if country else []
            if not props and iso:
                try:
                    import pycountry
                    i3 = pycountry.countries.get(alpha_2=iso.upper()).alpha_3
                    props = wfs(f"iso_ter1='{i3}'")
                except Exception:
                    pass
            props.sort(key=lambda x: (x["geoname"].startswith(("Joint regime", "Overlapping claim")), x["geoname"]))
            return props[0]["mrgid"] if props else None
        mrgid = self.cached(f"eezwfs|{country}|{iso}", run)
        if not mrgid:
            return None
        rec = self.cached(f"mrid|{mrgid}", lambda: self._get(f"https://www.marineregions.org/rest/getGazetteerRecordByMRGID.json/{mrgid}/", 0.5))
        return rec

    def rep_point(self, mrgid):
        """Marine Regions 多边形 -> 一定落在多边形内部的代表点 (lat, lon); 无几何返回 None. 只缓存点."""
        def run():
            info = self._get(f"https://www.marineregions.org/rest/getGazetteerWMSes.json/{mrgid}/", 0.5) or []
            from shapely.geometry import shape
            from shapely.ops import nearest_points, transform, unary_union
            parts = []
            for w in info:   # 一个地名可能由多块多边形组成 (如 Pacific Ocean = 17 个 IHO 分区), 必须全部合并
                url = ("https://geo.vliz.be/geoserver/MarineRegions/wfs?service=WFS&version=1.0.0&request=GetFeature"
                       f"&typeName={w.get('namespace', 'MarineRegions')}:{w['featureType']}"
                       f"&cql_filter={w['featureName']}='{w['value']}'&outputFormat=application/json")
                parts += [shape(f["geometry"]) for f in ((self._get(url, 0.5) or {}).get("features") or []) if f.get("geometry")]
            if not parts:
                return None
            geom = unary_union(parts)
            if (geom.bounds[2] - geom.bounds[0]) > 300:   # 跨 180° 的大区域: 平移到 0-360 再算中心
                geom = transform(lambda x, y, z=None: ([v + 360 if v < 0 else v for v in x], y), geom)
            cen = geom.centroid                              # 中心在区域内就用中心, 否则取区域内离中心最近的点
            pt = cen if geom.contains(cen) else nearest_points(geom, cen)[0]
            lon = pt.x - 360 if pt.x > 180 else pt.x
            return [round(pt.y, 4), round(lon, 4)]
        return self.cached(f"geom3|{mrgid}", run)   # geom3: 全部分区合并后取中心 (geom2 只取第一块分区, 太平洋 -> 东海)

    def save(self):
        GEO.write_text(json.dumps(self.c, ensure_ascii=False))


def snap_to_sea(c):
    """近似坐标落在陆地 (Natural Earth 1:50m) 时, 移到最近海岸外约 5 km; 原中心点保留在 coord_raw_lat/lon, 详情注明.
    原始坐标 (original) 不动 (潮间带/岸边标本坐标本就可能在陆地像元内)."""
    c["coord_raw_lat"], c["coord_raw_lon"] = "", ""
    try:
        import cartopy.io.shapereader as shp
        from shapely import STRtree
        from shapely.geometry import Point
        from shapely.ops import nearest_points, unary_union
        from shapely.prepared import prep
    except Exception as e:
        print(f"   (snap-to-sea skipped: {e})")
        return c
    polys = list(shp.Reader(shp.natural_earth("50m", "physical", "land")).geometries())
    land = prep(unary_union(polys))
    lines = [part.exterior for g in polys for part in getattr(g, "geoms", [g])]   # 只用外轮廓 (内环 = 湖, 不是海)
    tree = STRtree(lines)
    n_ = 0
    for i, r in c.iterrows():
        if not r.coord_lat or not str(r.coord_precision).startswith("approximate"):
            continue
        p = Point(float(r.coord_lon), float(r.coord_lat))
        if not land.contains(p):
            continue
        coast = nearest_points(lines[int(tree.nearest(p))], p)[0]
        dx, dy = coast.x - p.x, coast.y - p.y
        d = (dx * dx + dy * dy) ** 0.5 or 1e-9
        q = None
        for step in (0.05, 0.1, 0.2, 0.4):
            cand = Point(coast.x + dx / d * step, coast.y + dy / d * step)
            if not land.contains(cand):
                q = cand
                break
        if q is None:   # 狭湾/岛屿: 以海岸点为圆心, 16 个方向由近到远找第一个海上点
            import math
            for rad in (0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2):
                for k in range(16):
                    cand = Point(coast.x + rad * math.cos(k * math.pi / 8), coast.y + rad * math.sin(k * math.pi / 8))
                    if not land.contains(cand):
                        q = cand
                        break
                if q is not None:
                    break
        if q is None:
            continue
        c.at[i, "coord_raw_lat"], c.at[i, "coord_raw_lon"] = r.coord_lat, r.coord_lon
        c.at[i, "coord_lat"], c.at[i, "coord_lon"] = f"{q.y:.4f}", f"{q.x:.4f}"
        c.at[i, "coord_detail"] = r.coord_detail + " [centroid on land -> moved to nearest sea, ~5 km offshore]"
        n_ += 1
    print(f"   snap-to-sea: {n_} approximate coordinates moved from land to nearest sea", flush=True)
    return c


def main(taxon):
    out = data_dir(taxon, "worms")
    n = read_tsv(out / "names.tsv")
    t = read_tsv(out / "types.tsv").set_index("aphia_id")
    loc = read_tsv(out / "localities.tsv", required=False)
    loc = loc.set_index("aphia_id") if len(loc) else pd.DataFrame()
    s = read_tsv(out / "specimens.tsv", required=False)
    od = read_tsv(out / "original_descriptions.tsv", required=False)
    od = od.set_index("aphia_id") if len(od) and "od_title" in od else pd.DataFrame()
    # compilation 05: 原始描述原文中的模式产地 (项目/08_知识库/结构化/od_type_locality.tsv), 只用命名年份与文献年份一致的行
    odt_path = out.parents[2] / "08_知识库" / "结构化" / "od_type_locality.tsv"
    odt = {}
    if odt_path.exists():
        x = read_tsv(odt_path)
        x = x[(x.tl_cue != "") & (x.get("od_year_match", "Y") == "Y")]
        rank = {"type_locality": 0, "holotype": 1, "material": 2, "locality_sentence": 3, "work_title": 4}
        x = x.assign(_r=x.tl_cue.map(rank)).sort_values("_r")
        valid_id = dict(zip(n.scientific_name[n.aphia_id == n.valid_aphia_id], n.aphia_id[n.aphia_id == n.valid_aphia_id]))
        for r in x.to_dict("records"):
            a_ = valid_id.get(r["taxon"])
            if a_ and a_ not in odt:
                odt[a_] = r
    ov_path = out / "coordinates_override.tsv"
    ov = read_tsv(ov_path, required=False).set_index("aphia_id") if ov_path.exists() else pd.DataFrame()
    geo = Geo()
    GEO_REF['geo'] = geo

    spec = {}
    if len(s):
        for r in s[s.latitude != ""].to_dict("records"):
            rank = next((i for i, k in enumerate(TYPE_RANK) if k in r["type_status"].lower()), 99)
            if rank == 99 or r["type_status"].strip().lower() in ("nontype", "non-type"):   # 非模式标本不能作模式产地坐标
                continue
            spec.setdefault(r["aphia_id"], []).append((rank, r))

    def evidence(aid):
        """一个 AphiaID 自身的最佳坐标 (不含地理编码)."""
        if aid in ov.index:
            o = ov.loc[aid]
            return o["lat"], o["lon"], "manual_override", "original", "High", o.get("basis", ""), ""
        if aid in spec:
            rank, r = sorted(spec[aid], key=lambda x: x[0])[0]
            return (r["latitude"], r["longitude"], "worms_specimen", "original", "High",
                    f"{r['type_status']} {r['institution']} {r['catalog_no']} ({r['specimen_url']})".strip(), "")
        if aid in t.index:
            tr = t.loc[aid]
            tc = text_coords(" ".join([tr.type_locality_text, tr.type_data_notes, tr.type_material]))
            if tc:
                return tc[0], tc[1], "type_text_coordinates", "original", "High", f"text: {tc[2]}", ""
            first_loc = tr.type_dist_locality.split(";")[0]
            if tr.type_dist_lat and not OCEAN_RE.match(first_loc):
                return (tr.type_dist_lat, tr.type_dist_lon, "worms_type_distribution",
                        "approximate (region centroid)" if COARSE_RE.search(first_loc) else "approximate (place centroid)",
                        "Low" if COARSE_RE.search(first_loc) else "Medium",
                        f"WoRMS type distribution: {tr.type_dist_locality} (MRGID {tr.type_dist_mrgid})", "")
        return None

    sgeo = {}
    if len(s):
        for r in s.to_dict("records"):
            for k in ("worms: verbatimGeounit", "worms: Geounit"):
                if r.get(k):
                    sgeo.setdefault(r["aphia_id"], []).append(r[k])

    NATIONAL = ("Nation", "Country", "Sovereign", "Territory", "Dependency")

    def in_country(x, cbox):
        """地名命中点须落在模式产地所属国家 EEZ 边界框 (外扩 5°) 内; 无国家信息时不限制.
        2026-11-09: 'Lima, Peru' 被 Marine Regions 匹配到葡萄牙 Lima 河 (M. gayi, M. peruviana)."""
        if not cbox:
            return True
        lat, lon, _ = area_point(x)
        s_, n_, w_, e_ = cbox
        lon_ok = (w_ - 5 <= float(lon) <= e_ + 5) if w_ <= e_ else (float(lon) >= w_ - 5 or float(lon) <= e_ + 5)
        return s_ - 5 <= float(lat) <= n_ + 5 and lon_ok

    def country_box(L):
        if L is None or not L["country"]:
            return None
        z = geo.eez(L["country"], L["iso"])
        try:
            return tuple(float(z[k]) for k in ("minLatitude", "maxLatitude", "minLongitude", "maxLongitude")) if z else None
        except (KeyError, TypeError, ValueError):
            return None

    def mr_hit(name, basis, level, detail_prefix, cbox=None):
        for x in geo.marine_regions(name):
            if not in_country(x, cbox):
                continue
            if x.get("placeType") in NATIONAL:            # 国家级记录 = 陆地中心点 -> 改用该国 EEZ
                z = geo.eez(x.get("preferredGazetteerName") or name) or geo.eez(name)
                if z:
                    lat, lon, unc = area_point(z)
                    return (str(lat), str(lon), basis.replace("worms_place_name", "geocode_country_eez"), "approximate (EEZ centroid)", "Low",
                            f"{detail_prefix} '{name}' -> {x.get('placeType')} -> {z.get('preferredGazetteerName')} (MRGID {z.get('MRGID')})", str(unc))
                continue
            if x.get("placeType") not in ("Realm", "Province", "Ecoregion") and not land_type(x.get("placeType")):
                lat, lon, unc = area_point(x)
                return (str(lat), str(lon), basis, f"approximate ({level})", "Low",
                        f"{detail_prefix} '{name}' -> {x.get('preferredGazetteerName')} ({x.get('placeType')}, MRGID {x.get('MRGID')})", str(unc))
        return None

    def geocode(aid):
        """地名 -> 近似坐标, 由细到粗; 越粗可信度越低, coord_uncertainty_km 越大."""
        L = loc.loc[aid] if len(loc) and aid in loc.index else None
        if L is not None and not (L.get("country") if isinstance(L.get("country"), str) else "").strip():
            # 13 步未解析出国家时，从原文找国名 (最先出现者)，并用 '原文开头..国名' 做 Nominatim
            # 2026-11-09: 'Lima, Peru' 无结构化字段 -> Marine Regions 命中葡萄牙 Lima 河
            c, iso, qs = infer_country(L.get("locality_source_text", ""))
            if c:
                L = L.copy()
                L["country"], L["iso"] = c, iso
                for q in qs:
                    res = geo.nominatim(q, iso)
                    rank = int(res.get("place_rank", 30)) if res else 0
                    if res and rank > 8:                      # 州/省级中心点在陆上, 不用; 交给下面的 Marine Regions/EEZ
                        return (res["lat"], res["lon"], "geocode_locality", "approximate (locality)", "Low",
                                f"Nominatim '{q}' (country inferred from text) -> {res.get('display_name', '')[:120]}",
                                str(nom_unc(res)))
        if L is not None:
            parts = [clean_place(L["locality"]), clean_place(L["county_city"]), L["state_province"], L["country"]]   # 去掉 off/western/west coast of 等描述词
            for level, ps in (("locality", parts), ("county/city", parts[1:]), ("state/province", parts[2:])):
                if not ps[0] or len({p.lower() for p in ps if p}) < 2:
                    continue
                q = ", ".join(p for p in ps if p)
                res = geo.nominatim(q, L["iso"])
                rank = int(res.get("place_rank", 30)) if res else 0
                if res and rank > 4:                          # 国家级结果交给下面的 EEZ
                    lvl = "state/province" if rank <= 8 else level
                    conf = "Medium" if lvl == "locality" and L["confidence"] in ("High", "Medium") else "Low"
                    return (res["lat"], res["lon"], "geocode_locality", f"approximate ({lvl})", conf,
                            f"Nominatim '{q}' -> {res.get('display_name', '')[:120]}", str(nom_unc(res)))
            # 具体地名 -> Marine Regions (无国家的南极/公海地点也能定位): 标准化 Locality, 再 WoRMS 地名记录各段; 先精确后模糊
            names_ = [clean_place(L["locality"]), clean_place(L["county_city"])]
            names_ += [clean_place(x) for x in re.split(r"\|\||;|,", L.get("locality_source_text", ""))]
            seen_ = set()
            cbox = country_box(L)
            for nm in names_:
                if not nm or nm.lower() in seen_ or len(nm) > 80 or OCEAN_RE.match(nm) or nm == L["country"]:
                    continue
                seen_.add(nm.lower())
                e = mr_hit(nm, "worms_place_name", "named place/area centroid", "Marine Regions exact", cbox)
                if not e:
                    for x in [y for y in geo.marine_regions(nm, like=True) if in_country(y, cbox)][:1]:
                        if x.get("placeType") not in ("Realm", "Province", "Ecoregion", "Ocean") + NATIONAL and not land_type(x.get("placeType")):
                            lat, lon, unc = area_point(x)
                            e = (str(lat), str(lon), "worms_place_name", "approximate (named place/area centroid)", "Low",
                                 f"Marine Regions like '{nm}' -> {x.get('preferredGazetteerName')} ({x.get('placeType')}, MRGID {x.get('MRGID')})", str(unc))
                if e:
                    return e
            for wb in [w.strip() for w in L["water_body"].split(",") if w.strip()][:2]:
                if not OCEAN_RE.match(wb):
                    e = mr_hit(wb, "geocode_water_body", "water body centroid", "Marine Regions")
                    if e:
                        return e
            if L["country"]:
                x = geo.eez(L["country"], L["iso"])
                if x:
                    lat, lon, unc = area_point(x)
                    return (str(lat), str(lon), "geocode_country_eez", "approximate (EEZ centroid)", "Low",
                            f"country '{L['country']}' -> {x.get('preferredGazetteerName')} (MRGID {x.get('MRGID')})", str(unc))
        for g in sgeo.get(aid, []):                           # 标本 Geounit (WoRMS 地名, 即 Marine Regions 地名)
            x = geo.eez(g) or None
            if x:
                lat, lon, unc = area_point(x)
                return (str(lat), str(lon), "specimen_geounit_eez", "approximate (EEZ centroid)", "Low",
                        f"specimen Geounit '{g}' -> {x.get('preferredGazetteerName')} (MRGID {x.get('MRGID')})", str(unc))
            e = mr_hit(g, "specimen_geounit", "geounit centroid", "specimen Geounit")
            if e:
                return e
        if L is not None:
            for nm in [L["water_body"], L["region"]]:
                for w in [w.strip() for w in (nm or "").split(",") if w.strip()][:2]:
                    e = mr_hit(w, "geocode_ocean_region", "ocean/sea-area centroid", "Marine Regions")
                    if e:
                        return e
        return None

    def by_mrgid(ids, basis, note):
        """WoRMS 分布记录自带的 Marine Regions ID -> 区域代表点 (不靠名称匹配)."""
        for m_ in [x for x in str(ids).split("; ") if x.isdigit()]:
            rec = geo.cached(f"mrid|{m_}", lambda: geo._get(f"https://www.marineregions.org/rest/getGazetteerRecordByMRGID.json/{m_}/", 0.5))
            if not rec or land_type(rec.get("placeType")):
                continue
            if rec.get("placeType") in NATIONAL:
                rec = geo.eez(rec.get("preferredGazetteerName", "")) or None
                if not rec:
                    continue
            lat, lon, unc = area_point(rec)
            return (str(lat), str(lon), basis, "approximate (area centroid)", "Low",
                    f"{note}: {rec.get('preferredGazetteerName')} ({rec.get('placeType')}, MRGID {rec.get('MRGID')})", str(unc))
        return None

    def by_type_dist_name(aid):
        """模式分布记录无 MRGID (05 从网页补抓的记录) -> 按地名在 Marine Regions 精确匹配.
        2026-11-09: M. fijiensis 'Fijian Exclusive Economic Zone'、M. teretiuscula 'Zanzibar' 因无 MRGID 曾留空."""
        if aid not in t.index:
            return None
        for nm in [x.strip() for x in str(t.at[aid, "type_dist_locality"]).split(";") if x.strip()]:
            if OCEAN_RE.match(nm):
                continue
            e = mr_hit(nm, "worms_type_distribution_area", "area centroid", "WoRMS type-locality distribution (by name)")
            if e:
                return e
        return None

    def od_title_region(aid):
        """最后一级 (很粗): WoRMS 无任何模式产地信息时, 从原始描述题目中的国名取该国 EEZ 中心点.
        只作粗略参考 (confidence 'Very low'); 21 步不据此判远距. 2026-11-09 用户要求无模式产地的种也给粗略坐标."""
        if aid not in od.index:
            return None
        title = od.at[aid, "od_title"]
        if len(countries_in(title)) != 1:                     # 题目列多国 (M. galluccii: Argentina, Chile, NZ...) -> 不猜
            return None
        c_, iso_, _ = infer_country(title)
        x = geo.eez(c_, iso_) if c_ else None
        if not x:
            return None
        lat, lon, unc = area_point(x)
        return (str(lat), str(lon), "od_title_country_eez", "approximate (country from OD title)", "Very low",
                f"OD title mentions '{c_}' -> {x.get('preferredGazetteerName')} (MRGID {x.get('MRGID')})", str(unc))

    PLACE_RX = re.compile(r"\b((?:[A-Z][a-z]+\s){1,3}(?:Island|Islands|Bay|Harbou?r|Reef|Lagoon|Channel|Creek|Strait))\b")

    def od_text(aid):
        """compilation 05 原始描述原文模式产地 -> 坐标. 原文写明经纬度 -> original; 否则地名/国家定位 (粗).
        2026-11-09: Schmarda 1861 'An Korallenriffen im Süden von Jamaica' (M. depressa, M. hamata) 等 WoRMS 无模式产地."""
        r = odt.get(aid)
        if not r:
            return None
        src = f"OD {r['work_id']} p. {r['pages']} [{r['tl_cue']}]: '{r['tl_text'][:100]}'"
        title = r["tl_cue"] == "work_title"
        if r.get("tl_lat") and r.get("tl_lon"):
            return r["tl_lat"], r["tl_lon"], "od_text_coordinates", "original", "High", src, ""
        c_, iso_ = r.get("tl_country", ""), r.get("tl_iso", "")
        if not c_:
            return None
        if title and len(countries_in(r["tl_text"])) > 1:
            return None
        cb0 = country_box({"country": c_, "iso": iso_})
        for a, (_, place) in PLACE_ALIASES.items():           # 岛屿旧称 (Madeira, Zanzibar...) 直接查 Marine Regions, 限该国
            if re.search(r"\b" + re.escape(a) + r"\b", r["tl_text"]):    # (不限国家时 'Saint Thomas' 曾命中菲律宾)
                e = mr_hit(place, "od_title_place" if title else "od_text_locality", "named place/area centroid",
                           f"{src} -> Marine Regions", cb0)
                if e:
                    return e
        for q in [q for q in r.get("tl_queries", "").split(" | ") if q]:
            res = geo.nominatim(q, iso_)
            if res and int(res.get("place_rank", 30)) > 8:
                return (res["lat"], res["lon"], "od_title_place" if title else "od_text_locality", "approximate (locality)",
                        "Low", f"{src} -> Nominatim '{q}' -> {res.get('display_name', '')[:80]}", str(nom_unc(res)))
        if not title:
            cb = country_box({"country": c_, "iso": iso_})
            for nm in PLACE_RX.findall(r["tl_text"]):
                e = mr_hit(nm.strip(), "od_text_locality", "named place/area centroid", f"{src} -> Marine Regions", cb)
                if e:
                    return e
        x = geo.eez(c_, iso_)
        if not x:
            return None
        lat, lon, unc = area_point(x)
        return (str(lat), str(lon), "od_title_country_eez" if title else "od_text_country_eez", "approximate (EEZ centroid)",
                "Very low" if title else "Low", f"{src} -> country '{c_}' -> {x.get('preferredGazetteerName')}", str(unc))

    def locate(aid):
        e = evidence(aid) or geocode(aid)
        if not e and aid in t.index and "type_dist_mrgid_ids" in t:   # 只用模式分布记录 (WoRMS 模式产地信息), 不用非模式分布
            e = by_mrgid(t.at[aid, "type_dist_mrgid_ids"], "worms_type_distribution_area", "WoRMS type-locality distribution area")
        return e or by_type_dist_name(aid)

    rows = []
    sp = n[n["rank"].isin(["Species", "Subspecies", "Variety", "Forma"])]
    for i, r in enumerate(sp.to_dict("records"), 1):
        aid, oid = r["aphia_id"], r["original_name_aphia_id"]
        via = ""
        e = evidence(aid)
        if not e and oid and oid != aid:
            e, via = evidence(oid), "via original combination"
        if not e:
            e = locate(aid)
            if not e and oid and oid != aid:
                e, via = locate(oid), "via original combination"
        ew = e                                                 # 只用 WoRMS 信息得到的坐标 (供原文复查)
        o = od_text(aid)
        if o and (not e or (o[3] == "original" and str(e[3]).startswith("approximate") and e[2] != "manual_override")):
            e, via = o, ""                                     # WoRMS 无模式产地, 或原文写明经纬度而 WoRMS 只有近似点
        if not e:                                             # 最粗一级, 在原始组合也查不到之后
            e = od_title_region(aid)
            if not e and oid and oid != aid:
                e, via = od_title_region(oid), "via original combination"
        lat, lon, basis, prec, conf, detail, unc = e if e else ("", "", "", "", "", "", "")
        via = via if e else ""
        # 交叉核对: 原始描述原文定位 vs 采用坐标 (相距 > 1000 km 须核实; 原文为 OCR, 也可能是抽取错)
        # 原文为地名/经纬度级 -> 距离; 原文只到国家 -> 只看采用坐标是否在该国 EEZ 框 (外扩 5°) 内
        # 用户 2026-11-09: WoRMS 坐标也须原文复查 -> 比的是"只用 WoRMS 得到的坐标" (ew), 不是最终采用值
        chk_km, chk_cty = "", ""
        if o and ew and o[4] != "Very low":
            wl, wo = float(ew[0]), float(ew[1])
            if o[2] in ("od_text_coordinates", "od_text_locality"):
                chk_km = str(round(_hav_km(wl, wo, float(o[0]), float(o[1]))))
            if aid in odt and odt[aid].get("tl_country"):
                cb = country_box({"country": odt[aid]["tl_country"], "iso": odt[aid]["tl_iso"]})
                if cb:
                    chk_cty = "Y" if in_country({"latitude": wl, "longitude": wo}, cb) else "N"
        rows.append({"aphia_id": aid, "scientific_name": r["scientific_name"], "coord_lat": lat, "coord_lon": lon,
                     "coord_basis": basis, "coord_precision": prec, "coord_confidence": conf, "coord_uncertainty_km": unc,
                     "coord_detail": (detail + (f" [{via}]" if via else "")).strip(),
                     "od_tl_text": odt[aid]["tl_text"] if aid in odt else "",
                     "od_tl_source": f"{odt[aid]['work_id']} p. {odt[aid]['pages']} [{odt[aid]['tl_cue']}]" if aid in odt else "",
                     "worms_only_lat": ew[0] if ew else "", "worms_only_lon": ew[1] if ew else "",
                     "worms_only_basis": ew[2] if ew else "", "worms_only_unc_km": ew[6] if ew else "",
                     "od_lat": o[0] if o else "", "od_lon": o[1] if o else "", "od_basis": o[2] if o else "",
                     "od_vs_coord_km": chk_km, "od_country_match": chk_cty})
        if i % 200 == 0:
            geo.save()
            print(f"  {i}/{len(sp)}", flush=True)
    geo.save()
    c = pd.DataFrame(rows)
    c = snap_to_sea(c)
    write_tsv(c, out / "coordinates.tsv")
    if not ov_path.exists():
        write_tsv(pd.DataFrame(columns=["aphia_id", "scientific_name", "lat", "lon", "basis"]), ov_path)
    summary("14_coordinates", [f"{len(c)} species-level names: with coordinates {(c.coord_lat != '').sum()}",
                               "basis: " + "; ".join(f"{k} {v}" for k, v in c[c.coord_basis != ''].coord_basis.value_counts().items()),
                               "precision: original {0}; approximate {1}".format(c.coord_precision.eq("original").sum(), c.coord_precision.str.startswith("approximate").sum()),
                               f"-> {out / 'coordinates.tsv'}   (manual fixes: {ov_path.name})"])


if __name__ == "__main__":
    main(sys.argv[1])
