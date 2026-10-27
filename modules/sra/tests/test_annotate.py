import json

from conftest import FIX, TAXON, fake_eutils, load_step

XML = (FIX / "sra_pkg.xml").read_text(encoding="utf-8")
ESEARCH = json.dumps({"esearchresult": {"count": "1", "webenv": "W", "querykey": "1", "idlist": []}})


def test_parse_sra_package():
    from parse import parse_sra_packages
    rows = parse_sra_packages(XML)
    assert len(rows) == 1
    r = rows[0]
    assert r["Run"] == "SRR37048088"
    assert r["experiment_title"] == "Genome skimming dataset of Alentiana barnichae"
    assert r["study_title"].startswith("Phylogenomic studies of the genus Alentiana")
    assert r["design_description"] == "Low coverage, partial genome scan"
    assert r["collection_date"] == "2019-06-09"
    assert r["organisation_country"] == "China"
    assert not any("email" in k or "contact" in k for k in r)


def test_attribute_without_value_skipped_and_clash_prefixed():
    from parse import parse_sra_packages
    extra = ("<SAMPLE_ATTRIBUTE><TAG>empty_tag</TAG></SAMPLE_ATTRIBUTE>"
             "<SAMPLE_ATTRIBUTE><TAG>study_title</TAG><VALUE>from sample</VALUE></SAMPLE_ATTRIBUTE>")
    r = parse_sra_packages(XML.replace("<SAMPLE_ATTRIBUTES>", "<SAMPLE_ATTRIBUTES>" + extra))[0]
    assert "empty_tag" not in r
    assert r["sample_study_title"] == "from sample"
    assert r["study_title"].startswith("Phylogenomic")


def write_runinfo(project, runs):
    d = project / "02_原始数据" / "sra"
    d.mkdir(parents=True, exist_ok=True)
    (d / "runinfo.tsv").write_text("Run\tExperiment\n" + "".join(f"{r}\tSRX{i}\n" for i, r in enumerate(runs)))
    return d


def test_step02_keys_by_run(project):
    d = write_runinfo(project, ["SRR37048088"])
    eu, _ = fake_eutils([("esearch", ESEARCH), ("efetch", XML)])
    assert load_step("02_annotate").main([TAXON], eutils=eu) == 0
    lines = (d / "annotate.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0].split("\t")[0] == "Run" and len(lines) == 2


def test_step02_missing_runs_reported(project):
    d = write_runinfo(project, ["SRR37048088", "SRR0000001"])
    eu, _ = fake_eutils([("esearch", ESEARCH), ("efetch", XML)])
    assert load_step("02_annotate").main([TAXON], eutils=eu) == 1
    assert (d / "annotate_missing.txt").read_text().split() == ["SRR0000001"]


def test_step02_taxon_mode_reuses_term(project):
    d = write_runinfo(project, ["SRR37048088"])
    (d / "manifest.json").write_text(json.dumps({"mode": "taxon", "term": "txid46593[Organism:exp]"}))
    eu, t = fake_eutils([("esearch", ESEARCH), ("efetch", XML)])
    assert load_step("02_annotate").main([TAXON], eutils=eu) == 0
    assert "txid46593" in t.urls[0] and "accn" not in t.urls[0]
    assert "retmax=500" in t.urls[1]
