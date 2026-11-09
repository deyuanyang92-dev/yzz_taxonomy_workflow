"""genbank module output folders: one folder per software; inside gb2taxonomy/ one numbered folder per step.
Native output of each tool is kept unchanged. README.txt = English + Chinese notes.

  <genbank>/<Taxon>/
    README.txt
    gb2taxonomy/
      01_download/<tag>/   g2t-download: NCBI GenBank records (.gb) + manifest.json   (01_download)
      02_g2t/<tag>/        g2t native output                                          (02_g2t)
      03_results/          Excel tables, fasta/<tag>/<gene>.fasta, matrix_<tag>.tsv   (03_export, from g2t output)
      04_curation/         g2t-curate template <tag>_corrections.xlsx / user table B + curated Excel C  (04_curate)
    mitom/<tag>/           MitoM native output (-o)                                   (05_mitoz)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from common import data_dir  # noqa: E402

STEPS = {"gb": "gb2taxonomy/01_download", "g2t": "gb2taxonomy/02_g2t", "out": "gb2taxonomy/03_results",
         "curation": "gb2taxonomy/04_curation", "mitom": "mitom"}
README = """GenBank molecular data ({taxon}) - yzz workflow, genbank module. One folder per software.

gb2taxonomy\\                 gb2taxonomy (g2t) - download, sort by gene, results, curation
  01_download\\<tag>\\        g2t-download: NCBI GenBank records (.gb) + manifest.json
                              (NCBI 原始记录; tag: markers = 标记基因 COI/16S/18S/28S/H3/ITS...; mitogenome = 线粒体全基因组)
  02_g2t\\<tag>\\             g2t native output (g2t 原始输出, 未改动)
  03_results\\                tables made from the g2t output: <Taxon>_GenBank_<tag>_<date>.xlsx,
                              fasta\\<tag>\\<gene>.fasta, matrix_<tag>.tsv (结果: Excel 总表, 按基因 FASTA - 先看这里)
  04_curation\\               g2t-curate: <tag>_corrections.xlsx template (or your own table) -> curated Excel
                              (元数据校正: 改模板或放自己的表, 运行 genbank 04 生成校正后 Excel)
mitom\\<tag>\\                MitoM native output (MitoM 原始输出, 未改动; 见其中 README.txt)

Note: GenBank species names are the submitters' identifications, not verified. (GenBank 物种名未核实)
"""


def step_dir(taxon, key, tag=""):
    d = data_dir(taxon, "genbank") / STEPS[key]
    if tag:
        d = d / tag
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_readme(taxon):
    (data_dir(taxon, "genbank") / "README.txt").write_text("﻿" + README.format(taxon=taxon).replace("\n", "\r\n"),
                                                          encoding="utf-8")
