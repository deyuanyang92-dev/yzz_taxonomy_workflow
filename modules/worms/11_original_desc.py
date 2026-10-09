"""11 原始文献 (转换层)/重描述: 每个名称的原始描述 (缺失时回退到原始组合) + 重描述等 -> original_descriptions.tsv

输入: names.tsv, sources.tsv, refs.tsv
输出: 02_原始数据/worms/original_descriptions.tsv  每行 = 一个名称
规则: 原始描述 = WoRMS 来源 use="original description"; 本名称没有则取 original_name_aphia_id 上的
      (转属名称的原始文献挂在原始组合上). 多条用 ' || ' 连接.
      重描述 = use="redescription"; 另列 new combination reference / source of synonymy.
注意: names.tsv 的 worms_taxonomic_citation 是 WoRMS 条目的引用格式, 不是原始文献.
用法: python3 11_original_desc.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv

OD_FIELDS = ["authors", "year", "title", "journal_or_publisher", "volume_issue_pages", "doi_url", "link",
             "zoobank_lsid", "open_access", "source_id", "worms_source_url"]


def main(taxon):
    out = data_dir(taxon, "worms")
    n, s, f = read_tsv(out / "names.tsv"), read_tsv(out / "sources.tsv"), read_tsv(out / "refs.tsv")
    s = s.merge(f.drop(columns=["link", "doi", "worms_source_url"], errors="ignore"), on="source_id", how="left")
    by = {k: g for k, g in s.groupby("aphia_id")}
    j = lambda g, c: " || ".join(x for x in g[c] if x)
    cite = lambda g: " || ".join(f"{c} [pages for this taxon: {p}]" if p else c for c, p in zip(g.citation, g.page))

    rows = []
    for r in n.itertuples():
        own = by.get(r.aphia_id, pd.DataFrame(columns=s.columns))
        od = own[own.use == "original description"]
        frm = "this name" if len(od) else ""
        if not len(od) and r.original_name_aphia_id and r.original_name_aphia_id != r.aphia_id:
            g = by.get(r.original_name_aphia_id, pd.DataFrame(columns=s.columns))
            od = g[g.use == "original description"]
            frm = "original combination" if len(od) else ""
        red = own[own.use == "redescription"]
        rows.append({
            "aphia_id": r.aphia_id, "scientific_name": r.scientific_name, "authority": r.authority,
            "od_taken_from": frm, "od_citation": " || ".join(od.citation), "od_pages_for_taxon": j(od, "page"),
            **{f"od_{c}": j(od, c) for c in OD_FIELDS},
            "redescriptions": cite(red), "redescription_source_ids": j(red, "source_id"),
            "new_combination_refs": cite(own[own.use == "new combination reference"]),
            "source_of_synonymy_refs": cite(own[own.use == "source of synonymy"]),
            "n_sources_total": str(len(own)),
        })
    o = pd.DataFrame(rows)
    write_tsv(o, out / "original_descriptions.tsv")
    sp = o[n["rank"].isin(["Species", "Subspecies"]).values]
    summary("11_original_desc", [f"species-level {len(sp)}: original description {(sp.od_citation != '').sum()} "
                                 f"(this name {(sp.od_taken_from == 'this name').sum()}, original combination {(sp.od_taken_from == 'original combination').sum()}); "
                                 f"redescriptions {(sp.redescriptions != '').sum()}", f"-> {out / 'original_descriptions.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
