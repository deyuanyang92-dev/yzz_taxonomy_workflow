"""16 复核准备: 报表中标黄 (需核对) 且尚未复核的行 -> review/todo_<k>.tsv (附 PDF 与页码), 供子代理看原页图复核

输入: 02_原始数据/checklist/localities_worms.tsv (15), config.json, lit_inbox/todo_*.md (定位 PDF 页)
输出: 02_原始数据/checklist/review/todo_<k>.tsv (每块 ≤25 行); 子代理按 modules/checklist/REVIEW_PROMPT.md 写 done_<k>.tsv
      之后重跑 15: 读取 review/done_*.tsv, 应用修改/删除, 已核行不再标黄.
用法: python3 16_review_prep.py <Taxon> [--pid CN01 | --pid ALL]
      --pid: 该文献的全部采集地行 (研究标本/模式产地) 都复核, 不限标黄 (规则解析的 CN01 有未被标黄的 OCR 残字/图注, 2026-10-11 用户发现)
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
from common import data_dir, read_tsv, summary, write_tsv  # noqa: E402

SIZE = 25
COLS = ["rid", "物种名（中文）", "物种名（学名）", "采集地", "采集地类型", "页码", "note", "parse_flag", "check_note",
        "valid_name", "pid", "PDF", "PDF页"]


def norm(s):
    return re.sub(r"[^一-鿿A-Za-z0-9]", "", s or "")


def pdf_pages(r, d, cache):
    """估计该行所在 PDF 页: 专著用 OCR 页文本检索采集地/学名片段; 文献块同理, 找不到给块的页范围."""
    pid = r["pid"]
    if pid not in cache:
        cache[pid] = {int(f.stem[1:]): norm(f.read_text(encoding="utf-8")) for f in (d / "ocr" / pid).glob("p*.txt")}
    pages = cache[pid]
    probes = [norm(r["采集地"])[:8], norm(r["物种名（学名）"])[:12], norm(r.get("原文摘录", ""))[:8]]
    for pr in probes:
        if len(pr) >= 4:
            hit = sorted(p for p, t in pages.items() if pr in t)
            if 0 < len(hit) <= 3:
                return ",".join(map(str, hit))
    blk = r.get("块", "")
    if blk:
        f = d / "lit_inbox" / f"todo_{blk}.md"
        m = re.search(r"PDF 页: (\d+-\d+)", f.read_text(encoding="utf-8")) if f.exists() else None
        if m:
            return m.group(1)
    pg = re.match(r"\d+", r["页码"] or "")
    return pg.group(0) if pg else ""


def main(taxon, pid=None):
    d = data_dir(taxon, "checklist")
    df = read_tsv(d / "localities_worms.tsv")
    conf = json.loads((d / "config.json").read_text(encoding="utf-8"))
    pdf = {m["pid"]: m["pdf"] for m in conf.get("monographs", []) + conf.get("papers", [])}
    rv = d / "review"
    rv.mkdir(exist_ok=True)
    done = set()
    for f in rv.glob("done_*.tsv"):
        done |= set(read_tsv(f)["rid"])
    other = df["family"].ne("") & df["family"].ne(taxon)
    loc_rows = df["采集地类型"].isin(["研究标本", "模式产地"])
    if pid == "ALL":                       # 全表复核 (用户 2026-10-12: "再 check 一遍, 确保没有错误")
        sel = loc_rows
    elif pid:
        sel = (df["pid"] == pid) & loc_rows
    else:
        sel = df["需核对"] == "Y"
    todo = df[sel & ~other & ~df["rid"].isin(done)].copy()
    cache = {}
    todo["PDF"] = todo["pid"].map(pdf)
    todo["PDF页"] = [pdf_pages(r, d, cache) for _, r in todo.iterrows()]
    old = sorted(rv.glob("todo_*.tsv"))
    for f in old:
        if not (rv / f.name.replace("todo_", "done_")).exists():
            f.unlink()
    start = len(list(rv.glob("done_*.tsv"))) + 1
    n = 0
    for i in range(0, len(todo), SIZE):
        write_tsv(todo[COLS].iloc[i:i + SIZE], rv / f"todo_{start + n:02d}.tsv")
        n += 1
    summary("16_review_prep", [f"待复核 {len(todo)} 行 -> {n} 块 {rv}/todo_*.tsv (已复核 {len(done)} 行)",
                               "下一步: 派 sonnet 子代理按 modules/checklist/REVIEW_PROMPT.md 写 done_*.tsv, 再重跑 15"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[sys.argv.index("--pid") + 1] if "--pid" in sys.argv else None)
