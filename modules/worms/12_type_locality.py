"""12 模式产地汇总 (转换层): 从提取层 WoRMS 记录值合成每个种级名称的模式产地信息 -> types.tsv

只组合、不改写 WoRMS 记录值; 每列注明取自哪张原始表, 可回溯.
输入: taxdetails_items.tsv (04), distributions.tsv (05), specimens.tsv (06)
输出: 02_原始数据/worms/types.tsv  每行 = 一个种级名称
字段:
  type_locality_text          优先级: 04 note 'Type locality' > 04 dr 'type locality contained in' > 06 模式标本 verbatimGeounit > Geounit
  type_locality_text_source   上一列取自哪里
  type_localities             04 中全部 note 'Type locality' 记录值 (; 连接)
  type_locality_contained_in  04 中全部 dr 'type locality contained in' (; 连接)
  type_locality_from_synonym  Y = 页面标注该模式产地来自异名
  type_data_notes             04 Type data 区其他 note (label: value)
  type_material               04 中 sm 标本项记录值 (; 连接)
  type_dist_*                 05 中带 typeStatus 的分布记录: locality / higherGeography / MRGID / 坐标
  distribution_localities     05 中非模式分布记录的地名 (; 连接) 及条数
  specimen_geounits           06 标本 Geounit / verbatimGeounit
  type_depth_min_m/max_m/text 从上述文本解析的水深 (英寻换算)
用法: python3 12_type_locality.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, parse_depth, read_tsv, summary, uniq, write_tsv

SP = {"Species", "Subspecies", "Variety", "Forma"}
J = lambda xs: "; ".join(uniq(xs))


def main(taxon):
    out = data_dir(taxon, "worms")
    n = read_tsv(out / "names.tsv")
    it = read_tsv(out / "taxdetails_items.tsv")
    d = read_tsv(out / "distributions.tsv", required=False)
    s = read_tsv(out / "specimens.tsv", required=False)
    IT = {k: g for k, g in it.groupby("aphia_id")}
    D = {k: g for k, g in d.groupby("aphia_id")} if len(d) else {}
    if len(s):   # 只用模式标本 (Holotype/Syntype/Paratype/Lectotype/Neotype...); WoRMS 标本库也含 Nontype, 不能当模式产地
        s = s[s.type_status.str.strip().str.lower().str.contains("type") & ~s.type_status.str.strip().str.lower().isin(["nontype", "non-type", "unknown type"])]
    S = {k: g for k, g in s.groupby("aphia_id")} if len(s) else {}
    empty = pd.DataFrame(columns=it.columns)

    rows = []
    for a in n[n["rank"].isin(SP)].aphia_id:
        g = IT.get(a, empty)
        td = g[g.section == "Type data"]
        note_tl = td[(td.item_kind == "note") & (td.label.str.lower() == "type locality")]
        dr_tl = td[(td.item_kind == "dr") & td.label.str.lower().str.contains("type locality")]
        other_notes = td[(td.item_kind == "note") & (td.label.str.lower() != "type locality")]
        dd = D.get(a, pd.DataFrame(columns=["typeStatus", "locality"]))
        ts = dd[dd.get("typeStatus", pd.Series(dtype=str)).fillna("") != ""] if len(dd) else dd
        nts = dd[dd.get("typeStatus", pd.Series(dtype=str)).fillna("") == ""] if len(dd) else dd
        coords = (ts[(ts["decimalLatitude"].fillna("") != "") & (ts["decimalLongitude"].fillna("") != "")]   # 经纬度都有才算 (WoRMS 有只填纬度的记录)
                  if len(ts) and "decimalLatitude" in ts and "decimalLongitude" in ts else ts.iloc[0:0])
        ss = S.get(a, pd.DataFrame())
        sp_verb = J(ss.get("worms: verbatimGeounit", [])) if len(ss) else ""
        sp_geo = J(ss.get("worms: Geounit", [])) if len(ss) else ""
        text, text_src = ((J(note_tl.value), "taxdetails note 'Type locality'") if len(note_tl) else
                          (J(dr_tl.value), "taxdetails 'type locality contained in'") if len(dr_tl) else
                          (sp_verb, "type specimen verbatimGeounit (06)") if sp_verb else
                          (sp_geo, "type specimen Geounit (06)") if sp_geo else ("", ""))
        material = J(td[td.item_kind == "sm"].label + " " + td[td.item_kind == "sm"].value)
        lo, hi, snip = parse_depth(" ".join([text, J(other_notes.value), material]))
        rows.append({
            "aphia_id": a,
            "type_locality_text": text,
            "type_locality_text_source": text_src,
            "type_localities": J(note_tl.value),
            "type_locality_qc_source": J(note_tl.qc_source),
            "type_locality_contained_in": J(dr_tl.value),
            "type_locality_from_synonym": "Y" if (td.from_synonym == "Y").any() else "",
            "type_data_notes": J(other_notes.label + ": " + other_notes.value),
            "type_material": material,
            "type_specimen_summaries": material,
            "type_dist_locality": J(ts.get("locality", [])) if len(ts) else "",
            "type_dist_higher_geography": J(ts.get("higherGeography", [])) if len(ts) else "",
            "type_dist_mrgid": J(ts.get("locationID", [])) if len(ts) else "",
            "type_dist_lat": coords.iloc[0]["decimalLatitude"] if len(coords) else "",
            "type_dist_lon": coords.iloc[0]["decimalLongitude"] if len(coords) else "",
            "distribution_localities": J(nts.get("locality", [])) if len(nts) else "",
            "distribution_n": str(len(nts)),
            "specimen_geounits": J(list(ss.get("worms: verbatimGeounit", [])) + list(ss.get("worms: Geounit", []))) if len(ss) else "",
            "type_depth_min_m": lo, "type_depth_max_m": hi, "type_depth_text": snip,
        })
    t = pd.DataFrame(rows)
    # 模式分布记录自带的 Marine Regions ID (14 用它直接取区域, 不靠名称匹配)
    if len(d) and "locationID" in d:
        mr = lambda v: "; ".join(uniq(x.rstrip("/").split("/")[-1] for x in v if x))
        t["type_dist_mrgid_ids"] = t.aphia_id.map(d[d["typeStatus"].fillna("") != ""].groupby("aphia_id").locationID.apply(mr)).fillna("")
    # 有效名自身无模式产地信息时, 用原始组合 (同一模式) 的; 来源列注明 via original combination
    orig = dict(zip(n.aphia_id, n.original_name_aphia_id))
    T = t.set_index("aphia_id")
    fill = ["type_locality_text", "type_locality_text_source", "type_localities", "type_locality_qc_source",
            "type_locality_contained_in", "type_material", "type_specimen_summaries", "specimen_geounits",
            "type_depth_min_m", "type_depth_max_m", "type_depth_text"]
    for a in T.index[T.type_locality_text == ""]:
        o = orig.get(a, "")
        if o and o != a and o in T.index and T.at[o, "type_locality_text"]:
            for c in fill:
                if not T.at[a, c]:
                    T.at[a, c] = T.at[o, c]
            T.at[a, "type_locality_text_source"] = T.at[o, "type_locality_text_source"] + " [via original combination]"
    t = T.reset_index()
    write_tsv(t, out / "types.tsv")
    has = lambda c: int((t[c] != "").sum())
    summary("12_type_locality", [f"{len(t)} species-level names: type locality text {has('type_locality_text')} "
                                 f"(note {has('type_localities')}, contained-in {has('type_locality_contained_in')}); "
                                 f"type material {has('type_material')}; other distributions {(t.distribution_n != '0').sum()}; depth {has('type_depth_min_m')}",
                                 f"-> {out / 'types.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
