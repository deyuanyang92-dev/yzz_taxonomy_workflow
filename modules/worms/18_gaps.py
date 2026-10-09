"""18 缺失信息表: WoRMS 中每个种级名称缺什么 -> 供人工补充/核对的 Excel (以后由文献模块/合并步骤读取)

输入: names / types / coordinates / original_descriptions / specimens (02_原始数据/worms/)
输出: 04_处理数据/worms/<Taxon>_WoRMS_gaps_<date>.xlsx
  Gaps        每个种级名称一行 (有效种在前), 'missing' 列逐项写 WoRMS 缺失的信息; 有缺失才列出
              右侧 fill_* 为空白填写列 (人工从文献补: 模式产地、经纬度、水深、模式标本、文献、页码、备注、核对人、日期)
  Summary     各类缺失的数量 (有效种 / 全部种级名称)
缺失项:
  type_locality      WoRMS 无任何模式产地记录 (Type locality / contained in / 模式标本产地 / 模式分布)
  coordinates        无坐标
  coordinates_low    只有低精度模糊坐标 (EEZ/海区/大洋/州省中心点, coord_confidence = Low)
  original_desc      无原始文献 (use = original description)
  od_pages           有原始文献但无本种页码
  type_specimen      WoRMS 无模式标本记录 (物种页标本项与标本库都没有)
  depth              无模式产地水深
用法: python3 18_gaps.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import TODAY, data_dir, read_tsv, report_dir, summary
from excel import GREY, write_workbook

FILL = ["fill_type_locality", "fill_lat", "fill_lon", "fill_depth_m", "fill_type_specimen", "fill_reference", "fill_page",
        "fill_notes", "checked_by", "check_date"]


def main(taxon):
    src, out = data_dir(taxon, "worms"), report_dir(taxon, "worms")
    n, t, c, o = read_tsv(src / "names.tsv"), read_tsv(src / "types.tsv"), read_tsv(src / "coordinates.tsv"), read_tsv(src / "original_descriptions.tsv")
    s = read_tsv(src / "specimens.tsv", required=False)
    sp = n[n["rank"].isin(["Species", "Subspecies"])][["aphia_id", "scientific_name", "authority", "year", "status", "is_valid",
                                                       "valid_name", "valid_subfamily", "valid_genus"]]
    m = (sp.merge(t[["aphia_id", "type_locality_text", "type_material", "type_depth_min_m"]], on="aphia_id", how="left")
           .merge(c[["aphia_id", "coord_lat", "coord_lon", "coord_confidence", "coord_detail"]], on="aphia_id", how="left")
           .merge(o[["aphia_id", "od_citation", "od_pages_for_taxon"]], on="aphia_id", how="left")).fillna("")
    typed = set(s[s.type_status.str.lower().str.contains("type") & ~s.type_status.str.lower().isin(["nontype", "non-type"])].aphia_id) if len(s) else set()
    spec_depth = set(s[s.depth_min_m != ""].aphia_id) if len(s) else set()

    def gaps(r):
        g = []
        if not r.type_locality_text:
            g.append("type_locality")
        if not r.coord_lat:
            g.append("coordinates")
        elif r.coord_confidence == "Low":
            g.append("coordinates_low")
        if not r.od_citation:
            g.append("original_desc")
        elif not r.od_pages_for_taxon:
            g.append("od_pages")
        if not r.type_material and r.aphia_id not in typed:
            g.append("type_specimen")
        if not r.type_depth_min_m and r.aphia_id not in spec_depth:
            g.append("depth")
        return "; ".join(g)
    m["missing"] = [gaps(r) for r in m.itertuples()]
    m["n_missing"] = m.missing.map(lambda x: len(x.split("; ")) if x else 0)
    G = m[m.missing != ""].copy()
    for f in FILL:
        G[f] = ""
    G = G.sort_values(["is_valid", "valid_subfamily", "valid_genus", "scientific_name"], ascending=[False, True, True, True])
    lead = ["scientific_name", "authority", "year", "status", "valid_name", "valid_subfamily", "valid_genus", "missing", "n_missing"]
    G = G[lead + FILL + [x for x in G.columns if x not in lead + FILL]]
    keys = ["type_locality", "coordinates", "coordinates_low", "original_desc", "od_pages", "type_specimen", "depth"]
    acc = m[m.is_valid == "Y"]
    S = pd.DataFrame([{"missing": k, "accepted_species": int(acc.missing.str.contains(rf"\b{k}\b").sum()),
                       "all_species_level_names": int(m.missing.str.contains(rf"\b{k}\b").sum())} for k in keys]
                     + [{"missing": "(complete, nothing missing)", "accepted_species": int((acc.missing == "").sum()),
                         "all_species_level_names": int((m.missing == "").sum())}])
    path = out / f"{taxon}_WoRMS_gaps_{TODAY}.xlsx"
    path = write_workbook(path, {"Gaps": G, "Summary": S}, freeze={"Gaps": "B2"}, shade={"Gaps": [("is_valid", lambda v: v == "N", GREY)]})
    summary("18_gaps", [f"{len(G)}/{len(m)} species-level names with gaps (accepted {int((G.is_valid == 'Y').sum())}/{len(acc)})",
                        "accepted missing: " + "; ".join(f"{r.missing} {r.accepted_species}" for r in S.itertuples() if r.missing in keys),
                        f"-> {path}"])


if __name__ == "__main__":
    main(sys.argv[1])
