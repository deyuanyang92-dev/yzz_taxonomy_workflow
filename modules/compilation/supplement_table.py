"""补充文献 (WoRMS 未挂, 用户提供) -> 写回项目总表 (物种×文献 / 文献清单 / 物种覆盖), 使总表与汇编一致.
由 03_tables 结束时调用; 也可单独: python3 supplement_table.py <项目目录>
2026-11-08 用户: "monro 1934 文献还是没有整理" (汇编里已有, 总表里没有).
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg  # noqa: E402

SUP = cfg.S / "supplement_accounts.tsv"


def missing_od(sl):
    """03_缺原始描述.tsv (有效分类单元) + 异名的原始描述 -> 总表工作表 '缺原始描述' (用户 2026-11-08: 没有原始描述要告诉我)."""
    f = cfg.S / "03_缺原始描述.tsv"
    if not f.exists():
        return pd.DataFrame()
    m = pd.read_csv(f, sep="\t", dtype=str).fillna("")
    bad = pd.read_csv(cfg.S / "03_待核.tsv", sep="\t", dtype=str).fillna("") if (cfg.S / "03_待核.tsv").exists() else pd.DataFrame(columns=["ref_no", "scientific_name", "content", "comment"])
    t = pd.read_csv(cfg.S / "treatment.csv", dtype=str).fillna("")
    out = []

    def why(r):
        b = bad[(bad.ref_no == r.ref_no) & (bad.scientific_name == r.scientific_name)]
        if r.获取 == "未获取":
            return "PDF 未获取"
        return f"本地 PDF 不是该文献或找不到该种 ({b.content.iloc[0]}): {b.comment.iloc[0][:80]}" if len(b) else "已获取, 记述页未定位"
    for v in m.valid_taxon:                          # 有效分类单元本身
        ep = v.split()[1][:5]
        od = sl[(sl.valid_taxon == v) & sl.level.str.startswith("L3") & (sl.scientific_name.str.split().str[-1].str[:5] == ep)]
        if od.empty:
            out.append({"类别": "有效种", "valid_taxon": v, "名称": v, "原始描述": "WoRMS 无原始描述文献", "题名": "", "卷期页": "", "原因": "需人工查找"})
        for r in od.itertuples():
            out.append({"类别": "有效种", "valid_taxon": v, "名称": r.scientific_name, "原始描述": f"{r.authors.split(';')[0]} {r.year}",
                        "题名": re.sub(r"<[^>]+>", "", r.title), "卷期页": getattr(r, "volume_issue_pages", ""), "原因": why(r)})
    l3 = set(t[t.level == "L3"].scientific_name)
    for r in sl[sl.level.str.startswith("L3") & ~sl.valid_taxon.isin(m.valid_taxon)].itertuples():   # 异名
        if r.scientific_name not in l3:
            out.append({"类别": "异名", "valid_taxon": r.valid_taxon, "名称": r.scientific_name, "原始描述": f"{r.authors.split(';')[0]} {r.year}",
                        "题名": re.sub(r"<[^>]+>", "", r.title), "卷期页": getattr(r, "volume_issue_pages", ""), "原因": why(r)})
    return pd.DataFrame(out)


def main():
    if not SUP.exists():
        return 0
    x = pd.read_csv(SUP, sep="\t", dtype=str).fillna("")
    book = pd.read_excel(cfg.TAB, sheet_name=None, dtype=str)
    rel = lambda f: f"{cfg.PDFDIR.name}/{f}"                         # noqa: E731  文件路径相对 01_文献/
    sl, lit, cov = book["物种×文献"].fillna(""), book["文献清单"].fillna(""), book["物种覆盖"].fillna("")
    sl = sl[~sl.ref_no.str.match(r"^S\d+$")]
    lit = lit[~lit.ref_no.str.match(r"^S\d+$")]
    rows, refs = [], []
    for r in x.itertuples():
        title = re.sub(r"^.*?\(\d{4}\)\.\s*", "", r.citation)
        doi = (re.search(r"10\.\d{4,}/\S+", r.citation) or [""])[0]
        pages = f"{r.printed_start}-{r.printed_end}" if r.printed_end and r.printed_end != r.printed_start else r.printed_start
        if r.fig_pages:
            pages += f"; figs: {r.fig_pages}"
        rows.append({"valid_taxon": r.taxon_valid_full, "scientific_name": r.scientific_name, "level": r.level,
                     "desc_hint": "", "use": r.use, "page": pages, "note": f"补充 (WoRMS 未挂): {r.comment}",
                     "authors": r.authors, "year": r.year, "title": title, "获取": "已获取", "文件": rel(r.file),
                     "ref_no": r.sid, "doi": doi, "status": "", "in_taxon": "Y", "via": "supplement"})
        refs.append({"source_id": "", "ref_no": r.sid, "authors": r.authors, "year": r.year, "title": title,
                     "doi": doi, "获取": "已获取", "文件": rel(r.file), "levels": r.level, "names": r.scientific_name})
        m = cov.valid_taxon == r.taxon_valid_full
        if r.level.startswith("L3") and m.any():
            cov.loc[m, "原始描述"] = f"{r.authors.split(',')[0]} {r.year} (补充, WoRMS 未挂)"
            cov.loc[m, "原始描述PDF"] = "有"
    book["物种×文献"] = pd.concat([sl, pd.DataFrame(rows)], ignore_index=True)
    book["文献清单"] = pd.concat([lit, pd.DataFrame(refs)], ignore_index=True)
    book["物种覆盖"] = cov
    book["缺原始描述"] = missing_od(book["物种×文献"].fillna(""))
    with pd.ExcelWriter(cfg.TAB, engine="openpyxl") as w:
        for name, df in book.items():
            df.to_excel(w, sheet_name=name, index=False)
    print(f"[supplement] {len(rows)} 条补充文献写入总表 {cfg.TAB.name} (物种×文献 / 文献清单 / 物种覆盖)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
