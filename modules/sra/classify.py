"""数据类型派生 (NCBI 无"浅层"字段, 按样本数据量推断) + 样本/物种汇总 + 下载清单筛选. 纯函数, 无网络."""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CATEGORY_ORDER = ["shallow_WGS", "deep_WGS", "long_read_WGS", "low_data_WGS", "RNA-Seq", "long_read_RNA", "Hi-C",
                  "RAD-Seq", "AMPLICON", "WGS_metagenomic"]
SAMPLE_INFO = ["experiment_title", "study_title", "geo_loc_name", "lat_lon", "collection_date",
               "specimen_voucher", "isolate", "tissue"]
LINEAGE = ["rank_derived", "phylum", "class", "order", "family", "genus", "species"]


def load_rules(path=None):
    return json.loads(Path(path or HERE / "rules.json").read_text(encoding="utf-8"))


def platform_type(platform, rules):
    p = str(platform or "").upper()
    if p in rules["long_platforms"]:
        return "long"
    if p in rules.get("other_platforms", []) or not p:
        return "other"
    return "short"


def _col(df, name):
    return df[name].fillna("").astype(str) if name in df else pd.Series([""] * len(df), index=df.index)


def classify_runs(df, rules):
    """加 platform_type_derived / sample_key_derived / sample_total_Gb_derived / category_derived / category_rule_derived."""
    df = df.copy()
    strat = _col(df, "LibraryStrategy").str.upper()
    sel = _col(df, "LibrarySelection").str.upper()
    src = _col(df, "LibrarySource").str.upper()
    gb = pd.to_numeric(_col(df, "bases"), errors="coerce").fillna(0) / 1e9
    df["platform_type_derived"] = [platform_type(p, rules) for p in _col(df, "Platform")]
    bs = _col(df, "BioSample").str.strip()
    df["sample_key_derived"] = bs.where(bs != "", _col(df, "Run"))
    # LibrarySelection=PCR 不排除: Annelida 实测 WGS+PCR 多为 genome skimming / 基因组数据, 只在 QC 提示
    excluded = (strat == "WGS") & src.isin([x.upper() for x in rules["metagenomic_sources"]])
    grp = [df["sample_key_derived"], strat, df["platform_type_derived"]]
    total = gb.where(~excluded, 0).groupby(grp).transform("sum")
    df["sample_total_Gb_derived"] = total.where(~excluded, gb).round(3)
    lo, hi = rules["low_max_gb"], rules["shallow_max_gb"]
    cats, why = [], []
    for i in range(len(df)):
        s, t, g = strat.iat[i], df["platform_type_derived"].iat[i], df["sample_total_Gb_derived"].iat[i]
        raw = _col(df, "LibraryStrategy").iat[i]
        if excluded.iat[i]:
            c, w = "WGS_metagenomic", f"WGS & {src.iat[i]} -> WGS_metagenomic"
        elif s == "WGS" and t == "long":
            c, w = "long_read_WGS", f"WGS & {df['Platform'].iat[i]} -> long_read_WGS"
        elif s == "WGS" and t == "short":
            if g < lo:
                c, rng = "low_data_WGS", f"< {lo:g}"
            elif g < hi:
                c, rng = "shallow_WGS", f"in [{lo:g},{hi:g})"
            else:
                c, rng = "deep_WGS", f">= {hi:g}"
            w = f"WGS & {sel.iat[i]} & short & {g:.2f} Gb {rng} -> {c}"
        elif s == "RNA-SEQ" and t == "long":
            c, w = "long_read_RNA", "RNA-Seq & long -> long_read_RNA"
        else:
            c, w = raw or "unknown", f"LibraryStrategy={raw}"
        cats.append(c)
        why.append(w)
    df["category_derived"], df["category_rule_derived"] = cats, why
    return df


def _join(xs):
    out = []
    for x in xs:
        x = str(x)
        if x and x != "nan" and x not in out:
            out.append(x)
    return ";".join(out)


def _first(xs):
    for x in xs:
        if str(x) not in ("", "nan"):
            return x
    return ""


def summarize_samples(df):
    """一行一个 样本 × 数据类型 (挑选用)."""
    cols = ["sample_key_derived", "category_derived", "TaxID", "ScientificName", "BioProject", "BioSample",
            "n_runs", "total_Gb", "Platform", "LibraryLayout", "runs"]
    extra = [c for c in LINEAGE + SAMPLE_INFO if c in df]
    if df.empty:
        return pd.DataFrame(columns=cols + extra)
    d = df.copy()
    d["_gb"] = pd.to_numeric(_col(d, "bases"), errors="coerce").fillna(0) / 1e9
    out = []
    for (key, cat), g in d.groupby(["sample_key_derived", "category_derived"], sort=False):
        r = {"sample_key_derived": key, "category_derived": cat, "n_runs": len(g),
             "total_Gb": round(g["_gb"].sum(), 3), "runs": _join(g["Run"]),
             "Platform": _join(_col(g, "Platform")), "LibraryLayout": _join(_col(g, "LibraryLayout"))}
        for c in ["TaxID", "ScientificName", "BioProject", "BioSample"] + extra:
            r[c] = _first(_col(g, c))
        out.append(r)
    return pd.DataFrame(out, columns=cols + extra)


def ordered_categories(cats):
    cats = list(dict.fromkeys(cats))
    return [c for c in CATEGORY_ORDER if c in cats] + sorted(c for c in cats if c not in CATEGORY_ORDER)


def summarize_species(samples, taxonomy):
    """一行一个 TaxID: 阶元 + 各数据类型的样本数与 Gb."""
    if samples.empty:
        return pd.DataFrame(columns=["TaxID", "ScientificName"] + LINEAGE)
    s = samples.copy()
    s["TaxID"] = s["TaxID"].astype(str).str.replace(r"\.0$", "", regex=True)
    base = s.groupby("TaxID", sort=False)["ScientificName"].first().reset_index()
    tax = taxonomy[["TaxID"] + [c for c in LINEAGE if c in taxonomy]] if len(taxonomy) else pd.DataFrame(columns=["TaxID"])
    base = base.merge(tax.astype(str), on="TaxID", how="left")
    for cat in ordered_categories(s["category_derived"]):
        g = s[s.category_derived == cat].groupby("TaxID")
        base[f"{cat}_samples"] = base["TaxID"].map(g.size()).fillna(0).astype(int)
        base[f"{cat}_Gb"] = base["TaxID"].map(g["total_Gb"].sum()).fillna(0).round(3)
    return base.fillna("")


def _keep(df, types, platforms, layout, plat_col="Platform"):
    m = df["category_derived"].isin(types)
    if platforms:
        want = {p.upper() for p in platforms}
        m &= _col(df, plat_col).str.upper().str.split(";").apply(lambda xs: bool(want & set(xs)))
    if layout.upper() != "ALL":
        m &= _col(df, "LibraryLayout").str.upper().str.contains(layout.upper(), regex=False)
    return df[m]


def select_samples(samples, types, platforms, layout, top, per="sample", runs=None):
    """每 TaxID×BioProject×类型 取数据量最大的 top 个样本 (per="run" 时按 run, 需传 runs 表 = 旧脚本行为)."""
    keys = ["TaxID", "BioProject", "category_derived"]
    if per == "run":
        r = _keep(runs, types, platforms, layout).copy()
        r["total_Gb"] = (pd.to_numeric(_col(r, "bases"), errors="coerce").fillna(0) / 1e9).round(3)
        r = r.sort_values("total_Gb", ascending=False, kind="stable").groupby(keys, sort=False).head(top)
        return r.assign(runs=r["Run"])
    if samples.empty:
        return samples
    s = _keep(samples, types, platforms, layout).copy()
    s["_gb"] = pd.to_numeric(s["total_Gb"], errors="coerce").fillna(0)
    s = s.sort_values("_gb", ascending=False, kind="stable").groupby(keys, sort=False).head(top)
    return s.drop(columns="_gb")
