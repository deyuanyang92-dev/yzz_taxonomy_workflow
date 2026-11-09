"""05 原始描述原文 -> oworms: 模式产地原文抽取与 WoRMS 复查

本地库 (03 步 treatment.csv) 中每个种的原始描述 (L3) 原文导出为 oworms --od-text 表, 再调用 oworms:
  oworms 10 od_text   原文 -> 模式产地片段/经纬度/国家
  oworms 14           WoRMS 无模式产地时用原文; 原文写明经纬度时优先于 WoRMS 近似点
  oworms 16           分布记录 vs 模式产地 (模式产地变了, 远距判定随之更新)
  oworms 17 tl_verify WoRMS 模式产地/坐标逐种对照原文 (agree / close / conflict / OD finer ...)
  oworms 19           Excel (表 "TL check vs OD")
抽取与复查规则全部在 oworms (github.com/deyuanyang92-dev/oworms); 本脚本只准备输入、调用 oworms.
输出: 08_知识库/结构化/od_texts.tsv (oworms 输入); 结果在 oworms 输出目录 data/od_type_locality.tsv, type_locality_verify.tsv
用法: python3 yzz.py compilation 05 <项目目录>
"""
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from common import worms_root  # noqa: E402


def main():
    S = cfg.S
    tr = pd.read_csv(S / "treatment.csv", dtype=str).fillna("")
    wk = pd.read_csv(S / "work.csv", dtype=str).fillna("").set_index("work_id") if (S / "work.csv").exists() else pd.DataFrame()
    od = tr[tr.level == "L3"]

    def title(w):
        return re.sub(r"^.*?\(\d{4}[a-z]?\)\.\s*", "", wk.at[w, "citation"]) if len(wk) and w in wk.index else ""

    out = pd.DataFrame({"scientific_name": od.taxon, "text": od.original_text, "source": od.work_id, "pages": od.pages,
                        "language": od.language, "title": od.work_id.map(title), "authority": od.taxon_valid_full})
    p = S / "od_texts.tsv"
    out.to_csv(p, sep="\t", index=False)
    print(f"[05_type_locality] {len(out)} original-description texts ({out.scientific_name.nunique()} taxa) -> {p}")
    root = worms_root(cfg.GENUS)
    cmd = ["oworms", "run", cfg.GENUS, "--out", str(root.parent), "--steps", "10,14,16,17,19", "--od-text", str(p)]
    print("   " + " ".join(cmd), flush=True)
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
