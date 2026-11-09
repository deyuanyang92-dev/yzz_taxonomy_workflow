"""14 文献抽取合并: lit_inbox/done_*.tsv -> lit_localities.tsv (校验列名, 记录来源块)

输入: 02_原始数据/checklist/lit_inbox/done_<pid>_<k>.tsv (子代理按 LIT_PROMPT.md 输出)
输出: 02_原始数据/checklist/lit_localities.tsv
用法: python3 14_lit_merge.py <Taxon>
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import pandas as pd  # noqa: E402
from common import data_dir, read_tsv, summary, write_tsv  # noqa: E402

COLS = ["物种名（中文）", "物种名（学名）", "采集地", "参考文献", "页码", "采集地类型", "note", "原文摘录", "把握度"]
TYPES = {"研究标本", "模式产地", "文献记载分布"}


def main(taxon):
    inbox = data_dir(taxon, "checklist") / "lit_inbox"
    todo = sorted(p.stem[5:] for p in inbox.glob("todo_*.md"))
    parts, bad = [], []
    for tid in todo:
        f = inbox / f"done_{tid}.tsv"
        if not f.exists():
            continue
        df = read_tsv(f)
        miss = [c for c in COLS if c not in df.columns]
        if miss:
            bad.append(f"{f.name} 缺列 {miss}")
            continue
        df = df[COLS].copy()
        df["pid"], df["块"] = tid.rsplit("_", 1)[0], tid
        flags = []
        for _, r in df.iterrows():
            f_ = []
            if r["采集地类型"] not in TYPES:
                f_.append(f"采集地类型非法: {r['采集地类型']}")
            if r["把握度"] == "低":
                f_.append("子代理低把握度")
            if re.search(r"补|推得|推定|推算", r["note"]):
                f_.append("含原文以外推断/补充, 核对")
            flags.append("; ".join(f_))
        df["parse_flag"] = flags
        parts.append(df)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLS + ["pid", "块", "parse_flag"])
    write_tsv(out, data_dir(taxon, "checklist") / "lit_localities.tsv")
    n_done = len(parts) + len(bad)
    summary("14_lit_merge", [f"{n_done}/{len(todo)} 块已完成 -> {len(out)} 行 lit_localities.tsv",
                             *(bad[:3] or []), f"未完成块 {len(todo) - n_done} 个" if n_done < len(todo) else "全部块已完成"])


if __name__ == "__main__":
    main(sys.argv[1])
