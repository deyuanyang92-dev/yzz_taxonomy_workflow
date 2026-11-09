"""17 采集地/note 重分准备: 把所有采集地行 (含 note) 交子代理按内容重新划分采集地与 note

用户 2026-10-12: "采集地取第一个是你为了优化的规矩…遇到特殊就你自己模型判断" -> 按内容判断, 不按句号切.
输入: 02_原始数据/checklist/localities_worms.tsv (15, 已应用复核)
输出: 02_原始数据/checklist/resplit/todo_<k>.tsv (rid, 学名, 中文, 采集地类型, 采集地, note; 每块 40 行)
      子代理按 modules/checklist/RESPLIT_PROMPT.md 写 done_<k>.tsv (rid, 采集地, note, 依据); 15 应用并校验.
用法: python3 17_resplit_prep.py <Taxon>
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
from common import data_dir, read_tsv, summary, write_tsv  # noqa: E402

SIZE = 40


def main(taxon):
    d = data_dir(taxon, "checklist")
    df = read_tsv(d / "localities_worms.tsv")
    rv = d / "resplit"
    rv.mkdir(exist_ok=True)
    for f in rv.glob("todo_*.tsv"):
        f.unlink()
    other = df["family"].ne("") & df["family"].ne(taxon)
    sel = df[df["采集地类型"].isin(["研究标本", "模式产地"]) & ~other & (df["note"] != "")]
    cols = ["rid", "物种名（学名）", "物种名（中文）", "采集地类型", "采集地", "note"]
    n = 0
    for i in range(0, len(sel), SIZE):
        n += 1
        write_tsv(sel[cols].iloc[i:i + SIZE], rv / f"todo_{n:02d}.tsv")
    summary("17_resplit_prep", [f"{len(sel)} 行 -> {n} 块 {rv}/todo_*.tsv",
                                "下一步: 派 sonnet 子代理按 modules/checklist/RESPLIT_PROMPT.md 写 done_*.tsv, 再重跑 15"])


if __name__ == "__main__":
    main(sys.argv[1])
