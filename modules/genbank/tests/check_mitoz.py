"""genbank 05_mitoz 回归检查 (不需要真实 MitoZ: 用 fake_mitoz.py 代替).
用法: python3 modules/genbank/tests/check_mitoz.py   全部 PASS 才算通过.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

ROOT = Path(__file__).resolve().parents[3]
TAXON = "_check_mitoz"
PROJ = ROOT / "projects" / TAXON
fails = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def run05(*extra):
    return subprocess.run([sys.executable, str(ROOT / "yzz.py"), "genbank", "05", TAXON, *extra],
                          capture_output=True, text=True, cwd=ROOT)


def record(acc, organism, intron, seq):
    r = SeqRecord(Seq(seq), id=acc, name=acc.split(".")[0],
                  description=f"{organism} mitochondrion, complete genome")
    r.annotations.update(molecule_type="DNA", topology="circular", organism=organism, source=organism)
    r.features = [SeqFeature(FeatureLocation(0, 1200), type="source", qualifiers={"organism": [organism]})]
    if intron:
        r.features.append(SeqFeature(FeatureLocation(500, 700, 1), type="intron", qualifiers={"gene": ["cox1"]}))
    return r


try:
    shutil.rmtree(PROJ, ignore_errors=True)
    gb = PROJ / "02_原始数据" / "genbank" / "gb" / "mitogenome"
    gb.mkdir(parents=True)
    SeqIO.write([record("XX000001.1", "Perinereis aibuhitensis", True, "ACGT" * 300),
                 record("XX000002.1", "Perinereis nuntia", False, "AACGTT" * 200),
                 # identical sequence to XX000002.1 -> batch_mitoz.py drops it (dedup_report.tsv)
                 record("XX000003.1", "Perinereis nuntia", False, "AACGTT" * 200)], gb / "batch_0001.gb", "genbank")

    if not shutil.which("mitoz") and not (ROOT / "config" / "mitoz.json").exists():
        r = run05()
        check("no MitoZ -> skipped, exit 0", r.returncode == 0 and "跳过" in r.stdout and "MitoZ" in r.stdout)

    tmp = Path(tempfile.mkdtemp())
    exe = tmp / "mitoz"
    shutil.copy(Path(__file__).with_name("fake_mitoz.py"), exe)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    # --gene / --minlen come from `genbank all` and must not reach batch_mitoz.py
    r = run05("--mitoz_path", str(exe), "--gene", "COI", "--minlen", "500",
              "--threads", "1", "--max_tasks", "1", "--scheduler_backend", "threads")
    out = PROJ / "02_原始数据" / "genbank" / "mitoz" / "mitogenome"
    check("run OK, exit 0", r.returncode == 0 and "mitogenome: OK" in r.stdout)
    finals = sorted(p.name for p in (out / "04.final_gb").glob("*.gbf"))
    check("one final .gbf per record", finals == ["XX000001.1.gbf", "XX000002.1.gbf"])
    check("identical sequence deduplicated and reported",
          "XX000003.1" in (out / "dedup_report.tsv").read_text())
    check("all.final.gbf merged", (out / "all.final.gbf").read_text().count("LOCUS") == 2)
    txt = (out / "04.final_gb" / "XX000001.1.gbf").read_text()
    check("NCBI organism restored (no MitoZ placeholder)",
          "Perinereis aibuhitensis" in txt and "Test sp." not in txt)
    check("MitoZ annotation present", "/gene=\"cox1\"" in txt)
    check("internal-ID intermediates deleted",
          not any(out.glob("00.*")) and not any(out.glob("01.*")) and not any(out.glob("03.*")))
    check("summary reports intron records", "原记录含 intron 1 条" in r.stdout)
    check("original .gb untouched", (gb / "batch_0001.gb").read_text().count("intron") == 1)

    # intron step (mito_intron.py, MFannot method): Metridium senile COX1 + ND5 group I introns
    ibin = Path("/root/miniconda3/envs/mitointron/bin")
    fixture = ROOT / "temp_scripts" / "Mitoz-annotate" / "tests" / "data" / "NC_000933.gb"
    if (ibin / "exonerate").exists() and fixture.exists():
        for f in gb.glob("*.gb"):
            f.unlink()
        shutil.copy(fixture, gb / "batch_0001.gb")
        shutil.rmtree(out, ignore_errors=True)
        r = run05("--mitoz_path", str(exe), "--intron_bin", str(ibin), "--genetic_code", "4",
                  "--threads", "1", "--max_tasks", "1", "--scheduler_backend", "threads")
        check("intron step adds 2 introns in 2 genes", "mito_intron 补 intron 2 个 / 2 个基因" in r.stdout)
        rep = (out / "intron_report.tsv").read_text()
        check("intron report: cox1 + nad5, group I, NCBI coordinates (after reorientation)",
              all(x in rep.lower() for x in ("cox1\t", "nad5\t", "group i intron"))
              and "3956\t4808" in rep and "7544\t9224" in rep)
        check("final GenBank has 2 intron features",
              (out / "all.final.gbf").read_text().count("\n     intron ") == 2)
    else:
        print("SKIP intron step (no exonerate in /root/miniconda3/envs/mitointron)")
    shutil.rmtree(tmp, ignore_errors=True)
finally:
    if not os.environ.get("KEEP"):  # KEEP=1 保留测试项目以便排查
        shutil.rmtree(PROJ, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else f'{len(fails)} FAIL'}")
sys.exit(1 if fails else 0)
