"""02 WoRMS 校正: seed.tsv 的每个名称 -> 有效名、科、目、WoRMS 环境标记 -> seed_worms.tsv

用法: python3 02_worms_match.py <Taxon>
说明: 有效名/科/目只取 WoRMS 原值; 匹配不上或非精确匹配写入 worms_note, 不猜.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
sys.path.insert(0, str(HERE))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv
from wormsmatch import match


def main(taxon):
    d = data_dir(taxon, "habitat")
    seed = read_tsv(d / "seed.tsv")
    m = pd.DataFrame(match(seed["glasby_name"]))
    out = pd.concat([seed.reset_index(drop=True), m], axis=1)
    write_tsv(out, d / "seed_worms.tsv")
    notes = out["worms_note"].str.len() > 0
    syn = (out["worms_status"] != "accepted") & (out["accepted_name"] != "")
    summary("02_worms_match", [f"{len(out)} 名: 有效名 {(out['worms_status'] == 'accepted').sum()}, "
                               f"已变更为其他有效名 {syn.sum()}, 需人工看 worms_note {notes.sum()} -> seed_worms.tsv"])


if __name__ == "__main__":
    main(sys.argv[1])
