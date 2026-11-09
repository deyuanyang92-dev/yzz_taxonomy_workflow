"""16 物种 × 文献 (转换层): 每个名称 × 每篇 WoRMS 文献, 按描述证据等级分级 -> species_literature.tsv + Excel

目的 (用户 2026-11-08): 分类修订第一步, 逐种收集描述过该种的文献 (原始描述、模式重描述、非模式重描述),
便于逐种整理核对; 只有记录、名录等其他用途文献另列, 不混入. 证据等级沿用 Travisia 项目 (P:/Travisia/08_知识库/性状定义与计数规则.md):
  L3 原始描述        use = original description (本名称; 无则取原始组合上的, 转属名称的原始文献挂在原始组合上)
  L2 模式标本重描述  use = redescription 且 page / note 提到模式 (holotype / lectotype / syntype / type ...)
  L4 重描述          use = redescription, WoRMS 未注明是否模式 (须看原文: 可能是非模式材料, 也可能未注)
  其他用途           其余 use (additional source、basis of record、source of synonymy …): WoRMS 未标为描述, 是否含该种描述须看原文
note 来自 04 步 source_notes.tsv (网页才有, REST 无).

已移出属的名称 (仅当 <Taxon> 为属): 01 只取当前子树, 曾归该属、现归他属的名称 (如 Marphysa bellii -> Paucibranchia bellii)
不在 names.tsv; 本步用 REST AphiaRecordsByName '<Genus>%' 找出, 取其及其现行有效名的文献与网页 note, 一并分级, 标 in_taxon=N.

输入: names.tsv, sources.tsv, refs.tsv, original_descriptions.tsv, source_notes.tsv
输出: 02_原始数据/worms/species_literature.tsv  每行 = 名称 × 文献 × 用途
      04_处理数据/worms/<Taxon>_物种文献_<date>.xlsx  说明 / 描述文献 (L3/L2/L4) / 其他用途文献 / 物种覆盖 / 文献清单
用法: python3 yzz.py worms 23 <Taxon>  (在 oworms 01-11 之后)
"""
import datetime
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, read_tsv, report_dir, summary, write_tsv
from excel import write_workbook
from worms import REST, TYPE_NOTE, client, pmap, source_notes

SP = {"Species", "Subspecies", "Variety", "Forma"}
LEVEL_ORDER = {"L3 原始描述": 0, "L2 模式标本重描述": 1, "L4 重描述 (未注明模式)": 2, "其他用途": 3}


def level(use, page, note):
    if use == "original description":
        return "L3 原始描述"
    if use == "redescription":
        return "L2 模式标本重描述" if TYPE_NOTE.search(f"{page} {note}") else "L4 重描述 (未注明模式)"
    return "其他用途"


FIG = re.compile(r"\bfigs?\b|\bfigures?\b|\bpl\b|\bplates?\b|text-fig|\btaf\b|\btab\.", re.I)
DESC = re.compile(r"descri|figured|illustrat|diagnos", re.I)
LIST = re.compile(r"catalog|check-?list|register|inventa|\bliste?\b|list of|names? of|nomenclat|database|information system|"
                  r"biodiversity of|biota", re.I)


def hint(lv, page, note, title):
    """只用于排序, 不作剔除依据 (用户 2026-11-08: 先全收, 特征提取不到再过滤).
    M. corallina 实例: Day 1967 / de Silva 1961 / Ehlers 1904 / Hartman 1948 有描述却只标 additional source; Hartman 1959 是名录."""
    if lv != "其他用途":
        return ""
    if FIG.search(page) or DESC.search(note):
        return "强: 页码有图/图版或 note 提到描述"
    if LIST.search(title):
        return "弱: 名录/目录类题名"
    return ""


def moved_out(genus, known):
    """曾归该属、现归他属的名称: AphiaRecordsByName '<genus>%' 中有效名不在本属的."""
    http, recs, off = client().http, {}, 1
    while True:
        try:
            d = http.get_json(f"{REST}/AphiaRecordsByName/{genus}", params={"like": "true", "marine_only": "false", "offset": off})
        except Exception:
            d = None
        if not d:
            break
        for x in d:
            if x["scientificname"].split(" ")[0] == genus and str(x["AphiaID"]) not in known and x.get("valid_name") \
                    and x["valid_name"].split(" ")[0] != genus:
                recs[str(x["AphiaID"])] = x
        off += 50          # WoRMS 每页实际 45-50 条不定 (2026-11-08 实测 45/49/50), 不能以 <50 判末页; 取到空/204 为止
        if off > 5000:
            break
    return list(recs.values())


def ext_sources(aid):
    """名称外的 AphiaID: REST 文献 + 网页 note."""
    c = client()
    rest = c.http.get_json(f"{REST}/AphiaSourcesByAphiaID/{aid}") or []
    notes = {(r["source_id"], r["use"]): r for r in source_notes(c.taxdetails_html(int(aid)))}
    out = []
    for s in rest:
        n = notes.get((str(s["source_id"]), s["use"]), {})
        out.append({"aphia_id": str(aid), "source_id": str(s["source_id"]), "use": s["use"], "page": s.get("page") or "",
                    "note": n.get("note", ""), "reference": s.get("reference") or "", "doi": s.get("doi") or ""})
    return out


def main(taxon):
    out = data_dir(taxon, "worms")
    n, s, f = read_tsv(out / "names.tsv"), read_tsv(out / "sources.tsv"), read_tsv(out / "refs.tsv")
    od = read_tsv(out / "original_descriptions.tsv")
    sn = read_tsv(out / "source_notes.tsv", required=False)
    s = s.copy()
    if len(sn):
        s = s.merge(sn.drop_duplicates(["aphia_id", "source_id", "use"])[["aphia_id", "source_id", "use", "note"]],
                    on=["aphia_id", "source_id", "use"], how="left").fillna({"note": ""})
    else:
        s["note"] = ""
    s = s[["aphia_id", "source_id", "use", "page", "note"]]
    sp = n[n["rank"].isin(SP)].copy()
    sp["in_taxon"] = "Y"
    name_cols = ["aphia_id", "scientific_name", "authority", "status", "valid_aphia_id", "valid_name", "valid_authority", "in_taxon"]
    names = sp[name_cols]

    # 1) 01 子树之外、但曾归本属的名称 (checklist 已含大部分非有效名, 如 Marphysa bellii; 此处补漏网的, 如 Marphysa belli oculata)
    root = n[(n.scientific_name == taxon)]
    mv = moved_out(taxon, set(n.aphia_id)) if len(root) and root["rank"].iloc[0] == "Genus" else []
    mvn = pd.DataFrame([{"aphia_id": str(x["AphiaID"]), "scientific_name": x["scientificname"], "authority": x.get("authority") or "",
                         "status": x["status"], "valid_aphia_id": str(x.get("valid_AphiaID") or ""), "valid_name": x["valid_name"],
                         "valid_authority": x.get("valid_authority") or "", "in_taxon": "N"} for x in mv], columns=name_cols)
    # 2) 非有效名的现行有效分类单元在子树外 (Marphysa bellii -> Paucibranchia bellii): 其文献挂在有效名上 (如 Molina-Acevedo 2018
    #    重描述), 不取就漏. 有效名本身作为一行 (in_taxon = 'N (现行有效名)').
    allv = pd.concat([names, mvn])
    val = allv[(allv.valid_aphia_id != "") & ~allv.valid_aphia_id.isin(set(names.aphia_id) | set(mvn.aphia_id))]
    val = val[["valid_aphia_id", "valid_name", "valid_authority"]].drop_duplicates("valid_aphia_id")
    vrows = val.rename(columns={"valid_aphia_id": "aphia_id", "valid_name": "scientific_name", "valid_authority": "authority"})
    vrows = vrows.assign(status="accepted", valid_aphia_id=vrows.aphia_id, valid_name=vrows.scientific_name,
                         valid_authority=vrows.authority, in_taxon="N (现行有效名)")
    extra = pd.concat([mvn, vrows], ignore_index=True)
    es = pd.DataFrame()
    if len(extra):
        res = pmap(ext_sources, list(extra.aphia_id))
        es = pd.DataFrame([x for r in res if r for x in r])
        names = pd.concat([names, extra[name_cols]], ignore_index=True)
        if len(es):
            s = pd.concat([s, es[["aphia_id", "source_id", "use", "page", "note"]]], ignore_index=True)
            miss = es[~es.source_id.isin(set(f.source_id))].drop_duplicates("source_id")
            f = pd.concat([f, pd.DataFrame({"source_id": miss.source_id, "citation": miss.reference, "doi": miss.doi})], ignore_index=True)

    rows = s.merge(names, on="aphia_id", how="inner")
    rows["via"] = ""
    # 原始描述挂在原始组合 (他属) 上: 11 步已回退
    oc = od[(od.od_taken_from == "original combination") & (od.od_source_id != "")]
    add = []
    for r in oc.itertuples():
        nm = names[names.aphia_id == r.aphia_id]
        if not len(nm):
            continue
        for sid, pg in zip(r.od_source_id.split(" || "), (r.od_pages_for_taxon.split(" || ") + [""] * 9)):
            add.append({**nm.iloc[0].to_dict(), "source_id": sid, "use": "original description", "page": pg, "note": "",
                        "via": "原始组合上的原始描述"})
    if add:
        rows = pd.concat([rows, pd.DataFrame(add)], ignore_index=True)
    rows = rows.drop_duplicates(["aphia_id", "source_id", "use"])
    rows["level"] = [level(u, p, t) for u, p, t in zip(rows.use, rows.page, rows.note)]
    keep = ["source_id", "citation", "authors", "year", "title", "journal_or_publisher", "volume_issue_pages", "doi"]
    rows = rows.merge(f[[c for c in keep if c in f.columns]].drop_duplicates("source_id"), on="source_id", how="left").fillna("")
    rows["valid_taxon"] = (rows.valid_name + " " + rows.valid_authority).str.strip()
    rows.loc[rows.valid_taxon == "", "valid_taxon"] = (rows.scientific_name + " " + rows.authority).str.strip()
    rows["desc_hint"] = [hint(lv, p, t, ti) for lv, p, t, ti in zip(rows.level, rows.page, rows.note, rows.title + " " + rows.citation)]
    rows["_o"] = rows.level.map(LEVEL_ORDER)
    rows["_h"] = rows.desc_hint.str[:1].map({"强": 0, "": 1, "弱": 2}).fillna(1)
    rows = rows.sort_values(["valid_taxon", "_o", "_h", "year", "scientific_name"]).drop(columns=["_o", "_h"])
    cols = ["valid_taxon", "scientific_name", "authority", "status", "in_taxon", "level", "desc_hint", "use", "page", "note", "via",
            "source_id", "authors", "year", "title", "journal_or_publisher", "volume_issue_pages", "doi", "citation", "aphia_id", "valid_aphia_id"]
    rows = rows[cols]
    write_tsv(rows, out / "species_literature.tsv")

    desc = rows[rows.level != "其他用途"]
    other = rows[rows.level == "其他用途"]
    strong = other.desc_hint.str.startswith("强")
    cov = []
    for vt, g in rows.groupby("valid_taxon", sort=True):
        def lv(L, g=g):
            return "; ".join(dict.fromkeys(f"{a.split(';')[0].split(',')[0]} {y}".strip() for a, y in
                                           zip(g[g.level == L].authors, g[g.level == L].year)))
        cov.append({"valid_taxon": vt, "in_taxon": g.in_taxon.iloc[0], "names": "; ".join(sorted(set(g.scientific_name))),
                    "L3 原始描述": lv("L3 原始描述"), "L2 模式标本重描述": lv("L2 模式标本重描述"),
                    "L4 重描述 (未注明模式)": lv("L4 重描述 (未注明模式)"),
                    "n_L2": (g.level == "L2 模式标本重描述").sum(), "n_L4": (g.level == "L4 重描述 (未注明模式)").sum(),
                    "n_其他用途": g[g.level == "其他用途"].source_id.nunique(),
                    "其他用途_强线索": "; ".join(dict.fromkeys(f"{a.split(';')[0].split(',')[0]} {y}" for a, y, h in
                                                        zip(g.authors, g.year, g.desc_hint) if h.startswith("强")))})
    C = pd.DataFrame(cov)
    lit = rows.groupby("source_id").agg(levels=("level", lambda x: "; ".join(sorted(set(x), key=LEVEL_ORDER.get))),
                                        names=("scientific_name", lambda x: "; ".join(sorted(set(x)))),
                                        uses=("use", lambda x: "; ".join(sorted(set(x))))).reset_index()
    lit = lit.merge(f[[c for c in keep if c in f.columns]].drop_duplicates("source_id"), on="source_id", how="left").fillna("")
    lit["_o"] = lit.levels.map(lambda x: LEVEL_ORDER.get(x.split("; ")[0], 9))
    lit = lit.sort_values(["_o", "year"]).drop(columns="_o")
    readme = pd.DataFrame({"说明": [
        f"{taxon} 物种 × 文献 (WoRMS, {datetime.date.today()}). 每行 = 一个名称 × 一篇文献 × 一个用途; valid_taxon 带命名人, 区分同名异物.",
        "level: L3 原始描述 (use=original description; 转属名称回退原始组合上的) / L2 模式标本重描述 (redescription 且 page 或 note 提到模式) / "
        "L4 重描述 (redescription, WoRMS 未注明模式, 须看原文) / 其他用途 (WoRMS 未标为描述, 是否含该种描述须看原文).",
        "全部收录, 不按用途剔除: WoRMS 用途区分不了有无描述 (M. corallina: Day 1967、de Silva 1961、Ehlers 1904、Hartman 1948 有描述却标 "
        "additional source; Hartman 1959 名录同标 additional source). 特征提取时取不到描述的再过滤.",
        "desc_hint (只用于排序, 不作剔除): 强 = 页码有图/图版或 note 提到描述; 弱 = 名录/目录类题名; 空 = 未知.",
        "note 取自 WoRMS 物种页 (REST 不提供), 如 'redescription from holotype'.",
        "in_taxon = N: 曾归本属、现归他属的名称 (AphiaRecordsByName 补入); 'N (现行有效名)' 为其现行有效名本身的文献.",
        "WoRMS 只收编辑挂上的文献: 漏标的重描述、带描述的记录和大部分中文文献不在其中, 需逐种全文检索补齐.",
        "空白 = WoRMS 无此信息, 不推断."]})
    rep = report_dir(taxon, "worms") / f"{taxon}_物种文献_{datetime.date.today()}.xlsx"
    path = write_workbook(rep, {"说明": readme, "物种×文献 (全部)": rows, "物种覆盖": C, "文献清单": lit},
                          freeze={"物种×文献 (全部)": "C2", "物种覆盖": "B2"})
    vc = desc.level.value_counts()
    summary("23_species_literature", [
        f"{rows.valid_taxon.nunique()} taxa ({(~C.valid_taxon.str.startswith(taxon + ' ')).sum()} now in other genera); {rows.source_id.nunique()} sources; {len(rows)} name×source links",
        f"L3 {vc.get('L3 原始描述', 0)}; L2 {vc.get('L2 模式标本重描述', 0)}; L4 {vc.get('L4 重描述 (未注明模式)', 0)}; other-use links {len(other)} (hint 强 {strong.sum()}, 弱 {other.desc_hint.str.startswith('弱').sum()})",
        f"taxa without L3: {(C['L3 原始描述'] == '').sum()}; with L2/L4 redescription: {((C.n_L2 + C.n_L4) > 0).sum()}",
        f"-> {out / 'species_literature.tsv'}", f"-> {path}"])


if __name__ == "__main__":
    main(sys.argv[1])
