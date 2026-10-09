"""03 文献: 来源结构化拆分 (WoRMS sourcedetails 页的分项字段, 不靠正则猜) -> refs.tsv

输入: sources.tsv (去重 source_id)
输出: 02_原始数据/worms/refs.tsv  每行 = 一篇文献
字段: source_id, authors, year, title, journal_or_publisher, volume_issue_pages (WoRMS 'Suffix'), doi, doi_url, link,
      zoobank_lsid, source_type, open_access, fulltext_file, note, geographical/bibliographical/taxonomic terms, abstract, citation (规范完整引文), worms_source_url
另: 页面全部原始字段原样保留在 'worms: <标签>' 列 (提取层原则).
用法: python3 03_refs.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv
from worms import WEB, pmap, source_details


def citation(r):
    if r["authors"] and r["title"]:
        c = f"{r['authors']}. ({r['year']}). {r['title']}. {r['journal_or_publisher']}.".replace("..", ".")
        c += f" {r['volume_issue_pages']}." if r["volume_issue_pages"] else ""
    else:
        c = r["reference_worms"]
    return c + (f" DOI: {r['doi_url']}" if r["doi_url"] else "")


def main(taxon):
    out = data_dir(taxon, "worms")
    s = read_tsv(out / "sources.tsv")
    first = s.drop_duplicates("source_id").set_index("source_id")
    ids = [i for i in first.index if i]
    det = pmap(source_details, ids)
    rows = []
    for sid, d in zip(ids, det):
        d = d or {}
        doi = first.at[sid, "doi"] or d.get("DOI", "")
        r = {"source_id": sid, "authors": d.get("Authors", ""), "year": d.get("Year", ""), "title": d.get("Title", ""),
             "journal_or_publisher": d.get("Journal", ""), "volume_issue_pages": d.get("Suffix", ""),
             "doi": doi, "doi_url": f"https://doi.org/{doi}" if doi and not doi.startswith("http") else doi,
             "link": first.at[sid, "link"] or d.get("Link", ""), "zoobank_lsid": d.get("Zoobank LSID") or d.get("LSID", ""),
             "source_type": d.get("Type", ""), "open_access": d.get("_open_access", ""),
             "fulltext_file": d.get("Full text") or d.get("FullText", ""), "note": d.get("Note", ""),
             "geographical_terms": d.get("Geographical terms", ""), "bibliographical_terms": d.get("Bibliographical term", ""),
             "taxonomic_terms": d.get("Taxonomic terms", ""), "abstract": d.get("Abstract", ""),
             "reference_worms": first.at[sid, "reference"], "worms_source_url": f"{WEB}?p=sourcedetails&id={sid}",
             "fetch_error": "" if det else "Y",
             **{f"worms: {k}": v for k, v in d.items() if not k.startswith("_")}}   # sourcedetails 页全部原始字段
        r["citation"] = citation(r)
        rows.append(r)
    f = pd.DataFrame(rows)
    write_tsv(f, out / "refs.tsv")
    has = lambda c: int((f[c] != "").sum())
    summary("03_refs", [f"{len(f)} references; with title {has('title')}; journal {has('journal_or_publisher')}; DOI {has('doi')}; "
                        f"ZooBank {has('zoobank_lsid')}; open access {has('open_access')}", f"-> {out / 'refs.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
