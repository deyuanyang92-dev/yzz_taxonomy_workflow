"""22 模式产地原文复查: WoRMS 模式产地/坐标 vs 原始描述原文 -> type_locality_verify.tsv

目的 (用户 2026-11-09): WoRMS 编辑整理得很清楚, 但给出的模式产地和经纬度不一定最准, 须用原始描述原文复查.
输入: coordinates.tsv (14: worms_only_* = 只用 WoRMS 得到的坐标; od_* = 原文定位; od_vs_coord_km; od_country_match)
      types.tsv (12: WoRMS 模式产地原文), names.tsv
      <项目>/08_知识库/结构化/od_type_locality.tsv (compilation 05: 原文模式产地片段)
输出: 02_原始数据/worms/type_locality_verify.tsv  每行 = 一个有效种
判定 (verify_status):
  agree            原文经纬度/地名与 WoRMS 坐标相距 <= 100 km
  close            100-1000 km (多为同一地点不同精度; 原文写明经纬度的值得改用)
  conflict         > 1000 km, 或 WoRMS 坐标不在原文国家内 -> 须对照原文页图核实 (也可能是 05 抽错句子)
  OD finer         WoRMS 只到大洋/大海区 (坐标不确定度 > 1000 km), 原文更具体 -> 宜改用原文
  same country     原文只到国家, WoRMS 坐标在该国内
  OD only          WoRMS 无模式产地, 坐标取自原文
  OD title only    原文正文未抽到产地, 只有文献题目中的国家/岛屿 (很粗)
  OD no locality   有原始描述原文, 但未抽到模式产地 (OCR 差、或产地在题目/引言中) -> 人工看原文
  no OD text       本地库无原始描述原文 -> 先补文献 (compilation 03 的 03_缺原始描述.tsv)
用法: python3 22_tl_verify.py <Taxon>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv

AGREE_KM, CLOSE_KM = 100, 1000
ORDER = ["conflict", "close", "OD finer", "OD no locality", "OD title only", "no OD text", "OD only", "same country", "agree"]


def status(r, has_od_text):
    km = float(r["od_vs_coord_km"]) if r.get("od_vs_coord_km") else None
    if r.get("coord_basis", "").startswith("od_") and not r.get("worms_only_lat"):
        return "OD only"
    unc = r.get("worms_only_unc_km", "")
    if unc not in ("", None) and float(unc) > CLOSE_KM and (km is not None or r.get("od_country_match")):
        return "OD finer"                     # WoRMS 只到大洋/大海区 (如 'Atlantic Ocean'), 原文更具体
    if r.get("od_country_match") == "N" or (km is not None and km > CLOSE_KM):
        return "conflict"
    if km is not None:
        return "agree" if km <= AGREE_KM else "close"
    if r.get("od_country_match") == "Y":
        return "same country"
    if r.get("od_cue") == "work_title":
        return "OD title only"
    return "OD no locality" if has_od_text else "no OD text"


def main(taxon):
    out = data_dir(taxon, "worms")
    n = read_tsv(out / "names.tsv")
    c = read_tsv(out / "coordinates.tsv").set_index("aphia_id")
    t = read_tsv(out / "types.tsv").set_index("aphia_id")
    p = out.parents[2] / "08_知识库" / "结构化" / "od_type_locality.tsv"
    od = read_tsv(p) if p.exists() else pd.DataFrame(columns=["taxon", "tl_cue", "tl_text", "work_id", "pages"])
    has_text = set(od.taxon)
    acc = n[(n.aphia_id == n.valid_aphia_id) & n["rank"].isin(["Species", "Subspecies"]) & (n.status == "accepted")]
    rows = []
    for v in acc.to_dict("records"):
        a = v["aphia_id"]
        r = c.loc[a].to_dict() if a in c.index else {}
        o = od[od.taxon == v["scientific_name"]]
        o = o[o.tl_cue != ""]
        o = o.assign(_t=o.tl_cue == "work_title").sort_values("_t").head(1)     # 原文片段优先于题目
        r["od_cue"] = o.iloc[0]["tl_cue"] if len(o) else ""
        rows.append({
            "aphia_id": a, "valid_name": v["scientific_name"], "authority": v["authority"],
            "verify_status": status(r, v["scientific_name"] in has_text),
            "worms_type_locality": t.at[a, "type_locality_text"] if a in t.index else "",
            "worms_lat": r.get("worms_only_lat", ""), "worms_lon": r.get("worms_only_lon", ""),
            "worms_basis": r.get("worms_only_basis", ""),
            "od_source": f"{o.iloc[0]['work_id']} p. {o.iloc[0]['pages']} [{o.iloc[0]['tl_cue']}]" if len(o) else "",
            "od_type_locality_text": o.iloc[0]["tl_text"] if len(o) else "",
            "od_lat": r.get("od_lat", ""), "od_lon": r.get("od_lon", ""), "od_basis": r.get("od_basis", ""),
            "distance_km": r.get("od_vs_coord_km", ""), "od_country_match": r.get("od_country_match", ""),
            "adopted_lat": r.get("coord_lat", ""), "adopted_lon": r.get("coord_lon", ""), "adopted_basis": r.get("coord_basis", ""),
        })
    df = pd.DataFrame(rows)
    df["_o"] = df.verify_status.map({k: i for i, k in enumerate(ORDER)})
    df = df.sort_values(["_o", "valid_name"]).drop(columns="_o")
    write_tsv(df, out / "type_locality_verify.tsv")
    vc = df.verify_status.value_counts().to_dict()
    summary("22_tl_verify", [f"{len(df)} accepted species: {vc}",
                             "conflict: " + "; ".join(df[df.verify_status == "conflict"].valid_name),
                             f"-> {out / 'type_locality_verify.tsv'}  (原文为 OCR; conflict 须对照页图核实)"])


if __name__ == "__main__":
    main(sys.argv[1])
