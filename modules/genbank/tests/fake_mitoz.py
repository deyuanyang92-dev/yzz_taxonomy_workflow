#!/usr/bin/env python3
"""Stand-in for `mitoz annotate` used by check_mitoz.py: writes <workdir>/<prefix>.result/<prefix>.gbf
with a placeholder organism and one cox1 CDS, like MitoZ output, so batch_mitoz.py can run without MitoZ."""
import sys
from pathlib import Path

from Bio import SeqIO
from Bio.SeqFeature import FeatureLocation, SeqFeature

a = sys.argv[1:]


def arg(k):
    return a[a.index(k) + 1]


wd, pre = Path(arg("--workdir")), arg("--outprefix")
r = next(SeqIO.parse(arg("--fastafiles"), "fasta"))
r.annotations["molecule_type"] = "DNA"
r.features = [SeqFeature(FeatureLocation(0, len(r)), type="source", qualifiers={"organism": ["Test sp."]}),
              SeqFeature(FeatureLocation(100, 400, 1), type="gene", qualifiers={"gene": ["cox1"]}),
              SeqFeature(FeatureLocation(100, 400, 1), type="CDS", qualifiers={"gene": ["cox1"], "transl_table": ["5"]})]
(wd / f"{pre}.result").mkdir(parents=True, exist_ok=True)
SeqIO.write(r, wd / f"{pre}.result" / f"{pre}.gbf", "genbank")
