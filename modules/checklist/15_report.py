"""15 物种采集地报表: 专著 (12) + 文献 (14) 合并 -> WoRMS 批量匹配 (现行有效名) -> Excel

输入: 02_原始数据/checklist/mono_localities.tsv (12), lit_localities.tsv (14); 缺一个也可
输出: 02_原始数据/checklist/localities_worms.tsv
      04_处理数据/checklist/<Taxon>_物种采集地.xlsx
        工作表 物种采集地 = WoRMS 科为 <Taxon> 或未匹配到的行; 非<Taxon> = 匹配到其他科的行 (备查)
        标黄 = 需核对 (parse_flag 或 WoRMS check_note 非空)
        复核: 读取 review/done_*.tsv (16 步 + 子代理按 REVIEW_PROMPT.md 看原页图): 删除/修改原值, 已核行写"人工核对"列且不再标黄.
              rid = pid|页码|原学名|采集地类型|原采集地前 10 字, 在修改前计算, 故复核结果可反复应用.
        文选重复 = 文选 (WENXUAN) 中与原刊/单行本重复的记录 (同 AphiaID + 采集地类型 + 采集地前 12 字), 主表不再列
      config.json 有 "export_dir" 时, 另复制一份 Excel 到该目录 (如 /mnt/n/沙蚕科-知识库/名录; 用户 2026-10-11 要求)
用法: python3 15_report.py <Taxon>
"""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import pandas as pd  # noqa: E402
from common import data_dir, read_tsv, report_dir, summary, write_tsv  # noqa: E402
from excel import YELLOW, write_workbook  # noqa: E402
from worms_match import MATCH_COLS, match_names  # noqa: E402

WENXUAN = {"CN02", "CN03"}      # 吴宝铃文选上下册: 收录的论文多数另有原刊/单行本
FRONT = ["物种名（中文）", "物种名（学名）", "采集地", "参考文献", "页码", "采集地类型", "note"]
WORMS = ["valid_name", "valid_authority", "status", "name_changed", "AphiaID", "valid_AphiaID",
         "match_type", "matched_name", "family", "match_info", "check_note"]


def apply_review(df, rv):
    """review/done_*.tsv: rid, 结论 (确认/修改/删除), 字段, 新值, 依据."""
    df["人工核对"], df["复核非本科"] = "", ""
    files = sorted(rv.glob("done_*.tsv")) if rv.exists() else []
    if not files:
        return df, 0
    r = pd.concat([read_tsv(f) for f in files], ignore_index=True).fillna("")
    dele = r[r["结论"] == "删除"]
    not_taxon = set(dele.loc[dele["依据"].str.contains("非沙蚕科|非本科"), "rid"])   # 其他科: 移入另表, 不丢
    df = df[~df["rid"].isin(set(dele["rid"]) - not_taxon)].copy()
    df["复核非本科"] = df["rid"].isin(not_taxon).map({True: "Y", False: ""})
    for _, x in r[r["结论"] == "修改"].iterrows():
        if x["字段"] in df.columns:
            df.loc[df["rid"] == x["rid"], x["字段"]] = x["新值"]
    basis = r[r["结论"].isin(["确认", "修改"]) | r["rid"].isin(not_taxon)].groupby("rid")["依据"].apply(lambda v: "已核: " + "; ".join(dict.fromkeys(v)))
    df["人工核对"] = df["rid"].map(basis).fillna("")
    return df, len(set(r["rid"]))


def _chars(*xs):
    import re
    from collections import Counter
    return Counter(re.sub(r"[\s；;。，,、]", "", "".join(xs)))


def apply_resplit(df, rv):
    """resplit/done_*.tsv: rid, 采集地, note, 依据. 校验: 新旧 (采集地+note) 去标点字符多重集相同, 否则拒绝并保留原值."""
    files = sorted(rv.glob("done_*.tsv")) if rv.exists() else []
    if not files:
        return df, 0, []
    r = pd.concat([read_tsv(f) for f in files], ignore_index=True).fillna("").drop_duplicates("rid", keep="last")
    idx = {rid: i for i, rid in zip(df.index, df["rid"])}
    n, rejected = 0, []
    for _, x in r.iterrows():
        i = idx.get(x["rid"])
        if i is None:
            continue
        old_l, old_n = df.at[i, "采集地"], df.at[i, "note"]
        if _chars(x["采集地"], x["note"]) != _chars(old_l, old_n):
            rejected.append(x["rid"])
            continue
        if (x["采集地"], x["note"]) != (old_l, old_n):
            df.at[i, "采集地"], df.at[i, "note"] = x["采集地"], x["note"]
            n += 1
    return df, n, rejected


def species_table(df):
    """用户 2026-10-11: 每个物种在每本书中只一行 (原先按 研究标本/文献记载分布 拆两行, 用户误以为重复).
    列: 物种名（中文）| 物种名（学名）| 采集地 (标本采集地; 新种另注模式产地) | 参考文献 | 页码 | 现行有效名 | note
    note = "标本采集地"段第一个"。"之后的说明 + "讨论："段全文 (用户 2026-10-11 示例: 羽须鳃沙蚕).
    用户 2026-10-11: 只要采集地, 不要分布地 -> "地理分布"段 (文献记载分布) 不进表, 其页码/note 也不用."""
    def j(v):
        return "；".join(dict.fromkeys(x for x in v if x))
    df = df.copy()
    df["_k"] = df["AphiaID"].where(df["AphiaID"] != "", df["物种名（学名）"].str.lower().str.split().str[:2].str.join(" "))
    rows = []
    for (_, _, _), g in df.groupby(["pid", "参考文献", "_k"], sort=False):
        c = g[g["采集地类型"].isin(["研究标本", "模式产地"])]
        spec = c[c["采集地类型"] == "研究标本"]["采集地"]
        typ = c[c["采集地类型"] == "模式产地"]["采集地"]
        loc = j(spec)
        if j(typ):
            loc = j([loc, "模式产地：" + j(typ)])
        rows.append({"物种名（中文）": j(g["物种名（中文）"]).split("；")[0], "物种名（学名）": g["物种名（学名）"].iloc[0],
                     "采集地": loc, "参考文献": g["参考文献"].iloc[0], "页码": j(c["页码"]) or j(g["页码"]),
                     "现行有效名": " ".join(x for x in (g["valid_name"].iloc[0], g["valid_authority"].iloc[0]) if x),
                     "note": j(list(c["note"]) + ["讨论：" + x for x in dict.fromkeys(g.get("讨论", pd.Series(dtype=str)).fillna("")) if x])})
    return pd.DataFrame(rows)


def main(taxon):
    d = data_dir(taxon, "checklist")
    parts = []
    for f, route in (("mono_localities.tsv", "专著解析"), ("lit_localities.tsv", "子代理抽取")):
        df = read_tsv(d / f, required=False)
        if not df.empty:
            df["来源路线"] = route
            parts.append(df)
    if not parts:
        raise SystemExit("缺少 mono_localities.tsv / lit_localities.tsv: 先跑 12 或 13-14")
    df = pd.concat(parts, ignore_index=True).fillna("")
    df["rid"] = df["pid"] + "|" + df["页码"] + "|" + df["物种名（学名）"] + "|" + df["采集地类型"] + "|" + df["采集地"].str[:10]
    df, n_rv = apply_review(df, d / "review")
    df, n_rs, rs_rej = apply_resplit(df, d / "resplit")
    df["note"] = df["note"].str.replace(r"\s*\[注: 第一个“。”后仍有采集地点[^\]]*\]", "", regex=True).str.strip()   # 旧规则留下的注释, 重分后失效
    if rs_rej:
        print(f"   重分被拒绝 {len(rs_rej)} 行 (字符对不上, 保留原值): {rs_rej[:3]}")
    res = match_names(df["物种名（学名）"].tolist(), taxon)
    empty = dict.fromkeys(MATCH_COLS, "")
    m = pd.DataFrame([res.get(v.strip(), empty) for v in df["物种名（学名）"]], index=df.index)
    rest = [c for c in df.columns if c not in FRONT]
    out = pd.concat([df[FRONT], m[WORMS], df[rest]], axis=1)
    flagged = (out["parse_flag"] != "") | (out["check_note"] != "")
    out["需核对"] = (flagged & (out["人工核对"] == "")).map({True: "Y", False: ""})
    taxon_key = out["AphiaID"].where(out["AphiaID"] != "", out["物种名（学名）"].str.lower().str.split().str[:2].str.join(" "))
    loc_key = out["采集地"].str.replace(r"[\s，、；;,.。()（）]", "", regex=True).str[:12]
    key = taxon_key + "|" + out["采集地类型"] + "|" + loc_key
    in_wx = out["pid"].isin(WENXUAN)
    dup = in_wx & key.isin(set(key[~in_wx]))
    dup_rows, out = out[dup], out[~dup]
    write_tsv(out, d / "localities_worms.tsv")
    other = (out["family"].ne("") & out["family"].ne(taxon)) | out["复核非本科"].eq("Y")
    xlsx = write_workbook(report_dir(taxon, "checklist") / f"{taxon}_物种采集地.xlsx",
                          {"物种采集地": out[~other], f"非{taxon}": out[other], "文选重复": dup_rows},
                          freeze={"物种采集地": "C2"},
                          shade={"物种采集地": [("需核对", "Y", YELLOW)]})
    keep = out[~other]
    exp = json.loads((d / "config.json").read_text(encoding="utf-8")).get("export_dir") if (d / "config.json").exists() else None
    simple = species_table(keep)
    simple_x = write_workbook(report_dir(taxon, "checklist") / f"{taxon}_物种名录.xlsx", {"物种名录": simple},
                              freeze={"物种名录": "C2"})
    if exp:                      # 知识库只放简表 (用户: 只要书中物种信息, 不要别的表)
        Path(exp).mkdir(parents=True, exist_ok=True)
        shutil.copy2(simple_x, Path(exp) / Path(simple_x).name)
        print(f"   简表 {len(simple)} 行 -> {Path(exp) / Path(simple_x).name}")
    summary("15_report", [f"{keep['物种名（学名）'].nunique()} 个学名 / {len(keep)} 行 -> {xlsx}",
                          f"异名→有效名 {int((keep['name_changed'] == 'Y').sum())} 行; 需核对(标黄) {int((keep['需核对'] == 'Y').sum())} 行; 非{taxon} {int(other.sum())} 行另表"])


if __name__ == "__main__":
    main(sys.argv[1])
