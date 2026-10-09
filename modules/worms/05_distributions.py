"""05 分布记录 (提取层): WoRMS Documented distribution 全部记录 (含非模式记录) -> distributions.tsv

只照搬 WoRMS 记录值, REST AphiaDistributionsByAphiaID 每个字段原样保留.
输入: names.tsv (种级名称)
输出: 02_原始数据/worms/distributions.tsv  每行 = 一个名称的一条分布记录
字段 (WoRMS 原名): locality, locationID (Marine Regions MRGID), higherGeography, higherGeographyID, recordStatus,
      typeStatus (模式产地标记), establishmentMeans, invasiveness, occurrence, decimalLatitude, decimalLongitude,
      qualityStatus, sourceID, sourceReference ... (WoRMS 返回什么就保留什么)
用法: python3 05_distributions.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import clean, data_dir, read_tsv, summary, write_tsv
from worms import client, pmap

SP = {"Species", "Subspecies", "Variety", "Forma"}


def one(aid):
    return [{"aphia_id": aid, **{k: clean(v) for k, v in d.items()}} for d in (client().distributions(int(aid)) or [])]


def main(taxon):
    out = data_dir(taxon, "worms")
    n = read_tsv(out / "names.tsv")
    ids = list(n[n["rank"].isin(SP)].aphia_id)
    res = pmap(one, ids)
    d = pd.DataFrame([x for r in res if r for x in r])
    if not len(d):
        d = pd.DataFrame(columns=["aphia_id", "locality", "typeStatus"])
    write_tsv(d, out / "distributions.tsv")
    ts = d.get("typeStatus", pd.Series(dtype=str)).fillna("") != ""
    coords = d.get("decimalLatitude", pd.Series(dtype=str)).fillna("") != ""
    summary("05_distributions", [f"{len(d)} distribution records on {d.aphia_id.nunique()} names (type-status {int(ts.sum())}, "
                                 f"other {int((~ts).sum())}); with coordinates {int(coords.sum())}; failed {sum(r is None for r in res)}",
                                 f"-> {out / 'distributions.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
