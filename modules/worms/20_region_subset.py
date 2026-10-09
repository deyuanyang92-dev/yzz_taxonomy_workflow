"""20 区域子集: 从 worms 模块全部 WoRMS 记录中筛出与某海域相关的名称 -> Excel (三张表, 每条注明证据)

输入: names / types / localities / coordinates / original_descriptions / sources / taxdetails_items /
      taxdetails_fields / distributions (02_原始数据/worms/)
输出: 04_处理数据/worms/<Taxon>_<region>_<date>.xlsx
  A_type_locality   模式产地在该海域 (确定): WoRMS 模式产地记录 / 标准化地名含关键词, 或模式产地坐标在范围框内
                    (框内且标准化国家为空或属该海域国家, 且坐标可信度 High/Medium; Low 级模糊坐标不算)
  B_candidates      待文献核对: 不在 A, 但 (原始文献/重描述题目 | 种名词源 | 物种页注释 | 非模式分布) 含关键词,
  C_recorded        有该海域分布记录 (非模式产地): WoRMS 来源引用该海域名录/文献 (如 Liu 2008, Hanley 1992)
  Notes             关键词、范围框、口径
用法: python3 20_region_subset.py <Taxon> [--region china]
"""
import argparse, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import TODAY, data_dir, read_tsv, report_dir, summary
from excel import GREY, write_workbook

REGIONS = {
    "china": dict(
        label="China seas (Bohai, Yellow Sea, East China Sea, Taiwan Strait, South China Sea; incl. Taiwan, Hong Kong, Macau)",
        keywords=r"\bChina\b|Chinese|Taiwan|Formosa|Hong ?Kong|Macau|Bohai|Pohai|Po-?hai|Yellow Sea|Hwang ?hai|East China Sea|"
                 r"South China Sea|Nanhai|Taiwan Strait|Hainan|Xisha|Nansha|Paracel|Spratly|Pratas|Dongsha|Okinawa Trough|"
                 r"Xiamen|Amoy|Qingdao|Tsingtao|Tsingtau|Dalian|Yantai|Chefoo|Weihai|Shanghai|Zhoushan|Ningbo|Wenzhou|"
                 r"Fujian|Fukien|Zhejiang|Chekiang|Shandong|Shantung|Jiangsu|Liaoning|Hebei|Guangdong|Kwangtung|Guangxi|"
                 r"Beihai|Zhanjiang|Shenzhen|Sanya|Yalong|Qinglan|Beibu|Tonkin|Keelung|Kaohsiung|Penghu|Pescadores|Kinmen|Matsu",
        epithets=r"(sinensis|chinensis|chinense|amoyensis|amoyana|amoyanus|xiamenensis|nanhaiensis|hainanensis|hainanica|hainanicus|"
                 r"pohaiensis|bohaiensis|hwanghaiensis|huanghaiensis|qingdaoensis|tsingtaoensis|formosana|formosanus|formosensis|"
                 r"taiwanensis|taiwanica|hongkongensis|hongkongiensis|xishaensis|nanshaensis|beibuensis|tonkinica|tonkinensis|"
                 r"donghaiensis|zhejiangensis|fujianensis|guangdongensis|shandongensis|liaoningensis)\b",
        checklists=r"marine biota of China|China seas|Hong Kong|southern China|Taiwan|Formosa|Chinese",
        bbox=(3.0, 41.0, 105.0, 131.0),
        countries={"", "China", "Taiwan"}),
}


def main(taxon, region):
    R = REGIONS[region]
    src, out = data_dir(taxon, "worms"), report_dir(taxon, "worms")
    r = lambda f, req=True: read_tsv(src / f, required=req)
    n, t, l, c, o = r("names.tsv"), r("types.tsv"), r("localities.tsv"), r("coordinates.tsv"), r("original_descriptions.tsv")
    srcs, it, fld, dist = r("sources.tsv"), r("taxdetails_items.tsv", False), r("taxdetails_fields.tsv", False), r("distributions.tsv", False)
    s = r("specimens.tsv", False)
    kw = re.compile(r"\b(?:" + R["keywords"].replace("\\b", "") + r")\b", re.I)   # 词边界: 避免 Matsu 命中 Matsushima
    ep = re.compile(R["epithets"], re.I)
    found = lambda txt: sorted({m.group(0) for m in kw.finditer(txt or "")})

    sp = n[n["rank"].isin(["Species", "Subspecies"])][["aphia_id", "scientific_name", "authority", "year", "status", "is_valid",
                                                       "valid_name", "valid_authority", "valid_subfamily", "valid_genus", "species_epithet"]]
    m = (sp.merge(t[["aphia_id", "type_locality_text", "type_locality_text_source", "type_locality_contained_in", "type_material"]], on="aphia_id", how="left")
           .merge(l.drop(columns=["locality_source_text"]).rename(columns=lambda x: x if x == "aphia_id" else f"Std: {x}"), on="aphia_id", how="left")
           .merge(c.drop(columns=["scientific_name"]), on="aphia_id", how="left")
           .merge(o[["aphia_id", "od_citation", "od_pages_for_taxon", "od_doi_url", "redescriptions"]], on="aphia_id", how="left")).fillna("")
    if len(s):
        m["type_specimens"] = m.aphia_id.map(s.groupby("aphia_id").apply(
            lambda g: "; ".join(f"{x} {y} {z}".strip() for x, y, z in zip(g.type_status, g.institution, g.catalog_no)))).fillna("")

    # ---- A: 模式产地 ----
    rec = m[["type_locality_text", "type_locality_contained_in", "Std: country", "Std: state_province", "Std: county_city",
             "Std: locality", "Std: water_body"]].agg(" | ".join, axis=1)
    la, lo = pd.to_numeric(m.coord_lat, errors="coerce"), pd.to_numeric(m.coord_lon, errors="coerce")
    a_, b_, w_, e_ = R["bbox"]
    inbox = (la.between(a_, b_) & lo.between(w_, e_) & m["Std: country"].isin(R["countries"])
             & m.coord_confidence.isin(["High", "Medium"]))   # Low 级模糊坐标 (大洋/EEZ/岛屿中心) 不能作为'在该海域'的证据
    ev_a = [("; ".join(x for x in [f"type-locality record [{', '.join(found(t_))}]" if found(t_) else "",
                                   f"coordinates in box ({p_})" if ib else ""] if x))
            for t_, ib, p_ in zip(rec, inbox, m.coord_precision)]
    m["evidence"] = ev_a
    A = m[m.evidence != ""].copy()

    # ---- B: 待核对 ----
    notes = it.groupby("aphia_id").apply(lambda g: " | ".join(g.label + ": " + g.value)) if len(it) else pd.Series(dtype=str)
    odpage = fld[fld.field == "Original description"].groupby("aphia_id").text.apply(" | ".join) if len(fld) else pd.Series(dtype=str)
    ndist = dist[dist.get("typeStatus", "") == ""].groupby("aphia_id").locality.apply(" | ".join) if len(dist) else pd.Series(dtype=str)
    B_rows = []
    for x in m[~m.aphia_id.isin(A.aphia_id)].to_dict("records"):
        ev = []
        odt = x["od_citation"] + " | " + odpage.get(x["aphia_id"], "")
        if found(odt):
            ev.append(f"original description title [{', '.join(found(odt))}]")
        if found(x["redescriptions"]):
            ev.append(f"redescription title [{', '.join(found(x['redescriptions']))}]")
        if ep.search(x["species_epithet"] or x["scientific_name"].split()[-1]):
            ev.append(f"epithet '{x['scientific_name'].split()[-1]}'")
        if found(notes.get(x["aphia_id"], "")):
            ev.append(f"taxdetails notes [{', '.join(found(notes.get(x['aphia_id'], '')))}]")
        if found(ndist.get(x["aphia_id"], "")):
            ev.append(f"non-type distribution [{', '.join(found(ndist.get(x['aphia_id'], '')))}]")
        if ev:
            B_rows.append({**x, "evidence": "; ".join(ev)})
    B = pd.DataFrame(B_rows, columns=list(m.columns))

    # ---- C: 有该海域分布记录 (非模式) ----
    ck = srcs[srcs.reference.str.contains(R["checklists"], case=False, regex=True)]
    C = (ck.groupby("aphia_id").reference.apply(lambda x: " || ".join(sorted(set(x))[:5])).rename("regional_references").reset_index()
           .merge(m[["aphia_id", "scientific_name", "authority", "status", "is_valid", "valid_name", "valid_subfamily", "valid_genus",
                     "type_locality_text"]], on="aphia_id"))
    C["type_locality_in_region"] = C.aphia_id.isin(A.aphia_id).map({True: "Y", False: ""})

    lead = ["scientific_name", "authority", "year", "status", "valid_name", "valid_authority", "valid_subfamily", "valid_genus",
            "evidence", "type_locality_text", "Std: country", "Std: locality", "coord_lat", "coord_lon", "coord_precision"]
    order = lambda d: d[[x for x in lead if x in d] + [x for x in d.columns if x not in lead]].sort_values(
        ["valid_subfamily", "valid_genus", "valid_name", "is_valid"], ascending=[True, True, True, False]) if len(d) else d
    A, B = order(A), order(B)
    C = C.sort_values(["valid_subfamily", "valid_genus", "scientific_name"])
    notes_df = pd.DataFrame({"item": ["Region", "A_type_locality", "B_candidates", "C_recorded", "Keywords", "Epithets", 
                                      "Regional references (C)", "Bounding box", "Limits"],
                             "value": [R["label"],
                                       f"{len(A)} names ({int((A.is_valid == 'Y').sum())} accepted): type locality in region per WoRMS record or coordinates",
                                       f"{len(B)} names: region mentioned elsewhere in WoRMS (title, epithet, notes, non-type distribution) - verify in the literature",
                                       f"{len(C)} names: WoRMS sources cite regional checklists/literature (records, not type localities)",
                                       R["keywords"], R["epithets"], R["checklists"], str(R["bbox"]),
                                       "Only as complete as WoRMS: species whose type locality is not recorded in WoRMS and not mentioned in any "
                                       "WoRMS field cannot be found here; cross-check with regional checklists (e.g. Liu 2008) and literature."]})
    path = out / f"{taxon}_{region}_{TODAY}.xlsx"
    path = write_workbook(path, {"A_type_locality": A, "B_candidates": B, "C_recorded": C, "Notes": notes_df},
                          freeze={"A_type_locality": "B2", "B_candidates": "B2", "C_recorded": "B2"},
                          shade={k: [("is_valid", lambda v: v == "N", GREY)] for k in ("A_type_locality", "B_candidates", "C_recorded")})
    summary("20_region_subset", [f"{region}: A type locality {len(A)} ({int((A.is_valid == 'Y').sum())} accepted); "
                                 f"B candidates {len(B)}; C recorded (non-type) {len(C)}", f"-> {path}"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("taxon")
    ap.add_argument("--region", default="china", choices=sorted(REGIONS))
    a = ap.parse_args()
    main(a.taxon, a.region)
