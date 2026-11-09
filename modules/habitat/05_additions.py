"""05 新增记录: 合并子代理从 yes/maybe 文献抽取的物种记录 -> additions.tsv (附 WoRMS 校正)

子代理按 EXTRACT_PROMPT.md 读 extract/todo_*.tsv 的文献, 写 extract/found_*.tsv, 列:
  species, authority, habitat_cn (纯淡水/半盐水/均可/陆生), habitat_evidence (原文短句), salinity,
  locality, record_type (new species / new record / habitat evidence / revision), reference, doi,
  work_id, page, confidence (确证/待核)
用法:
  python3 05_additions.py <Taxon> --todo [--chunk 15]   把 yes/maybe 文献分块写 extract/todo_N.tsv
  python3 05_additions.py <Taxon>                        合并 found_*.tsv -> additions.tsv
"""
import argparse, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
sys.path.insert(0, str(HERE))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv
from wormsmatch import match

COLS = ["species", "authority", "habitat_cn", "habitat_evidence", "salinity", "locality", "record_type",
        "reference", "doi", "work_id", "page", "confidence"]
HABITATS = {"纯淡水", "半盐水", "均可", "陆生", "排除"}   # 排除 = 主线程裁定不符合收录口径


def todo(d, chunk, decisions=("yes", "maybe")):
    works = read_tsv(d / "works.tsv")
    ex = d / "extract"
    ex.mkdir(exist_ok=True)
    done = set()
    for p in ex.glob("done_ids_*.txt"):
        done |= set(p.read_text().split())
    for p in ex.glob("todo_*.tsv"):            # already assigned to a chunk (maybe still being processed)
        done |= set(read_tsv(p)["id"])
    w = works[works["decision"].isin(list(decisions)) & ~works["id"].isin(done)]
    w = w.sort_values(["decision", "year"], ascending=[False, True])
    old = max([int(p.stem.split("_")[1]) for p in ex.glob("todo_*.tsv")] or [0])
    for i in range(0, len(w), chunk):
        n = old + i // chunk + 1
        write_tsv(w.iloc[i:i + chunk][["id", "doi", "year", "title", "venue", "abstract", "decision", "reason"]],
                  ex / f"todo_{n}.tsv")
    summary("05_additions", [f"{len(w)} 篇 {'/'.join(decisions)} 待抽取 -> extract/todo_{old + 1}..{old + (len(w) + chunk - 1) // chunk}.tsv"])


def merge(d):
    ex = d / "extract"
    parts = [read_tsv(p) for p in sorted(ex.glob("found_*.tsv"))]
    parts = [p for p in parts if len(p)]
    if not parts:
        raise SystemExit("extract/ 下没有 found_*.tsv")
    a = pd.concat(parts, ignore_index=True)
    for c in COLS:
        if c not in a:
            a[c] = ""
    a = a[COLS]
    bad = ~a["habitat_cn"].isin(HABITATS)
    m = pd.DataFrame(match(a["species"]))
    a = pd.concat([a.reset_index(drop=True), m], axis=1)
    # same taxon + same paper but different habitat class (parallel agents disagree) -> adjudication list
    a["_ref"] = a["doi"].where(a["doi"] != "", a["reference"].str[:60])
    a["_tax"] = a["accepted_aphia_id"].where(a["accepted_aphia_id"] != "", a["species"])
    g = a.groupby(["_tax", "_ref"])["habitat_cn"].nunique()
    conf = a.set_index(["_tax", "_ref"]).loc[g[g > 1].index].reset_index() if (g > 1).any() else a.iloc[0:0]
    write_tsv(conf[["species", "habitat_cn", "salinity", "habitat_evidence", "reference", "doi", "work_id"]],
              d / "additions_conflicts.tsv")
    # adjudications by the main thread: extract/adjudicated.tsv (species, doi, habitat_cn, note) overrides
    adj = read_tsv(ex / "adjudicated.tsv", required=False)
    if len(adj):
        for r in adj.to_dict("records"):
            hit = (a["species"] == r["species"]) & (a["doi"] == r["doi"])
            a.loc[hit, "habitat_cn"] = r["habitat_cn"]
            a.loc[hit, "habitat_evidence"] = a.loc[hit, "habitat_evidence"] + " [裁定: " + r["note"] + "]"
    a = a.drop(columns=["_ref", "_tax"])
    write_tsv(a, d / "additions.tsv")
    summary("05_additions", [f"{len(a)} 条记录, {a['species'].nunique()} 个名称; 生境值不合规 {bad.sum()}; "
                             f"WoRMS 未匹配 {(a['worms_note'].str.startswith('no WoRMS')).sum()} -> additions.tsv",
                             f"同种同文献生境冲突 {len(conf)} 行 -> additions_conflicts.tsv (裁定写 extract/adjudicated.tsv)"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("taxon")
    ap.add_argument("--todo", action="store_true")
    ap.add_argument("--chunk", type=int, default=15)
    ap.add_argument("--decisions", default="yes,maybe", help="逗号分隔; 额度紧时先 yes")
    a = ap.parse_args()
    d = data_dir(a.taxon, "habitat")
    todo(d, a.chunk, a.decisions.split(",")) if a.todo else merge(d)


if __name__ == "__main__":
    main()
