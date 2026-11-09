"""07 合并导出: seed_worms + additions (+ worms_env_candidates 作待核附表) -> 名录 Excel

主表前 5 列固定: 物种名 | 科 | 目 | 生境类型 | 参考文献 ; 其后为追溯列.
- 物种名/科/目 取 WoRMS 有效名与分类 (WoRMS 无“目”时目列留空, 在“WoRMS上级阶元”列给出亚纲/下纲).
- 生境类型: 底本按 config.habitat_rule 由 Ecology 代码换算; 新文献按子代理判定; 多来源冲突 -> 合并为“均可”并标注.
- 参考文献: 原始描述 (WoRMS 作者年份) + 生境依据文献.
输出: 04_处理数据/habitat/<Taxon>_checklist_<date>.xlsx + 02_原始数据/habitat/checklist.tsv
用法: python3 07_build.py <Taxon>
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import pandas as pd
from common import TODAY, data_dir, read_tsv, report_dir, summary, write_tsv

MAIN = ["物种名", "科", "目", "生境类型", "参考文献"]
# a species row needs a scientific name: Genus [(Subgenus)] epithet|sp./cf./aff. ...; descriptive text stays in 生境证据
BINOMIAL = re.compile(r"^[A-Z][a-z]+(?: \([A-Z][a-z]+\))? (?:[a-z][a-z\-]+|sp\.|spp\.|cf\.|aff\.|nr\.)(?: |$)")


def habitat_from_codes(eco):
    codes = set(re.findall(r"\b(FW|FT|ST|T)\b", eco or ""))
    if "FT" in codes or {"FW", "ST"} <= codes:
        return "均可"
    if codes == {"FW"} or codes == {"FW", "T"}:
        return "纯淡水"
    if codes == {"ST"}:
        return "半盐水"
    if codes == {"T"}:
        return "陆生"
    return ""


def combine(habs):
    h = {x for x in habs if x}
    if not h:
        return ""
    if len(h) == 1:
        return h.pop()
    aquatic = h - {"陆生"}
    if aquatic == {"纯淡水"}:
        return "纯淡水"
    return "均可"


def not_poly(r):
    lin = r.get("lineage", "")
    return "" if not lin or "Polychaeta" in lin else f"WoRMS 不归入 Polychaeta ({higher(r) or lin})"


def higher(r):
    """WoRMS 无目级时给出科以上的完整 WoRMS 路径 (Annelida 以下)."""
    lin = r.get("lineage", "")
    if "Annelida > " in lin:
        lin = lin.split("Annelida > ", 1)[1]
    return lin.split(" > " + r["family"])[0] if r.get("family") and r["family"] in lin else lin


def main(taxon):
    d = data_dir(taxon, "habitat")
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    short = cfg["seed"]["short"]
    seed = read_tsv(d / "seed_worms.tsv")
    add = read_tsv(d / "additions.tsv", required=False)

    rows = {}
    for r in seed.to_dict("records"):
        name = r["accepted_name"] or re.sub(r"\s*\([^)]*\)\s*$", "", r["glasby_name"])
        key = r["accepted_aphia_id"] or "seed:" + r["glasby_name"]
        auth = r["accepted_authority"]
        if key in rows:          # two Glasby entries -> one WoRMS valid name: keep one row, record both
            x = rows[key]
            x["_habs"].append(habitat_from_codes(r["ecology"]))
            x["_refs"].append(f"生境: {short}, p. {r['page']}")
            x["Glasby名称"] += " | " + r["glasby_name"]
            x["备注"] = "; ".join(filter(None, [x["备注"], f"Glasby 2009 另列 {r['glasby_name']}, WoRMS 归为同一有效名"]))
            continue
        rows[key] = {
            "物种名": f"{name} {auth}".strip(),
            "科": r["family"] or r["glasby_family"],
            "目": r["order"],
            "生境类型": habitat_from_codes(r["ecology"]),
            "_habs": [habitat_from_codes(r["ecology"])],
            "_refs": [f"原始描述: {auth}" if auth else "", f"生境: {short}, p. {r['page']}"],
            "WoRMS上级阶元": "" if r["order"] else higher(r),
            "来源": "Glasby et al. 2009",
            "Glasby名称": r["glasby_name"] + (" species group" if r["species_group"] == "Y" else ""),
            "Glasby_Ecology": r["ecology"], "Glasby_Habitat": r["habitat"], "Glasby_Distribution": r["distribution"],
            "WoRMS状态": r["worms_status"], "WoRMS_AphiaID": r["accepted_aphia_id"] or r["worms_aphia_id"],
            "WoRMS淡水/半咸/海洋": "/".join(r[k] or "-" for k in ("is_freshwater", "is_brackish", "is_marine")),
            "可信度": "确证", "备注": "; ".join(filter(None, [r["worms_note"], not_poly(r)])),
        }
    evidence = []
    if len(add):
        for r in add.to_dict("records"):
            key = r["accepted_aphia_id"] or "add:" + r["species"]
            evidence.append(r)
            if (r["habitat_cn"] == "排除" or re.search(r"\bspp\.?$|^\S+$", r["species"].strip())
                    or not BINOMIAL.match(r["species"].strip())):     # genus-level only: evidence sheet, not a species row
                continue
            ref = f"生境: {r['reference']}" + (f", p. {r['page']}" if r.get("page") else "")
            ym = re.search(r"\((1[789]\d\d|20[012]\d)[a-z]?\)|\b(1[789]\d\d|20[012]\d)\b", r["reference"] or "")
            ref_year = int(next(g for g in ym.groups() if g)) if ym else None
            if key in rows:
                x = rows[key]
                x.setdefault("_years", []).append(ref_year)
                if r["confidence"] == "确证" and (ref_year or 0) >= 2009:
                    x["_post_confirmed"] = True
                x["_habs"].append(r["habitat_cn"])
                x["_refs"].append(ref)
                if x["来源"] == "Glasby et al. 2009":
                    x["来源"] = "Glasby et al. 2009 + 新文献"
                continue
            name = r["accepted_name"] or r["species"]
            auth = r["accepted_authority"] or r["authority"]
            rows[key] = {
                "物种名": f"{name} {auth}".strip(), "科": r["family"], "目": r["order"], "生境类型": r["habitat_cn"],
                "_habs": [r["habitat_cn"]], "_refs": [f"原始描述: {auth}" if auth else "", ref],
                "WoRMS上级阶元": "" if r["order"] else higher(r), "来源": "2009 年后文献",
                "Glasby名称": "", "Glasby_Ecology": "", "Glasby_Habitat": "", "Glasby_Distribution": "",
                "WoRMS状态": r["worms_status"], "WoRMS_AphiaID": r["accepted_aphia_id"] or r["worms_aphia_id"],
                "WoRMS淡水/半咸/海洋": "/".join(r[k] or "-" for k in ("is_freshwater", "is_brackish", "is_marine")),
                "可信度": r["confidence"] or "待核",
                "备注": "; ".join(filter(None, [r["worms_note"], not_poly(r)])),
                "_years": [ref_year], "_post_confirmed": r["confidence"] == "确证" and (ref_year or 0) >= 2009,
            }
    out = []
    for x in rows.values():
        years = [y for y in x.pop("_years", []) if y]
        post = x.pop("_post_confirmed", False)
        if x["来源"] == "2009 年后文献" and years and max(years) < 2009:
            x["来源"] = "2009 年前文献 (Glasby 2009 未收)"
            x["可信度"] = "待核"
            x["备注"] = "; ".join(filter(None, [x["备注"], f"依据均为 {min(years)}-{max(years)} 年文献而 Glasby 2009 未收录: "
                                                  "Glasby 等审阅过这些文献, 可能有意排除, 需人工判断"]))
        elif x["来源"] == "2009 年后文献" and post:
            x["可信度"] = "确证"
        merged = combine(x["_habs"])
        if merged != x["生境类型"]:
            x["备注"] = "; ".join(filter(None, [x["备注"], f"生境由“{x['生境类型']}”按新文献合并为“{merged}”"]))
            x["生境类型"] = merged
        x["参考文献"] = "; ".join(dict.fromkeys(r for r in x.pop("_refs") if r))
        x.pop("_habs")
        out.append(x)
    t = pd.DataFrame(out)
    t = t[MAIN + [c for c in t.columns if c not in MAIN]].sort_values(["科", "物种名"]).reset_index(drop=True)
    t.insert(0, "序号", range(1, len(t) + 1))
    write_tsv(t, d / "checklist.tsv")

    xlsx = report_dir(taxon, "habitat") / f"{taxon}_checklist_{TODAY}.xlsx"
    notes = pd.DataFrame({"项目": ["范围", "生境类型规则", "分类系统", "底本", "新增文献", "可信度", "生成日期"],
                          "说明": [cfg.get("title", ""), cfg.get("habitat_rule", ""),
                                   "WoRMS 有效名与分类 (查询日期见生成日期); WoRMS 无目级时“目”留空, 见“WoRMS上级阶元”",
                                   cfg["seed"]["citation"],
                                   "引文滚雪球 (OpenAlex/Semantic Scholar) + 关键词检索, 子代理按规则抽取, 见“生境证据”表",
                                   "确证 = 原文明确; 待核 = 摘要推断或信息不全, 需人工核对原文", TODAY]})
    with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
        t.to_excel(w, sheet_name="名录", index=False)
        if evidence:
            pd.DataFrame(evidence).to_excel(w, sheet_name="生境证据", index=False)
        env = d / "worms_env_candidates.tsv"
        if env.exists():
            e = read_tsv(env)
            if len(e):
                e[e["in_checklist"] == ""].to_excel(w, sheet_name="WoRMS候选_未核", index=False)
        notes.to_excel(w, sheet_name="说明", index=False)
    from openpyxl import load_workbook
    from openpyxl.styles import Font
    wb = load_workbook(xlsx)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                c.font = Font(name="宋体", bold=c.row == 1)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(60, max(10, max(len(str(c.value or "")) for c in col[:200]) + 2))
        ws.freeze_panes = "B2"
    wb.save(xlsx)
    vc = t["生境类型"].value_counts().to_dict()
    summary("07_build", [f"{len(t)} 种 ({t['来源'].value_counts().to_dict()})", f"生境: {vc}",
                         f"待核 {(t['可信度'] == '待核').sum()}; 目为空 {(t['目'] == '').sum()} -> {xlsx.name}"])


if __name__ == "__main__":
    main(sys.argv[1])
