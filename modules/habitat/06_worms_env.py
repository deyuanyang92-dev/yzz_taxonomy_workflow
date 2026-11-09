"""06 WoRMS 环境标记候选: 遍历相关科 (marine_only=false), 找 WoRMS 标为淡水/非海洋但不在名录中的有效种 -> worms_env_candidates.tsv

科来源: seed_worms.tsv 的 family 列 ∪ additions.tsv 的 family 列 ∪ config.extra_families.
候选条件: 有效种 (accepted) 且 isFreshwater=1, 或 isBrackish=1 且 isMarine=0.
WoRMS 环境标记有错 (见 worms README), 候选只作为待核线索, 须经文献核实才进名录.
用法: python3 06_worms_env.py <Taxon>
"""
import json, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
sys.path.insert(0, str(HERE))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv
from worms import REST, client
from wormsmatch import _get, query_name

SPECIES = {"Species", "Subspecies"}


def children(c, aid):
    out, off = [], 1
    while True:
        for i in range(4):
            try:
                page = _get(c, f"{REST}/AphiaChildrenByAphiaID/{aid}",
                            params={"marine_only": "false", "extant_only": "true", "offset": off})
                break
            except Exception:
                time.sleep(5 * (i + 1))
        else:
            print(f"   !! children {aid} offset {off} 失败, 跳过", file=sys.stderr)
            return out
        if not page:
            return out
        out += page
        if len(page) < 50:
            return out
        off += 50


def walk(c, aid):
    """All accepted species/subspecies under aid."""
    found, stack = [], [aid]
    while stack:
        for r in children(c, stack.pop()):
            if r.get("status") != "accepted":
                continue
            if r.get("rank") in SPECIES:
                found.append(r)
            else:
                stack.append(r["AphiaID"])
    return found


def main(taxon):
    d = data_dir(taxon, "habitat")
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    seed = read_tsv(d / "seed_worms.tsv")
    add = read_tsv(d / "additions.tsv", required=False)
    fams = set(seed["family"]) | (set(add["family"]) if len(add) else set()) | set(cfg.get("extra_families", []))
    fams = sorted(f for f in fams if f)
    known = set(seed["accepted_name"]) | {query_name(n)[0] for n in seed["glasby_name"]}
    if len(add):
        known |= set(add.get("accepted_name", pd.Series(dtype=str))) | set(add["species"])
    c = client(delay=0.1)
    rows = []
    for fam in fams:
        fid = _get(c, f"{REST}/AphiaIDByName/{fam}", params={"marine_only": "false"})
        if fid == -999 or (fid and int(fid) < 0):    # ambiguous name (homonyms): take the accepted Annelida family
            recs = _get(c, f"{REST}/AphiaRecordsByName/{fam}", params={"like": "false", "marine_only": "false"}) or []
            recs = [r for r in recs if r.get("rank") == "Family" and r.get("status") == "accepted"
                    and r.get("phylum") == "Annelida"]
            fid = recs[0]["AphiaID"] if recs else None
        if not fid or int(fid) < 0:
            print(f"   !! 科 {fam} 无 AphiaID", file=sys.stderr)
            continue
        for r in walk(c, fid):
            fw, br, ma = r.get("isFreshwater"), r.get("isBrackish"), r.get("isMarine")
            if not (fw == 1 or (br == 1 and ma != 1)):
                continue
            rows.append({"family": fam, "species": r["scientificname"], "authority": r.get("authority") or "",
                         "aphia_id": r["AphiaID"], "is_marine": ma, "is_brackish": br, "is_freshwater": fw,
                         "is_terrestrial": r.get("isTerrestrial"), "in_checklist": "Y" if r["scientificname"] in known else "",
                         "worms_url": f"https://www.marinespecies.org/aphia.php?p=taxdetails&id={r['AphiaID']}"})
    out = pd.DataFrame(rows)
    write_tsv(out, d / "worms_env_candidates.tsv")
    new = out[out["in_checklist"] == ""] if len(out) else out
    summary("06_worms_env", [f"{len(fams)} 科; WoRMS 非海洋标记有效种 {len(out)}, 其中不在名录 {len(new)} -> worms_env_candidates.tsv"])


if __name__ == "__main__":
    main(sys.argv[1])
