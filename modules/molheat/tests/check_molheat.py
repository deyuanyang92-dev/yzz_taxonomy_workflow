"""python3 modules/molheat/tests/check_molheat.py  — name typesetting (Python == R), counting rules, both plotters."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from taxname import abbreviate, segments  # noqa: E402

RSCRIPT = shutil.which("Rscript") or "/root/miniconda3/envs/rmap/bin/Rscript"
fails = 0


def check(ok, msg):
    global fails
    print(("PASS " if ok else "FAIL ") + msg)
    fails += not ok


CASES = {
    "Marphysa sanguinea": [("Marphysa sanguinea", True)],
    "Marphysa sp.": [("Marphysa ", True), ("sp.", False)],
    "Marphysa sp. E HA-2019": [("Marphysa ", True), ("sp. E HA-2019", False)],
    "Marphysa cf. hentscheli JZ-2010": [("Marphysa ", True), ("cf. ", False), ("hentscheli ", True), ("JZ-2010", False)],
    "Marphysa aff. sanguinea": [("Marphysa ", True), ("aff. ", False), ("sanguinea", True)],
    "Eunicidae und.": [("Eunicidae und.", False)],
    "Eunicidae environmental sample": [("Eunicidae environmental sample", False)],
    "Nereis (Neanthes) japonica Izuka, 1908": [("Nereis (Neanthes) japonica ", True), ("Izuka, 1908", False)],
    "M. abiuma": [("M. abiuma", True)],
    "Marphysa sp. BOLD:AAY5846": [("Marphysa ", True), ("sp. BOLD:AAY5846", False)],
}
for n, exp in CASES.items():
    check(segments(n) == exp, f"python typeset {n!r}")
check(abbreviate("Marphysa aegypti") == "M. aegypti" and abbreviate("Marphysa sp.") == "Marphysa sp.", "abbreviate genus")

if Path(RSCRIPT).exists():
    r = subprocess.run([RSCRIPT, str(HERE / "molheat.R"), "--print-labels", *CASES], capture_output=True, text=True)
    lines = [x.strip() for x in r.stdout.splitlines() if "=>" in x]
    py = [f"{n} => " + " | ".join(f"{'I' if it else 'R'}:'{t}'" for t, it in segments(n)) for n in CASES]
    check(lines == py, "R typesetting == Python typesetting")
else:
    print("SKIP R (Rscript not found)")

with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "gb.tsv").write_text("organism\tgene_type\n" + "\n".join([
        "Marphysa sanguinea\tcoi", "Marphysa sanguinea\tmtgenome", "Marphysa sp. E HA-2019\tcoi",
        "Marphysa cf. hentscheli JZ-2010\t16s", "Eunicidae environmental sample\t16s", "Palola sp.\tits1-its2",
        "Eunice pennata\th3"]) + "\n")
    (d / "sra.tsv").write_text("ScientificName\tcategory_derived\tfamily\tBioSample\tn_runs\ttotal_Gb\n" + "\n".join([
        "Marphysa sanguinea\tRNA-Seq\tEunicidae\tS1\t2\t5", "Marphysa sanguinea\tHi-C\tEunicidae\tS2\t1\t30",
        "Marphysa sanguinea\tshallow_WGS\tEunicidae\tS3\t1\t3", "Marphysa sanguinea\tlong_read_WGS\tEunicidae\tS4\t1\t20",
        "Diopatra cuprea\tshallow_WGS\tOnuphidae\tS5\t1\t3"]) + "\n")
    (d / "asm.tsv").write_text("organism\tlevel\nMarphysa sanguinea\tChromosome\n")
    base = [sys.executable, str(HERE / "01_count.py"), "Eunicidae", "--genbank", str(d / "gb.tsv"),
            "--sra", str(d / "sra.tsv"), "--genome", str(d / "asm.tsv")]
    subprocess.run(base + ["--level", "genus", "--out", str(d / "g")], check=True, capture_output=True)
    subprocess.run(base + ["--level", "species", "--genus", "Marphysa", "--out", str(d / "s")], check=True, capture_output=True)
    import pandas as pd
    g = pd.read_csv(d / "g.tsv", sep="\t", index_col=0)
    s = pd.read_csv(d / "s.tsv", sep="\t", index_col=0)
    check(list(g.index) == ["Eunicidae und.", "Eunice", "Marphysa", "Palola"], f"genus rows {list(g.index)}")
    check(g.loc["Marphysa", "coi"] == 3 and g.loc["Marphysa", "cox2"] == 1 and g.loc["Marphysa", "mt"] == 1,
          "mitogenome counted in mt + mt genes")
    check(g.loc["Marphysa", "lcWGS"] == 1 and g.loc["Marphysa", "RNA"] == 1, "lcWGS = shallow_WGS only (no Hi-C/long-read/deep); RNA = RNA-Seq")
    check(g.loc["Marphysa", "Genome"] == 1, "Genome from assembly table")
    check(g.loc["Palola", "its"] == 1 and "Diopatra" not in g.index, "its rename; SRA family filter")
    check(list(s.index) == ["Marphysa cf. hentscheli", "Marphysa sanguinea", "Marphysa sp."], f"species rows {list(s.index)}")
    for tool, cmd in (("python", [sys.executable, str(HERE / "02_plot.py")]), ("R", [RSCRIPT, str(HERE / "molheat.R")])):
        if tool == "R" and not Path(RSCRIPT).exists():
            continue
        out = d / f"h_{tool}"
        subprocess.run(cmd + ["--matrix", str(d / "g.tsv"), "--matrix", str(d / "s.tsv"), "--highlight", "Marphysa",
                              "--abbreviate-genus", "no", "--abbreviate-genus", "yes", "--values", "no",
                              "--out", str(out)], capture_output=True)
        check((d / f"h_{tool}.pdf").exists() and (d / f"h_{tool}.png").exists(), f"{tool} plot pdf+png")
print("ALL PASS" if not fails else f"{fails} FAIL")
sys.exit(1 if fails else 0)
