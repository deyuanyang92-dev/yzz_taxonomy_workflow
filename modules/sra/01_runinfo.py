"""01 RunInfo: 得到 NCBI SraRunInfo 表 (原列名、原值), 三种输入任选其一.

用法:
  python3 yzz.py sra 01 Polynoidae                      # 类群名 -> txid<id>[Organism:exp], 分页取全
  python3 yzz.py sra 01 Polynoidae --query 'WGS[Strategy]'   # 追加 Entrez 子句
  python3 yzz.py sra 01 <项目名> --runs list.txt          # SRR/ERR/DRR 列表 (一行一个)
  python3 yzz.py sra 01 <项目名> --runinfo SraRunInfo.csv  # 网页下载的 RunInfo
输出: 02_原始数据/sra/runinfo.tsv, manifest.json, (runs_not_found.txt)
核对: 类群模式下 唯一 Experiment 数 必须 = esearch Count (db=sra 按 experiment 计数).
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import pandas as pd  # noqa: E402
from common import ROOT, TODAY, data_dir, summary, write_tsv  # noqa: E402
from eutils import Eutils, EutilsError, load_identity, resolve_taxid  # noqa: E402
from parse import parse_runinfo  # noqa: E402

BATCH = 200


def fetch(eu, term):
    r = eu.esearch("sra", term)
    rows = []
    for page in eu.efetch_history("sra", r["webenv"], r["query_key"], r["count"], rettype="runinfo", retmode="text"):
        rows += parse_runinfo(page)
    return r["count"], rows


def read_runs(path):
    seen = []
    for line in Path(path).read_text(encoding="utf-8-sig").split():
        acc = line.strip()
        if acc and acc not in seen:
            seen.append(acc)
    return seen


def main(argv, eutils=None):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    p.add_argument("--taxid")
    p.add_argument("--query")
    p.add_argument("--runs")
    p.add_argument("--runinfo")
    p.add_argument("--max-experiments", type=int, default=200000)
    a, _ = p.parse_known_args(argv)
    eu = eutils or Eutils(*load_identity(ROOT))
    out = data_dir(a.taxon, "sra")
    m = {"taxon": a.taxon, "date": TODAY, "taxid": "", "term": "", "esearch_count": None,
         "not_found": 0, "problems": []}
    try:
        if a.runinfo:
            m["mode"] = "runinfo"
            rows = parse_runinfo(Path(a.runinfo).read_text(encoding="utf-8-sig", errors="replace"))
        elif a.runs:
            m["mode"] = "runs"
            want = read_runs(a.runs)
            rows, total = [], 0
            for i in range(0, len(want), BATCH):
                n, got = fetch(eu, " OR ".join(f"{x}[accn]" for x in want[i:i + BATCH]))
                total += n
                rows += got
            rows = [r for r in rows if r["Run"] in set(want)]
            missing = [x for x in want if x not in {r["Run"] for r in rows}]
            m["esearch_count"], m["not_found"] = total, len(missing)
            (out / "runs_not_found.txt").write_text("".join(x + "\n" for x in missing))
            if missing:
                m["problems"].append(f"{len(missing)} 个 run 在 NCBI SRA 查不到, 见 runs_not_found.txt")
        else:
            m["mode"] = "taxon"
            m["taxid"] = a.taxid or resolve_taxid(eu, a.taxon)
            term = f"txid{m['taxid']}[Organism:exp]" + (f" AND ({a.query})" if a.query else "")
            m["term"] = term
            n = eu.esearch("sra", term)["count"]
            m["esearch_count"] = n
            if n > a.max_experiments:
                print(f"[01_runinfo] {term} 有 {n} 条 experiment, 超过 --max-experiments {a.max_experiments}; "
                      f"确认要全部获取请加大该值")
                return 2
            n, rows = fetch(eu, term)
    except EutilsError as e:
        print(f"[01_runinfo] 失败: {e}")
        return 1

    df = pd.DataFrame(rows).drop_duplicates("Run") if rows else pd.DataFrame(columns=["Run", "Experiment"])
    m["runs"] = int(len(df))
    m["experiments"] = int(df["Experiment"].nunique()) if "Experiment" in df else 0
    m["empty_bioproject"] = int((df.get("BioProject", pd.Series(dtype=str)).fillna("") == "").sum())
    if m["mode"] == "taxon" and m["experiments"] != m["esearch_count"]:
        m["problems"].append(f"唯一 Experiment {m['experiments']} != esearch Count {m['esearch_count']}")
    m["ok"] = not (m["mode"] == "taxon" and m["problems"])
    write_tsv(df, out / "runinfo.tsv")
    (out / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"{m['mode']}: {m['term'] or a.runs or a.runinfo}",
             f"{m['experiments']} experiment / {m['runs']} run; BioProject 为空 {m['empty_bioproject']}",
             f"-> {out / 'runinfo.tsv'}"]
    lines += [f"警告: {x}" for x in m["problems"]]
    summary("01_runinfo", lines)
    return 0 if m["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
