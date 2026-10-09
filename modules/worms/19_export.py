"""19 导出: 合并全部 TSV -> 一个 Excel 报表 + Markdown 摘要 (只做展示, 不改数据)

输入: 02_原始数据/worms/*.tsv
输出: 04_处理数据/worms/<Taxon>_WoRMS_<date>.xlsx , <Taxon>_WoRMS_<date>.md
工作表:
  Names                全部名称 (各阶元, 有效+非有效; 按有效名分组, 非有效名灰底) + 原始文献
  Species summary      种级名称一行: 归属 + 原始文献 + 重描述 + 模式产地 (WoRMS 记录值+标准化) + 生境/水深 + 模式标本
  Original descriptions 原始文献结构化字段 (作者/年/题目/期刊/卷期页码/本种页码/DOI/链接/ZooBank/开放获取)
  References           全部文献 (refs.tsv)
  Specimens            全部标本 (含 WoRMS 原始字段)
  Valid genera         有效属统计      Decades   各年代有效种描述数
  QC                   需人工核对的问题  Notes     数据来源/覆盖率/口径说明
用法: python3 19_export.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import TODAY, data_dir, read_tsv, report_dir, summary
from excel import GREY, YELLOW, write_workbook

SP = ["Species", "Subspecies", "Variety", "Forma"]


# 标本字段 -> 总表列名 (WoRMS specdetails 页全部常见字段; 页面上有而这里没列的字段仍在 Specimens 表)
SPEC_FIELDS = [("type_status", "spec_type_status"), ("catalog_no", "spec_catalog_no"), ("institution", "spec_institution"),
               ("worms: Museum", "spec_museum"), ("worms: Specimen count", "spec_count"), ("worms: Preservation", "spec_preservation"),
               ("worms: Geounit", "spec_geounit"), ("worms: verbatimGeounit", "spec_verbatim_geounit"),
               ("latitude", "spec_lat"), ("longitude", "spec_lon"), ("worms: End latitude", "spec_end_lat"),
               ("worms: End longitude", "spec_end_lon"), ("depth_min_m", "spec_depth_min_m"), ("depth_max_m", "spec_depth_max_m"),
               ("worms: Begindate", "spec_begin_date"), ("worms: Enddate", "spec_end_date"), ("worms: Collector", "spec_collector"),
               ("worms: Note", "spec_note"), ("worms: Label", "spec_label"), ("worms: Phys. Location", "spec_phys_location"),
               ("worms: Alternative code", "spec_alternative_code"), ("worms: Precision", "spec_precision"),
               ("specimen_url", "spec_url")]


def specimen_columns(n, s):
    """每个名称一行的标本汇总: 多份标本按同一顺序用 ' || ' 连接 (第 k 项在各列对应同一份标本).
    有效名同时汇总挂在其异名/原始组合上的标本, spec_linked_name 注明标本挂在哪个名称上."""
    if not len(s):
        return pd.DataFrame()
    valid_of = dict(zip(n.aphia_id, n.valid_aphia_id))
    name_of = dict(zip(n.aphia_id, n.scientific_name))
    rows = []
    for r in s.to_dict("records"):
        targets = {r["aphia_id"]}
        v = valid_of.get(r["aphia_id"])
        if v and v != r["aphia_id"]:
            targets.add(v)
        for t_ in targets:
            rows.append({"aphia_id": t_, "spec_linked_name": name_of.get(r["aphia_id"], r.get("identified_as", "")),
                         **{new: str(r.get(old, "") or "") for old, new in SPEC_FIELDS}})
    d = pd.DataFrame(rows).sort_values(["aphia_id", "spec_type_status", "spec_catalog_no"])
    cols = ["spec_linked_name"] + [new for _, new in SPEC_FIELDS]
    out = d.groupby("aphia_id")[cols].agg(lambda x: " || ".join(x) if any(x) else "").reset_index()
    out.insert(1, "spec_n", d.groupby("aphia_id").size().reindex(out.aphia_id).astype(str).values)
    return out


def main(taxon):
    src, out = data_dir(taxon, "worms"), report_dir(taxon, "worms")
    n = read_tsv(src / "names.tsv")
    od = read_tsv(src / "original_descriptions.tsv", required=False)
    f = read_tsv(src / "refs.tsv", required=False)
    t = read_tsv(src / "types.tsv", required=False)
    loc = read_tsv(src / "localities.tsv", required=False)
    s = read_tsv(src / "specimens.tsv", required=False)
    qc = read_tsv(src / "qc.tsv", required=False)
    co = read_tsv(src / "coordinates.tsv", required=False)

    it = read_tsv(src / "taxdetails_items.tsv", required=False)
    dist = read_tsv(src / "distributions.tsv", required=False)
    att = read_tsv(src / "attributes.tsv", required=False)
    ver = read_tsv(src / "vernaculars.tsv", required=False)

    # 地理信息三段并排: [WoRMS 记录值] -> [标准化 Std] -> [坐标 coord]; WoRMS 记录值列一律加前缀 'WoRMS: '
    geo = pd.DataFrame({"aphia_id": n[n["rank"].isin(SP)].aphia_id})
    if len(t):
        raw_cols = ["type_locality_text", "type_locality_text_source", "type_locality_qc_source", "type_locality_contained_in",
                    "type_locality_from_synonym", "type_data_notes", "type_material", "type_dist_locality",
                    "type_dist_higher_geography", "type_dist_mrgid", "type_dist_lat", "type_dist_lon",
                    "distribution_localities", "distribution_n", "specimen_geounits", "type_depth_text"]
        geo = geo.merge(t[["aphia_id"] + [c for c in raw_cols if c in t]].rename(columns={c: f"WoRMS: {c}" for c in raw_cols}),
                        on="aphia_id", how="left")
    if len(loc):
        geo = geo.merge(loc.drop(columns=["locality_source_text"]).rename(columns=lambda c: c if c == "aphia_id" else f"Std: {c}"),
                        on="aphia_id", how="left")
    if len(t):
        geo = geo.merge(t[["aphia_id", "type_depth_min_m", "type_depth_max_m"]].rename(
            columns={"type_depth_min_m": "Std: depth_min_m", "type_depth_max_m": "Std: depth_max_m"}), on="aphia_id", how="left")
    if len(co):
        geo = geo.merge(co.drop(columns=["scientific_name"]), on="aphia_id", how="left")

    names = n.merge(od.drop(columns=["scientific_name", "authority"]), on="aphia_id", how="left") if len(od) else n
    names = names.merge(geo, on="aphia_id", how="left")
    spec = specimen_columns(n, s)
    if len(spec):
        names = names.merge(spec, on="aphia_id", how="left")
    sp = names[names["rank"].isin(SP)].copy()
    env = sp.apply(lambda r: "/".join(k for k in ["marine", "brackish", "freshwater", "terrestrial"] if r[k] == "1"), axis=1)
    keep = ["no", "aphia_id", "scientific_name", "authority", "year", "status", "is_valid", "valid_name", "valid_authority",
            "valid_subfamily", "valid_genus", "original_name", "od_citation", "od_taken_from", "od_pages_for_taxon",
            "od_doi_url", "od_link", "redescriptions"]
    summ = sp[[c for c in keep if c in sp]].copy()
    summ.insert(summ.columns.get_loc("status"), "environment_worms", env)
    summ = summ.merge(geo, on="aphia_id", how="left")
    if len(spec):
        summ = summ.merge(spec, on="aphia_id", how="left")
    dmax = pd.to_numeric(summ.get("Std: depth_max_m"), errors="coerce")
    if "spec_depth_max_m" in summ:
        dmax = dmax.fillna(summ.spec_depth_max_m.fillna("").map(lambda v: max([float(x) for x in v.split(" || ") if x] or [float("nan")])))
    dmin = pd.to_numeric(summ.get("Std: depth_min_m"), errors="coerce")
    if "spec_depth_min_m" in summ:
        dmin = dmin.fillna(summ.spec_depth_min_m.fillna("").map(lambda v: min([float(x) for x in v.split(" || ") if x] or [float("nan")])))
    summ.insert(summ.columns.get_loc("Std: depth_max_m") + 1 if "Std: depth_max_m" in summ else len(summ.columns), "Std: depth_class",
                ["" if pd.isna(lo) else ("Deep (>200 m)" if lo > 200 else ("Shallow (<=200 m)" if hi <= 200 else "Spans shallow/deep"))
                 for lo, hi in zip(dmin, dmax)])
    if len(qc):
        summ["qc_flags"] = summ.aphia_id.map(qc.groupby("aphia_id").check.apply(lambda x: "; ".join(sorted(set(x))))).fillna("")

    odcols = ["aphia_id", "scientific_name", "authority", "status", "od_taken_from", "od_citation", "od_authors", "od_year",
              "od_title", "od_journal_or_publisher", "od_volume_issue_pages", "od_pages_for_taxon", "od_doi_url", "od_link",
              "od_zoobank_lsid", "od_open_access", "od_source_id", "od_worms_source_url"]
    odsheet = names[names["rank"].isin(SP)][[c for c in odcols if c in names]] if len(od) else None

    acc = sp[(sp["rank"] == "Species") & (sp.is_valid == "Y")]
    gen = n[(n["rank"] == "Genus") & (n.is_valid == "Y")]
    gtab = pd.DataFrame([{"subfamily": g.subfamily, "genus": g.scientific_name, "authority": g.authority, "year": g.year,
                          "accepted_species": int((acc.genus == g.scientific_name).sum()),
                          "species_names_incl_synonyms": int((sp.valid_genus == g.scientific_name).sum()),
                          "accepted_species_since_2000": int(((acc.genus == g.scientific_name) & (pd.to_numeric(acc.year, errors="coerce") >= 2000)).sum()),
                          "genus_synonyms": g.synonyms, "aphia_id": g.aphia_id} for g in gen.itertuples()])
    yrs = pd.to_numeric(acc.year, errors="coerce")
    dec = acc.assign(decade=(yrs // 10 * 10).astype("Int64")).pivot_table(index="decade", columns="genus", values="aphia_id", aggfunc="count", fill_value=0)
    if len(dec):
        dec["total"] = dec.sum(axis=1)
        dec["cumulative"] = dec.total.cumsum()
        dec = dec.reset_index()

    has = lambda df, c: f"{int((df[c].fillna('') != '').sum())}/{len(df)}" if c in df else "n/a"
    notes = pd.DataFrame({"item": [
        "Source", "Date", "Taxon", "Names (all ranks)", "Species-level names", "Accepted species", "Accepted genera",
        "With original description", "With redescription", "With type locality text", "With country (normalised)",
        "Specimen records", "With coordinates (original / approximate)", "QC issues", "Column notes"], "value": [
        "WoRMS (REST + taxdetails/sourcedetails/speclist/specdetails pages), harvested by yzz workflow modules/worms 01-09",
        TODAY, taxon, len(n), len(sp), len(acc), len(gen), has(summ, "od_citation"), has(summ, "redescriptions"),
        has(summ, "WoRMS: type_locality_text"), has(summ, "Std: country"), len(s),
        (f"{int((summ.get('coord_lat', pd.Series(dtype=str)).fillna('') != '').sum())}/{len(summ)} "
         f"({int((summ.get('coord_precision', pd.Series(dtype=str)) == 'original').sum())} / "
         f"{int(summ.get('coord_precision', pd.Series(dtype=str)).fillna('').str.startswith('approximate').sum())})"), len(qc),
        "Column prefixes: 'WoRMS: ' = text extracted verbatim from WoRMS (raw, never edited); 'Std: ' = converted/standardised from the raw columns; coord_* = best coordinate with its basis. Raw sheets: Type data items / Distributions / Attributes / Vernaculars / References / Specimens. Blank = not available in WoRMS (never guessed). 'worms_taxonomic_citation' is the WoRMS database citation, NOT the original "
        "literature (see od_*). Original description falls back to the original combination when the name itself has none "
        "(od_taken_from). Environment copies WoRMS flags verbatim; implausible flags are listed in QC. Region..Water body are "
        "AI-normalised from WoRMS type-locality text only; Confidence Low = check manually. coord_*: best type-locality "
        "coordinate by evidence rank (manual > WoRMS specimen > coordinates in type text > WoRMS type distribution > "
        "geocoded locality > water-body centroid); coord_precision 'original' = given by source, 'approximate' = georeferenced "
        "centre of a named place - show differently on maps. Manual fixes: 02_原始数据/worms/coordinates_override.tsv. Depth from type data text or "
        "specimen records; >200 m = Deep."]})

    path = out / f"{taxon}_WoRMS_{TODAY}.xlsx"
    notvalid = lambda v: v == "N"
    path = write_workbook(path, {"Names": names, "Species summary": summ, "Original descriptions": odsheet,
                          "References": f, "Specimens": s, "Type data items (raw)": it, "Distributions (raw)": dist,
                          "Attributes (raw)": att, "Vernaculars (raw)": ver, "Valid genera": gtab, "Decades": dec, "QC": qc, "Notes": notes},
                   freeze={"Names": "E2", "Species summary": "E2", "Original descriptions": "D2", "Specimens": "C2"},
                   shade={"Names": [("is_valid", notvalid, GREY)], "Species summary": [("is_valid", notvalid, GREY), ("Std: confidence", "Low", YELLOW), ("coord_confidence", "Low", YELLOW)]})
    md = [f"# {taxon} — WoRMS ({TODAY})", "", *[f"- {a}: {b}" for a, b in zip(notes.item[3:14], notes.value[3:14])]]
    if len(gtab) > 1:
        md += ["", "| Subfamily | Genus | Accepted spp. | Since 2000 |", "|---|---|---|---|"]
        md += [f"| {r.subfamily} | *{r.genus}* | {r.accepted_species} | {r.accepted_species_since_2000} |" for r in gtab.sort_values(["subfamily", "genus"]).itertuples()]
    path.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    summary("19_export", [f"names {len(n)}; species-level {len(sp)}; accepted species {len(acc)}; accepted genera {len(gen)}; specimens {len(s)}; QC {len(qc)}",
                          f"original description {has(summ, 'od_citation')}; type locality text {has(summ, 'WoRMS: type_locality_text')}; Std country {has(summ, 'Std: country')}; coords {has(summ, 'coord_lat')}",
                          f"-> {path}"])


if __name__ == "__main__":
    main(sys.argv[1])
