"""compilation 05 原始描述原文 -> 模式产地 回归测试 (pytest). 例句取自 2026-11-09 岩虫属原始描述原文 (OCR)."""
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def M(tmp_path_factory):
    root = tmp_path_factory.mktemp("proj")
    (root / "08_知识库").mkdir()
    (root / "08_知识库" / "compilation.json").write_text('{"genus": "Marphysa", "table": "x.xlsx"}', encoding="utf-8")
    sys.argv = ["05", str(root)]
    sys.path.insert(0, str(HERE))
    sys.modules.pop("cfg", None)
    spec = importlib.util.spec_from_file_location("tl05", HERE / "05_type_locality.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_german_closing_sentence(M):
    # Schmarda 1861: 产地在末句, 德文
    cue, s = M.extract("Die Bauchcirre fehlt. An Korallenriffen im Süden von Jamaica.")
    assert cue == "locality_sentence" and "Jamaica" in s
    assert M.W14.infer_country(s)[1] == "JM"


def test_ocr_ceylon(M):
    cue, s = M.extract("bei zweifacher Vergrösserung. Au der Ostküste von Cevlon. S c li")
    assert M.W14.infer_country(s)[1] == "LK"


def test_holotype_coordinates(M):
    t = ("Material examined. HOLOTYPE: Australia, Northern Territory, off Elizabeth River, Darwin region "
         "12.70313˚S 130.96233˚E (NTM W23040), coll. C. Glasby.")
    cue, s = M.extract(t)
    assert cue == "type_locality" or cue == "holotype"
    assert M.W14.text_coords(s)[:2] == (-12.70313, 130.96233)


def test_type_locality_only_as_heading(M):
    # 讨论段落中顺带的 'type locality' 不算 (M. chirigota 曾取到 'chirigotas are satirical songs')
    cue, _ = M.extract("This name is unrelated to the type locality of the species. The chirigotas are songs.")
    assert cue != "type_locality"
    cue, s = M.extract("Remarks. Type locality: Río Lagartos, Yucatán, Mexico. Distribution. Yucatán.")
    assert cue == "type_locality" and s.startswith("Río Lagartos")


def test_work_title_fallback(M):
    cue, s = M.extract("Ein bräunliches Thier von 2,0 cm.", "Die Wurmfauna von Madeira, IV. Z. wiss. Zool.")
    assert cue == "work_title" and M.W14.infer_country(s)[1] == "PT"


def test_country_name_inside_water_body_or_adjective(M):
    W = M.W14
    assert W.infer_country("South China Sea, Malaysia, east coast")[1] == "MY"
    assert W.infer_country("Beihai coast, south of China")[1] == "CN"
    assert W.infer_country("Leodicidae of the West Indian region")[0] == ""
    assert W.infer_country("Fisheries Research Station, Colombo")[1] == "LK"


def test_ocr_control_char_degree(M):
    # Kara 2023 M. mzingazia: 度号在文字层中是控制字符 -> Excel 导出报 IllegalCharacterError
    cue, s = M.extract("Holotype. One specimen, Richards Bay harbour, South Africa, 28\x0147′09.6″S 32\x0104′55.8″E, coll. J. Kara.")
    assert "\x01" not in s
    lat, lon = M.W14.text_coords(s)[:2]
    assert round(lat, 2) == -28.79 and round(lon, 2) == 32.08


def test_old_english_collected_sentence(M):
    # Treadwell 1921 M. brevitentaculata
    cue, s = M.extract("Body slender. The specimens were collected in sand on a beach near Scarborough, in Tobago, in April 1918.")
    assert cue == "locality_sentence" and M.W14.infer_country(s)[1] == "TT"
