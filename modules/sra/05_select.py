"""05 select: 按数据类型/平台/文库布局筛选, 输出可直接交给 kingfisher 的 run 清单 (本工具不下载).

用法:
  python3 yzz.py sra 05 <Taxon>                                   # 默认 shallow_WGS,deep_WGS,RNA-Seq; PAIRED; 每组前 3
  python3 yzz.py sra 05 <Taxon> --type RNA-Seq --top 1 --tag rna
  python3 yzz.py sra 05 <Taxon> --platform ILLUMINA,DNBSEQ --layout ALL
  python3 yzz.py sra 05 <Taxon> --per run                         # 旧脚本行为: 按 run 取前 N
分组 = TaxID × BioProject × 数据类型, 按数据量从大到小取 --top 个样本, 并带上样本的全部 run.
输出: selected_<tag>.tsv, run_list_<tag>.txt
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import pandas as pd  # noqa: E402
from classify import select_samples  # noqa: E402
from common import data_dir, read_tsv, summary, write_tsv  # noqa: E402


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    p.add_argument("--type", default="shallow_WGS,deep_WGS,RNA-Seq")
    p.add_argument("--platform")
    p.add_argument("--layout", default="PAIRED", choices=["PAIRED", "SINGLE", "ALL"])
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--per", default="sample", choices=["sample", "run"])
    p.add_argument("--tag", default="default")
    a, _ = p.parse_known_args(argv)
    d = data_dir(a.taxon, "sra")
    types = [x.strip() for x in a.type.split(",") if x.strip()]
    plats = [x.strip() for x in a.platform.split(",")] if a.platform else None
    if a.per == "run":
        sel = select_samples(None, types, plats, a.layout, a.top, per="run", runs=read_tsv(d / "table.tsv"))
    else:
        sel = select_samples(read_tsv(d / "samples.tsv"), types, plats, a.layout, a.top)
    runs = []
    for x in sel.get("runs", pd.Series(dtype=str)):
        runs += [r for r in str(x).split(";") if r and r not in runs]
    write_tsv(sel, d / f"selected_{a.tag}.tsv")
    out = d / f"run_list_{a.tag}.txt"
    out.write_text("".join(r + "\n" for r in runs))
    gb = pd.to_numeric(sel.get("total_Gb", pd.Series(dtype=str)), errors="coerce").sum()
    summary("05_select", [f"{a.type} | {a.layout} | 每组前 {a.top} 个{'样本' if a.per == 'sample' else ' run'}",
                          f"{len(sel)} 个{'样本' if a.per == 'sample' else ' run'}, {len(runs)} run, 约 {gb:.1f} Gb",
                          f"-> {out}",
                          f"下载示例: kingfisher get --run-identifiers-list {out} -m ena-ftp aws-http prefetch -f fastq.gz"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
