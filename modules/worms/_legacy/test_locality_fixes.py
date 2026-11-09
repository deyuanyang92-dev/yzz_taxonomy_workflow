"""worms 14/05/21 回归测试 (pytest): 2026-11-09 岩虫属综述中查出的地理编码/分布问题，每条一测。"""
import importlib.util
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[1] / "lib"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), HERE / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = _load("14_coordinates.py")
D5 = _load("05_distributions.py")
D21 = _load("21_distribution_check.py")


def test_decimal_degrees_with_hemisphere():
    # M. zanolae: '-2.9°S, 151.1°E' 曾被读成 9°S 1°E
    assert C.text_coords("off New Ireland, Papua New Guinea, -2.9°S, 151.1°E, 350-847 m")[:2] == (-2.9, 151.1)
    assert C.text_coords("12°30'S 45°15'W")[:2] == (-12.5, -45.25)


def test_infer_country_first_and_query():
    # M. gayi / M. peruviana: 'Lima, Peru' 无结构化国家 -> Marine Regions 命中葡萄牙 Lima 河
    c, iso, qs = C.infer_country("Lima, Peru or Valparaiso, Chile")
    assert (c, iso) == ("Peru", "PE") and qs[0] == "Lima, Peru"
    c, iso, qs = C.infer_country("South west Atlantic, Brazil, Sao Paulo, Sao Sebastio, Sao Francisco Beach")
    assert c == "Brazil" and qs[-1] == "Sao Paulo, Brazil" and "Sao Francisco Beach" in qs[0]


def test_infer_country_ignores_water_bodies_and_nan():
    assert C.infer_country("Gulf of Mexico")[0] == ""
    assert C.infer_country(float("nan")) == ("", "", [])   # NaN 曾让整个种的地理编码失败


def test_distribution_locality_normalisation():
    # 网页 Geounit 'Madagascar (Nation) ( doubtful )' 与 REST 'Madagascar' 必须配上
    assert D5._norm("Madagascar (Nation) ( doubtful )") == "madagascar"
    assert D5._norm("South Africa (country) (Nation)") == D5._norm("South Africa (country)")


def test_box_distance():
    d, _ = D21.box_dist(0.0, 0.0, (-1, 1, -1, 1))
    assert d == 0
    d, _ = D21.box_dist(0.0, 0.0, (0, 0, 10, 10))
    assert math.isclose(d, D21.hav_km(0, 0, 0, 10), rel_tol=1e-6)
    d, _ = D21.box_dist(0.0, 179.0, (-1, 1, 170, -170))      # 跨 180° 经线的框
    assert d == 0


def test_large_region_far_from_tl_is_distant():
    # M. aenea (TL Chile) 的新西兰 EEZ 记录曾被当作 'coarse region' 而漏判
    base = {"typeStatus": "", "dist_type_locality": ""}
    assert D21.classify({**base, "dist_km": 7473, "box_diag_km": 5000}) == "distant"
    assert D21.classify({**base, "dist_km": 0, "box_diag_km": 5000}) == "coarse region"
    assert D21.classify({**base, "dist_km": 300, "box_diag_km": 800}) == "near"


def test_od_title_country_inference():
    # M. fauchaldi: WoRMS 无模式产地; 原始描述题目 '... from northern Australia ...' -> 粗略 (Australia EEZ)
    t = ("A new species of Marphysa Quatrefages, 1865 (Polychaeta: Eunicida: Eunicidae) from northern Australia "
         "and a review of similar taxa from the Indo-west Pacific")
    assert C.infer_country(t)[:2] == ("Australia", "AU")


def test_rough_basis_not_judged_distant():
    assert "od_title_country_eez" in D21.ROUGH_BASIS


def test_od_title_multiple_countries_not_guessed():
    # M. galluccii: 题目 '... With addenda to the Eunicemorpha of Argentina, Chile, New Zealand, Australia ...' 曾被定到智利
    t = ("The Eunicemorph polychaete annelids from Antarctic and Subantarctic Seas. With addenda to the Eunicemorpha "
         "of Argentina, Chile, New Zealand, Australia, and the Southern Indian Ocean")
    assert len(C.countries_in(t)) > 1
    assert C.countries_in("from northern Australia and a review of similar taxa") == {"AU"}


def test_verify_status():
    V = _load("22_tl_verify.py")
    assert V.status({"od_vs_coord_km": "50", "od_country_match": "Y", "worms_only_lat": "1"}, True) == "agree"
    assert V.status({"od_vs_coord_km": "", "od_country_match": "N", "worms_only_lat": "1"}, True) == "conflict"
    assert V.status({"coord_basis": "od_text_country_eez", "worms_only_lat": ""}, True) == "OD only"
    assert V.status({"od_cue": "work_title"}, True) == "OD title only"
    assert V.status({}, False) == "no OD text"


def test_west_indies_is_not_india():
    # M. brevitentaculata: WoRMS 'Atlantic Ocean, West Indies' 曾经模糊匹配成 India -> 德里
    assert C.infer_country("Atlantic Ocean, West Indies")[0] == ""


def test_verify_coarse_worms_is_od_finer():
    V = _load("22_tl_verify.py")
    assert V.status({"od_vs_coord_km": "9000", "worms_only_lat": "1", "worms_only_unc_km": "8227"}, True) == "OD finer"
