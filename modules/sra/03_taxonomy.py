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
import pandas as pd  # noqa: E402
from common import ROOT, data_dir, read_tsv, summary, write_tsv  # noqa: E402
from eutils import Eutils, EutilsError, load_identity  # noqa: E402
from parse import RANKS, norm_taxid, parse_taxonomy_xml  # noqa: E402

BATCH = 200


def main(argv, eutils=None):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    a, _ = p.parse_known_args(argv)
    eu = eutils or Eutils(*load_identity(ROOT))
    d = data_dir(a.taxon, "sra")
    ids = []
    for x in read_tsv(d / "runinfo.tsv").get("TaxID", pd.Series(dtype=str)):
        x = norm_taxid(x)
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
    df = pd.DataFrame(rows, columns=cols).drop_duplicates("TaxID")
    df = df[df["TaxID"].isin(ids)]
    missing = [x for x in ids if x not in set(df["TaxID"])]
    (d / "taxonomy_missing.txt").write_text("".join(x + "\n" for x in missing))
    write_tsv(df, d / "taxonomy.tsv")
    lines = [f"{len(df)}/{len(ids)} 个 TaxID 取到阶元; 科 {df['family'].replace('', pd.NA).nunique()} 个, "
             f"种级 {int((df['rank_derived'] == 'species').sum())} 个", f"-> {d / 'taxonomy.tsv'}"]
    if missing:
        lines.append(f"警告: {len(missing)} 个 TaxID 查不到, 见 taxonomy_missing.txt")
    summary("03_taxonomy", lines)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
