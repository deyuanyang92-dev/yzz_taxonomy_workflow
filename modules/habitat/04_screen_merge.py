"""04 合并筛选结果: screen/decided_*.tsv (id, decision, reason; 子代理写) -> works.tsv 的 decision/reason

筛选由 sonnet 子代理按 config.screening_rules 完成, 每个子代理读一个 to_screen_*.tsv 分块, 写 decided_<同名>.tsv.
用法: python3 04_screen_merge.py <Taxon>
      python3 04_screen_merge.py <Taxon> --prefilter <round>   关键词预过滤: 标题/摘要无多毛类类群词且无淡水/低盐词
                                                               -> 自动判 no (decided_prefilter_<round>.tsv),
                                                               其余写 to_screen_<round>_kw.tsv 交子代理
"""
import argparse, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv

VALID = {"yes", "maybe", "no"}


HAB = r"fresh.?water|brackish|oligohalin|limnic|non.?marine|inland|river|lake|stream|cave|ground.?water|stygo|" \
      r"hyporheic|spring|estuar|lagoon|low salinity|salinity|caspian|aral|phytotelm|terrestrial|soil|swamp|mangrove"
TAX = r"polychaet|annelid|nereid|spionid|sabellid|serpulid|capitellid|aeolosom|histriobdell|ampharetid|nephtyid|" \
      r"namanereid|fanworm|ragworm|bristle.?worm|parergodril|potamodril|nerillid|protodril|hrabeiell"


FAUNA = r"fauna|benth|invertebrat|zoobenth|macrobenth|worms?\b|commensal|epizo|crab|crustacea|stygobio"


def keep_mask(text, rx):
    """Keep = taxon word, or (habitat word and fauna word). Validated on rounds 1+S (2026-10-11):
    requiring taxon AND habitat lost 10 of 137 productive works."""
    return text.str.contains(rx) | (text.str.contains(re.compile(HAB, re.I)) & text.str.contains(re.compile(FAUNA, re.I)))


def prefilter(d, rnd):
    seed = read_tsv(d / "seed_worms.tsv")
    add = read_tsv(d / "additions.tsv", required=False)
    names = set(seed["glasby_name"].str.split().str[0]) | set(seed["genus"])
    if len(add):
        names |= set(add["species"].str.split().str[0])
    names = {n for n in names if n and n[0].isupper() and len(n) > 3}
    rx = re.compile(TAX + "|" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)), re.I)
    t = read_tsv(d / "screen" / f"to_screen_round{rnd}.tsv")
    text = t["title"] + " " + t["abstract"]
    keep = keep_mask(text, rx)
    no = t[~keep][["id"]].assign(decision="no", reason="prefilter: no polychaete taxon word and no habitat+fauna words")
    write_tsv(no, d / "screen" / f"decided_prefilter_{rnd}.tsv")
    write_tsv(t[keep], d / "screen" / f"to_screen_{rnd}_kw.tsv")
    summary("04_prefilter", [f"第 {rnd} 轮 {len(t)} 篇: 自动 no {len(no)}, 交子代理 {keep.sum()} -> to_screen_{rnd}_kw.tsv"])


def main(taxon):
    d = data_dir(taxon, "habitat")
    works = read_tsv(d / "works.tsv")
    dec = [read_tsv(p) for p in sorted((d / "screen").glob("decided_*.tsv"))]
    if not dec:
        raise SystemExit("screen/ 下没有 decided_*.tsv")
    dec = pd.concat(dec).drop_duplicates("id", keep="last")
    dec["decision"] = dec["decision"].str.strip().str.lower()
    bad = dec[~dec["decision"].isin(VALID)]
    dec = dec[dec["decision"].isin(VALID)].set_index("id")
    hit = works["id"].isin(dec.index)
    works.loc[hit, "decision"] = works.loc[hit, "id"].map(dec["decision"])
    works.loc[hit, "reason"] = works.loc[hit, "id"].map(dec["reason"])
    write_tsv(works, d / "works.tsv")
    pend = (works["decision"] == "").sum()
    vc = works.loc[hit, "decision"].value_counts().to_dict()
    unknown = len(set(dec.index) - set(works["id"]))
    summary("04_screen_merge", [f"写回 {hit.sum()} 篇: {vc}; 仍未筛 {pend} 篇",
                                f"无效决定 {len(bad)} 行, works.tsv 中找不到的 id {unknown} 个"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("taxon")
    ap.add_argument("--prefilter")
    a = ap.parse_args()
    if a.prefilter:
        prefilter(data_dir(a.taxon, "habitat"), a.prefilter)
    else:
        main(a.taxon)
