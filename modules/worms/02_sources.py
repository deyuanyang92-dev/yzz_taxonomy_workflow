"""02 来源: 每个名称在 WoRMS 的全部文献来源 (含 use 类型) -> sources.tsv

输入: names.tsv (含原始组合 AphiaID, 原始组合不在子树内时也一并查)
输出: 02_原始数据/worms/sources.tsv  每行 = 一个名称 x 一条来源
字段: aphia_id, source_id, use (original description / redescription / new combination reference /
      source of synonymy / additional source / ...), reference, page (该名称所在页码/图), doi, link, fulltext, worms_source_url
用法: python3 02_sources.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import clean, data_dir, read_tsv, summary, write_tsv
from worms import client, pmap


def sources(aid):
    return [{"aphia_id": aid, "source_id": str(x.get("source_id") or ""), "use": clean(x.get("use")),
             "reference": clean(x.get("reference")), "page": clean(x.get("page")), "doi": clean(x.get("doi")),
             "link": clean(x.get("link")), "fulltext": clean(x.get("fulltext")), "worms_source_url": clean(x.get("url"))}
            for x in (client().sources(int(aid)) or [])]


def main(taxon):
    out = data_dir(taxon, "worms")
    n = read_tsv(out / "names.tsv")
    ids = sorted(set(n.aphia_id) | set(x for x in n.original_name_aphia_id if x))
    res = pmap(sources, ids)
    failed = [a for a, r in zip(ids, res) if r is None]
    s = pd.DataFrame([row for r in res if r for row in r])
    write_tsv(s, out / "sources.tsv")
    summary("02_sources", [f"{len(ids)} AphiaIDs -> {len(s)} source links; {s.source_id.nunique()} distinct sources; failed {len(failed)}",
                           "uses: " + "; ".join(f"{k} {v}" for k, v in s.use.value_counts().head(6).items()),
                           f"-> {out / 'sources.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
