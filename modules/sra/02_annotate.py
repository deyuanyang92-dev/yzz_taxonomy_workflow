"""02 annotate: 照 kingfisher annotate 的做法, 取 efetch db=sra 完整 XML 中的标题、摘要、提交单位与样本全部属性.

用法: python3 yzz.py sra 02 <Taxon>
输入: runinfo.tsv (01)   输出: annotate.tsv (以 Run 为键), annotate_missing.txt
XML 中缺失的 run 超过 1% 时退出码 1.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import pandas as pd  # noqa: E402
from common import ROOT, data_dir, read_tsv, summary, write_tsv  # noqa: E402
from eutils import Eutils, EutilsError, load_identity  # noqa: E402
from parse import parse_sra_packages  # noqa: E402

BATCH = 200


def main(argv, eutils=None):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    a, _ = p.parse_known_args(argv)
    eu = eutils or Eutils(*load_identity(ROOT))
    d = data_dir(a.taxon, "sra")
    runs = [r for r in read_tsv(d / "runinfo.tsv").get("Run", pd.Series(dtype=str)) if r]
    mf = d / "manifest.json"
    manifest = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    rows = []
    try:
        if manifest.get("mode") == "taxon" and manifest.get("term"):
            # 类群模式: 复用 01 的检索式, 每页 500 (比按 accession 分批快约一倍)
            r = eu.esearch("sra", manifest["term"])
            for page in eu.efetch_history("sra", r["webenv"], r["query_key"], r["count"], page=500):
                rows += parse_sra_packages(page)
        else:
            for i in range(0, len(runs), BATCH):
                r = eu.esearch("sra", " OR ".join(f"{x}[accn]" for x in runs[i:i + BATCH]))
                for page in eu.efetch_history("sra", r["webenv"], r["query_key"], r["count"], page=BATCH):
                    rows += parse_sra_packages(page)
    except EutilsError as e:
        print(f"[02_annotate] 失败: {e}")
        return 1
    want = set(runs)
    df = pd.DataFrame([x for x in rows if x["Run"] in want])
    df = df.drop_duplicates("Run") if len(df) else pd.DataFrame(columns=["Run"])
    missing = [x for x in runs if x not in set(df["Run"])]
    (d / "annotate_missing.txt").write_text("".join(x + "\n" for x in missing))
    write_tsv(df, d / "annotate.tsv")
    bad = len(runs) and len(missing) / len(runs) > 0.01
    lines = [f"{len(df)}/{len(runs)} run 取到注释, {df.shape[1] - 1} 列 (含样本属性)", f"-> {d / 'annotate.tsv'}"]
    if missing:
        lines.append(f"{'错误' if bad else '警告'}: {len(missing)} 个 run 无 XML 记录, 见 annotate_missing.txt")
    summary("02_annotate", lines)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
