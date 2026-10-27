import pandas as pd

from classify import classify_runs, load_rules, summarize_samples, summarize_species

R = load_rules()


def run(run="SRR1", bs="SAMN1", strategy="WGS", sel="RANDOM", src="GENOMIC", plat="ILLUMINA", gb=1.0, **kw):
    return {"Run": run, "BioSample": bs, "LibraryStrategy": strategy, "LibrarySelection": sel,
            "LibrarySource": src, "Platform": plat, "bases": str(int(gb * 1e9)), "LibraryLayout": "PAIRED",
            "TaxID": kw.get("taxid", "1"), "ScientificName": kw.get("name", "A b"), "BioProject": kw.get("bp", "P1")}


def cat(*rows):
    return list(classify_runs(pd.DataFrame(list(rows)), R)["category_derived"])


def test_pcr_selection_classified_by_volume():
    # Annelida 2026-10-27: WGS+PCR are mostly genome skimming / genome data (PRJNA1075478, PRJNA551036)
    df = classify_runs(pd.DataFrame([run(sel="PCR", gb=1.84), run(run="R2", bs="S2", sel="PCR", gb=0.08)]), R)
    assert list(df.category_derived) == ["shallow_WGS", "low_data_WGS"]
    assert "PCR" in df.category_rule_derived[0]


def test_rule_metagenomic():
    assert cat(run(src="METAGENOMIC", gb=5)) == ["WGS_metagenomic"]


def test_rule_long():
    assert cat(run(plat="PACBIO_SMRT", gb=30), run(run="SRR2", bs="S2", plat="OXFORD_NANOPORE")) == \
        ["long_read_WGS", "long_read_WGS"]


def test_thresholds():
    rows = [run(run=f"R{i}", bs=f"S{i}", gb=g) for i, g in enumerate([0.49, 0.5, 9.99, 10.0])]
    assert cat(*rows) == ["low_data_WGS", "shallow_WGS", "shallow_WGS", "deep_WGS"]


def test_sample_sum_includes_pcr_runs_excludes_metagenomic():
    df = classify_runs(pd.DataFrame([run(run="R1", gb=3), run(run="R2", sel="PCR", gb=20),
                                     run(run="R3", src="METAGENOMIC", gb=50)]), R)
    assert list(df.category_derived) == ["deep_WGS", "deep_WGS", "WGS_metagenomic"]
    assert df.sample_total_Gb_derived[0] == 23.0


def test_runs_of_one_sample_are_summed():
    df = classify_runs(pd.DataFrame([run(run="R1", gb=6), run(run="R2", gb=6)]), R)
    assert set(df.category_derived) == {"deep_WGS"}


def test_empty_biosample_uses_run():
    df = classify_runs(pd.DataFrame([run(run="R1", bs=""), run(run="R2", bs="")]), R)
    assert list(df.sample_key_derived) == ["R1", "R2"]


def test_rnaseq_raw_and_long():
    assert cat(run(strategy="RNA-Seq", sel="cDNA", src="TRANSCRIPTOMIC"),
               run(run="R2", bs="S2", strategy="RNA-Seq", plat="PACBIO_SMRT"),
               run(run="R3", bs="S3", strategy="Hi-C")) == ["RNA-Seq", "long_read_RNA", "Hi-C"]


def test_rule_text():
    df = classify_runs(pd.DataFrame([run(gb=1.84)]), R)
    assert "1.84 Gb in [0.5,10) -> shallow_WGS" in df.category_rule_derived[0]


def test_case_insensitive():
    assert cat(run(strategy="wgs", src="metagenomic")) == ["WGS_metagenomic"]


def test_summaries():
    df = classify_runs(pd.DataFrame([run(run="R1", gb=1), run(run="R2", gb=1),
                                     run(run="R3", bs="S3", strategy="RNA-Seq", gb=4)]), R)
    s = summarize_samples(df)
    assert len(s) == 2
    wgs = s[s.category_derived == "shallow_WGS"].iloc[0]
    assert wgs.n_runs == 2 and wgs.total_Gb == 2.0 and wgs.runs == "R1;R2"
    tax = pd.DataFrame([{"TaxID": "1", "rank_derived": "species", "phylum": "Annelida", "class": "", "order": "",
                         "family": "F", "genus": "A", "species": "A b"}])
    sp = summarize_species(s, tax)
    assert len(sp) == 1
    row = sp.iloc[0]
    assert row["family"] == "F" and row["shallow_WGS_samples"] == 1 and row["RNA-Seq_Gb"] == 4.0
