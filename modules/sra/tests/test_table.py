import json

import pytest
from openpyxl import load_workbook

from conftest import TAXON, load_step

SHEETS = ["Summary", "Samples", "shallow_WGS", "deep_WGS", "long_read_WGS", "RNA-Seq", "Hi-C", "Other",
          "Runs", "QC", "Query"]
HDR = "Run\tExperiment\tLibraryStrategy\tLibrarySelection\tLibrarySource\tLibraryLayout\tPlatform\tbases\t" \
      "BioProject\tBioSample\tTaxID\tScientificName\n"


def setup(project, runinfo_rows, annotate=None, taxonomy=None):
    d = project / "02_原始数据" / "sra"
    d.mkdir(parents=True)
    (d / "runinfo.tsv").write_text(HDR + "".join(runinfo_rows), encoding="utf-8")
    if annotate is not None:
        (d / "annotate.tsv").write_text(annotate, encoding="utf-8")
    if taxonomy is not None:
        (d / "taxonomy.tsv").write_text(taxonomy, encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({"taxon": TAXON, "mode": "taxon", "term": "txid1[Organism:exp]",
                                                 "runs": len(runinfo_rows), "problems": []}))
    return d


ROWS = ["SRR1\tX1\tWGS\tRANDOM\tGENOMIC\tPAIRED\tILLUMINA\t2000000000\tP1\tS1\t11.0\tA b\n",
        "SRR2\tX2\tRNA-Seq\tcDNA\tTRANSCRIPTOMIC\tPAIRED\tILLUMINA\t5000000000\t\tS2\t11\tA b\n",
        "SRR3\tX3\tWGS\tPCR\tGENOMIC\tSINGLE\tILLUMINA\t80000000\tP3\tS3\t12\tC d\n"]
ANN = "Run\texperiment_title\tgeo_loc_name\nSRR1\t=cmd|' /C calc'!A0\tChina: Qingdao\n"
TAX = "TaxID\trank_derived\tphylum\tclass\torder\tfamily\tgenus\tspecies\n11\tspecies\tAnnelida\t\t\tF\tA\tA b\n"


def xlsx(project):
    return next((project / "04_处理数据" / "sra").glob("*_SRA_*.xlsx"))


def test_merge_preserves_rows(project):
    d = setup(project, ROWS, ANN, TAX)
    assert load_step("04_table").main([TAXON]) == 0
    lines = (d / "table.tsv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    hdr = lines[0].split("\t")
    r1 = dict(zip(hdr, lines[1].split("\t")))
    assert r1["family"] == "F" and r1["geo_loc_name"] == "China: Qingdao" and r1["TaxID"] == "11.0"
    assert r1["category_derived"] == "shallow_WGS"


def test_excel_sheets(project):
    setup(project, ROWS, ANN, TAX)
    load_step("04_table").main([TAXON])
    wb = load_workbook(xlsx(project))
    assert wb.sheetnames == SHEETS
    runs = wb["Runs"]
    hdr = [c.value for c in runs[1]]
    assert runs.max_row == 4
    title = runs.cell(row=2, column=hdr.index("experiment_title") + 1)
    assert title.data_type == "s"                                   # NCBI text never becomes a formula
    qc = [r[0] for r in wb["QC"].iter_rows(min_row=2, values_only=True)]
    assert "WGS_PCR_suspect" in qc and "empty_BioProject" in qc
    der = runs.cell(row=1, column=hdr.index("category_derived") + 1)
    assert der.fill.fgColor.rgb.endswith("FFF2CC")


def test_empty_pipeline(project):
    setup(project, [])
    assert load_step("04_table").main([TAXON]) == 0
    wb = load_workbook(xlsx(project))
    q = {r[0]: r[1] for r in wb["Query"].iter_rows(min_row=2, values_only=True)}
    assert str(q["runs"]) == "0"


def test_requires_inputs(project):
    with pytest.raises(SystemExit) as e:
        load_step("04_table").main([TAXON])
    assert "runinfo.tsv" in str(e.value)
