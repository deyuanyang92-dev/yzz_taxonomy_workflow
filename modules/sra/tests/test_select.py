import pandas as pd

from classify import select_samples
from conftest import TAXON, load_step


def s(key, gb, taxid="1", bp="P1", cat="shallow_WGS", layout="PAIRED", runs=None, plat="ILLUMINA"):
    return {"sample_key_derived": key, "category_derived": cat, "TaxID": taxid, "BioProject": bp,
            "total_Gb": gb, "LibraryLayout": layout, "Platform": plat, "runs": runs or f"{key}r"}


def test_top_per_group():
    df = pd.DataFrame([s("A", 1), s("B", 5), s("C", 3), s("D", 2)])
    out = select_samples(df, ["shallow_WGS"], None, "PAIRED", 3)
    assert list(out.sample_key_derived) == ["B", "C", "D"]


def test_selected_sample_brings_all_runs(project):
    d = project / "02_原始数据" / "sra"
    d.mkdir(parents=True)
    pd.DataFrame([s("A", 2, runs="SRR1;SRR2"), s("B", 1, cat="Hi-C", runs="SRR3")]).to_csv(
        d / "samples.tsv", sep="\t", index=False)
    assert load_step("05_select").main([TAXON, "--type", "shallow_WGS"]) == 0
    assert (d / "run_list_default.txt").read_text().split() == ["SRR1", "SRR2"]
    assert (d / "selected_default.tsv").exists()


def test_layout_filter():
    df = pd.DataFrame([s("A", 1, layout="SINGLE"), s("B", 1)])
    assert list(select_samples(df, ["shallow_WGS"], None, "PAIRED", 3).sample_key_derived) == ["B"]
    assert len(select_samples(df, ["shallow_WGS"], None, "ALL", 3)) == 2


def test_platform_filter():
    df = pd.DataFrame([s("A", 1, plat="DNBSEQ"), s("B", 1)])
    assert list(select_samples(df, ["shallow_WGS"], ["DNBSEQ"], "ALL", 3).sample_key_derived) == ["A"]


def test_per_run_mode():
    runs = pd.DataFrame([{"Run": r, "sample_key_derived": "A", "category_derived": "shallow_WGS", "TaxID": "1",
                          "BioProject": "P1", "bases": str(b), "LibraryLayout": "PAIRED", "Platform": "ILLUMINA"}
                         for r, b in [("R1", 1e9), ("R2", 3e9), ("R3", 2e9), ("R4", 4e9)]])
    out = select_samples(pd.DataFrame(), ["shallow_WGS"], None, "PAIRED", 3, per="run", runs=runs)
    assert list(out.runs) == ["R4", "R2", "R3"]


def test_sp_taxids_not_collapsed():
    df = pd.DataFrame([s("A", 1, taxid="900"), s("B", 1, taxid="901")])
    assert len(select_samples(df, ["shallow_WGS"], None, "PAIRED", 1)) == 2


def test_select_empty(project):
    d = project / "02_原始数据" / "sra"
    d.mkdir(parents=True)
    (d / "samples.tsv").write_text("sample_key_derived\tcategory_derived\tTaxID\tBioProject\ttotal_Gb\t"
                                   "LibraryLayout\tPlatform\truns\n")
    assert load_step("05_select").main([TAXON]) == 0
    assert (d / "run_list_default.txt").read_text() == ""
