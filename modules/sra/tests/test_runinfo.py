import json

import pytest

from conftest import FIX, TAXON, fake_eutils, load_step


def esearch_json(count, ids=(), webenv="WE", qk="1"):
    return json.dumps({"esearchresult": {"count": str(count), "webenv": webenv, "querykey": qk,
                                         "idlist": list(ids)}})


RUNINFO = (FIX / "runinfo.csv").read_text(encoding="utf-8-sig")


def test_parse_runinfo_quirks():
    from parse import parse_runinfo
    rows = parse_runinfo((FIX / "runinfo.csv").read_text(encoding="utf-8"))
    assert [r["Run"] for r in rows] == ["SRR1", "SRR2", "SRR3"]
    assert "Run" in rows[0]                                  # BOM stripped from first header


def test_identity_env_overrides_config(tmp_path, monkeypatch):
    from eutils import load_identity
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "ncbi.json").write_text('{"email": "a@x", "api_key": "K1"}')
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.setenv("NCBI_API_KEY", "K2")
    assert load_identity(tmp_path) == ("a@x", "K2")


def test_resolve_taxid_ambiguous():
    from eutils import EutilsError, resolve_taxid
    eu, _ = fake_eutils([("esearch", esearch_json(2, ["111", "222"])),
                         ("efetch", "<TaxaSet><Taxon><TaxId>111</TaxId><ScientificName>X</ScientificName>"
                                    "<Lineage>A; B</Lineage></Taxon><Taxon><TaxId>222</TaxId>"
                                    "<ScientificName>X</ScientificName><Lineage>C; D</Lineage></Taxon></TaxaSet>")])
    with pytest.raises(EutilsError) as e:
        resolve_taxid(eu, "X")
    assert "111" in str(e.value) and "222" in str(e.value)


def test_resolve_taxid_numeric_passthrough():
    from eutils import resolve_taxid
    eu, t = fake_eutils([])
    assert resolve_taxid(eu, "46593") == "46593"
    assert t.urls == []


def test_error_body_retried_then_fails():
    from eutils import EutilsError
    eu, t = fake_eutils([("esearch", "<!DOCTYPE html><html>busy</html>")])
    with pytest.raises(EutilsError):
        eu.esearch("sra", "x")
    assert len(t.urls) == 5


def test_xml_error_body_is_failure():
    from eutils import EutilsError
    eu, t = fake_eutils([("efetch", "<eFetchResult><ERROR>Empty result</ERROR></eFetchResult>")])
    with pytest.raises(EutilsError):
        eu.efetch_ids("sra", ["1"])


def run01(argv, rules):
    eu, t = fake_eutils(rules)
    rc = load_step("01_runinfo").main(argv, eutils=eu)
    return rc, t


def manifest(project):
    return json.loads((project / "02_原始数据" / "sra" / "manifest.json").read_text(encoding="utf-8"))


def test_step01_taxon_invariant_ok(project):
    rc, _ = run01([TAXON, "--taxid", "46593"], [("esearch", esearch_json(2)), ("efetch", RUNINFO)])
    assert rc == 0
    m = manifest(project)
    assert m["ok"] is True and m["experiments"] == 2 and m["runs"] == 3
    assert m["term"] == "txid46593[Organism:exp]"
    tsv = (project / "02_原始数据" / "sra" / "runinfo.tsv").read_text(encoding="utf-8").splitlines()
    assert len(tsv) == 4 and tsv[0].startswith("Run\t")


def test_step01_invariant_mismatch(project):
    rc, _ = run01([TAXON, "--taxid", "46593"], [("esearch", esearch_json(3)), ("efetch", RUNINFO)])
    assert rc == 1
    m = manifest(project)
    assert m["ok"] is False and any("Experiment" in p for p in m["problems"])


def test_max_experiments_guard(project):
    rc, t = run01([TAXON, "--taxid", "1"], [("esearch", esearch_json(300000))])
    assert rc == 2
    assert not any("efetch" in u for u in t.urls)


def test_runs_not_found(project, tmp_path):
    lst = tmp_path / "runs.txt"
    lst.write_text("SRR1\nSRR2\n\nSRR3\nSRR3\nSRR999\n")
    rc, t = run01([TAXON, "--runs", str(lst)], [("esearch", esearch_json(2)), ("efetch", RUNINFO)])
    assert rc == 0
    assert b"SRR999%5Baccn%5D" in (t.posts[0] or t.urls[0].encode())
    nf = (project / "02_原始数据" / "sra" / "runs_not_found.txt").read_text().split()
    assert nf == ["SRR999"]
    assert manifest(project)["not_found"] == 1


def test_runinfo_file_quirks(project):
    rc, t = run01([TAXON, "--runinfo", str(FIX / "runinfo.csv")], [])
    assert rc == 0 and t.urls == []
    m = manifest(project)
    assert m["mode"] == "runinfo" and m["runs"] == 3


def test_long_query_is_posted():
    eu, t = fake_eutils([("esearch", esearch_json(0))])
    eu.esearch("sra", " OR ".join(f"SRR{1000000 + i}[accn]" for i in range(200)))
    assert t.posts[0] is not None and len(t.urls[0]) < 2000
    assert b"SRR1000199" in t.posts[0]


def test_short_query_is_get():
    eu, t = fake_eutils([("esearch", esearch_json(0))])
    eu.esearch("sra", "txid1[Organism:exp]")
    assert t.posts[0] is None and "txid1" in t.urls[0]
