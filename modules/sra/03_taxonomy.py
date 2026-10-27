"""03 taxonomy: TaxID -> 门/纲/目/科/属/种 (NCBI Taxonomy, 不依赖 ete3 本地库).

用法: python3 yzz.py sra 03 <Taxon>
输入: runinfo.tsv   输出: taxonomy.tsv (以 TaxID 为键), taxonomy_missing.txt
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "lib"))
from common import ROOT, data_dir, summary  # noqa: E402
from eutils import Eutils, EutilsError, load_identity  # noqa: E402
from parse import RANKS, norm_taxid, parse_taxonomy_xml  # noqa: E402
from tsv import read_tsv, write_tsv  # noqa: E402

BATCH = 200


def main(argv, eutils=None):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    a, _ = p.parse_known_args(argv)
    eu = eutils or Eutils(*load_identity(ROOT))
    d = data_dir(a.taxon, "sra")
    ids = []
    for r in read_tsv(d / "runinfo.tsv")[1]:
        x = norm_taxid(r.get("TaxID"))
        if x and x not in ids:
            ids.append(x)
    rows = []
    try:
        for i in range(0, len(ids), BATCH):
            rows += parse_taxonomy_xml(eu.efetch_ids("taxonomy", ids[i:i + BATCH]))
    except EutilsError as e:
        print(f"[03_taxonomy] 失败: {e}")
        return 1
    cols = ["TaxID", "rank_derived", *RANKS]
    want, got = set(ids), {}
    for r in rows:
        if r["TaxID"] in want and r["TaxID"] not in got:
            got[r["TaxID"]] = r
    df = list(got.values())
    missing = [x for x in ids if x not in got]
    (d / "taxonomy_missing.txt").write_text("".join(x + "\n" for x in missing))
    write_tsv(d / "taxonomy.tsv", cols, df)
    lines = [f"{len(df)}/{len(ids)} 个 TaxID 取到阶元; 科 {len({r['family'] for r in df} - {''})} 个, "
             f"种级 {sum(r['rank_derived'] == 'species' for r in df)} 个", f"-> {d / 'taxonomy.tsv'}"]
    if missing:
        lines.append(f"警告: {len(missing)} 个 TaxID 查不到, 见 taxonomy_missing.txt")
    summary("03_taxonomy", lines)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
