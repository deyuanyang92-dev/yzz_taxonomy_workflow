"""lib/worms_match.py 回归测试 (离线, 假 WoRMS 客户端)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import worms_match as wm  # noqa: E402


def test_parse_subgenus_and_authority():
    p = wm.parse_name("Ceratonereis (Composetia) costae (Grube, 1840)")
    assert p["name"] == "Ceratonereis costae"
    assert p["name_subgenus"] == "Ceratonereis (Composetia) costae"
    assert p["authority"] == "(Grube, 1840)"


def test_parse_fullwidth_and_qualifier():
    p = wm.parse_name("Perinereis cf. nuntia （Savigny，1818）")
    assert p["name"] == "Perinereis nuntia"
    assert p["qualifier"] == "cf."
    assert p["authority"] == "(Savigny,1818)"


def test_parse_subspecies_and_garbage():
    assert wm.parse_name("Platynereis dumerilii dumerilii Audouin, 1833")["name"] == "Platynereis dumerilii dumerilii"
    assert wm.parse_name("Nereis vexillosa var. minor Grube")["name"] == "Nereis vexillosa var. minor"
    assert wm.parse_name("某 OCR 文本")["name"] == ""


class FakeClient:
    def __init__(self, db):
        self.db, self.calls = db, []

    def records_by_match_names(self, names, **kw):
        self.calls.append(list(names))
        return [self.db.get(n, []) for n in names]


def rec(name, status, valid, family="Nereididae", mt="exact", aid=1):
    return {"scientificname": name, "status": status, "valid_name": valid, "family": family,
            "match_type": mt, "AphiaID": aid, "valid_AphiaID": aid + 100}


def test_synonym_not_flagged_but_marked_changed():
    c = FakeClient({"Neanthes japonica": [rec("Neanthes japonica", "unaccepted", "Hediste japonica")]})
    r = wm.match_names(["Neanthes japonica (Izuka, 1908)"] * 2, "Nereididae", c)
    row = r["Neanthes japonica (Izuka, 1908)"]
    assert row["valid_name"] == "Hediste japonica" and row["name_changed"] == "Y"
    assert row["check_note"] == ""
    assert c.calls == [["Neanthes japonica"]]          # 重复名只查一次


def test_subgenus_retry_and_flags():
    c = FakeClient({
        "Nereis (Neanthes) foo": [rec("Nereis (Neanthes) foo", "accepted", "Nereis (Neanthes) foo")],
        "Perinereis nunita": [rec("Perinereis nuntia", "accepted", "Perinereis nuntia", mt="near_1")],
        "Nereis dubia": [rec("Nereis dubia", "nomen dubium", "")],
    })
    r = wm.match_names(["Nereis (Neanthes) foo", "Perinereis nunita", "Nereis dubia", "Nereis nothing"], "", c)
    assert r["Nereis (Neanthes) foo"]["AphiaID"] == "1"
    assert "near_1" in r["Perinereis nunita"]["check_note"]
    assert "无有效名" in r["Nereis dubia"]["check_note"]
    assert r["Nereis nothing"]["check_note"] == "WoRMS 无匹配"


def test_family_preference_among_homonyms():
    c = FakeClient({"Nereis alba": [rec("Nereis alba", "accepted", "Nereis alba", family="Mollusca", aid=5),
                                    rec("Nereis alba", "accepted", "Nereis alba", aid=7)]})
    row = wm.match_names(["Nereis alba"], "Nereididae", c)["Nereis alba"]
    assert row["AphiaID"] == "7" and row["n_candidates"] == "2"


def test_fallback_glued_and_infraspecific():
    c = FakeClient({
        "Typosyllis vittata": [rec("Typosyllis vittata", "unaccepted", "Syllis vittata", family="Syllidae")],
        "Perinereis cultrifera": [rec("Perinereis cultrifera", "accepted", "Perinereis cultrifera")],
    })
    r = wm.match_names(["Typosyllisvittata (Grube, 1840)", "Perinereis cultrifera var. typica Grube",
                        "Eusylliscf.irregulata Imajima, 1966"], "", c)
    assert r["Typosyllisvittata (Grube, 1840)"]["valid_name"] == "Syllis vittata"
    assert "OCR 粘连" in r["Typosyllisvittata (Grube, 1840)"]["check_note"]
    assert r["Perinereis cultrifera var. typica Grube"]["AphiaID"] == "1"
    assert "退回按种" in r["Perinereis cultrifera var. typica Grube"]["check_note"]
    assert r["Eusylliscf.irregulata Imajima, 1966"]["query_name"] == "Eusyllis irregulata"


def test_variety_prefers_elevated_name_over_species():
    """2026-10-11: P. nuntia var. brevicirris 的有效名是 P. vallata, 退回到 P. nuntia 是错的."""
    c = FakeClient({
        "Perinereis helleri": [rec("Perinereis helleri", "accepted", "Perinereis helleri", aid=9)],
        "Perinereis cultrifera": [rec("Perinereis cultrifera", "accepted", "Perinereis cultrifera", aid=1)],
        "Perinereis nuntia brevicirris": [rec("Perinereis nuntia brevicirris", "junior subjective synonym",
                                              "Perinereis vallata", aid=3)],
    })
    r = wm.match_names(["Perinereis cultrifera var. helleri Grube", "Perinereis nuntia var. brevicirris Grube"], "", c)
    assert r["Perinereis cultrifera var. helleri Grube"]["AphiaID"] == "9"
    assert "种级名称" in r["Perinereis cultrifera var. helleri Grube"]["match_info"]
    assert r["Perinereis nuntia var. brevicirris Grube"]["valid_name"] == "Perinereis vallata"
