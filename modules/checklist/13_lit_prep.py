"""13 文献抽取准备: papers 的 OCR 页 -> 子代理待办块 lit_inbox/todo_<pid>_<k>.md

输入: config.json "papers" 段, 02_原始数据/checklist/ocr/<pid>/p*.txt (11 步), worms/names.tsv (属名, 可缺)
输出: 02_原始数据/checklist/lit_inbox/todo_<pid>_<k>.md (已有 done_<pid>_<k>.tsv 的块不重建)
选页: ≤40 页的文献全取; 更长的 (文选、集刊、学位论文) 只取含沙蚕科关键词的页及前后各 1 页.
之后由 Claude 派 sonnet 子代理按 modules/checklist/LIT_PROMPT.md 逐块写 done_<pid>_<k>.tsv, 再跑 14.
用法: python3 13_lit_prep.py <Taxon>
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
from common import data_dir, read_tsv, summary  # noqa: E402

MAX_PAGES, MAX_CHARS, SHORT = 12, 30000, 40


def keyword_re(taxon):
    genera = {"Nereis", "Namalycastis", "Lycastis"}
    df = read_tsv(data_dir(taxon, "worms") / "names.tsv", required=False)
    if not df.empty:
        genera |= {g for g in df["genus"] if g} | {n.split()[0] for n in df["scientific_name"] if n}
    alt = "|".join(sorted((re.escape(g) for g in genera if len(g) > 4), key=len, reverse=True))
    return re.compile(rf"沙蚕|沙蠶|沙蠋|Nereid|{alt}", re.I)


def main(taxon):
    d = data_dir(taxon, "checklist")
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8")).get("papers", [])
    inbox = d / "lit_inbox"
    inbox.mkdir(exist_ok=True)
    kw = keyword_re(taxon)
    made = skipped = missing = 0
    for m in cfg:
        od = d / "ocr" / m["pid"]
        lo, _, hi = m["pages"].partition("-")
        pages = list(range(int(lo), int(hi or lo) + 1))
        if m.get("select") == "keywords":            # 11 步只 OCR 了关键词页; 以 11 是否跑完为准
            if not (od / "_done").exists():
                missing += 1
                continue
            pages = sorted(int(f.stem[1:]) for f in od.glob("p*.txt"))
        files = {p: od / f"p{p:04d}.txt" for p in pages}
        if not all(f.exists() for f in files.values()):
            missing += 1
            continue
        text = {p: files[p].read_text(encoding="utf-8") for p in pages}
        if len(pages) > SHORT and m.get("select") != "keywords":
            hit = {p for p in pages if kw.search(text[p]) or kw.search(re.sub(r"\s", "", text[p]))}
            pages = sorted({q for p in hit for q in (p - 1, p, p + 1) if q in text})
        chunks, cur, size = [], [], 0
        for p in pages:
            if cur and (len(cur) >= MAX_PAGES or size + len(text[p]) > MAX_CHARS or p != cur[-1] + 1 and len(cur) >= 4):
                chunks.append(cur)
                cur, size = [], 0
            cur.append(p)
            size += len(text[p])
        if cur:
            chunks.append(cur)
        for k, ch in enumerate(chunks, 1):
            tid = f"{m['pid']}_{k:02d}"
            if (inbox / f"done_{tid}.tsv").exists():
                skipped += 1
                continue
            head = (f"# todo_{tid}\n\npid: {m['pid']}\nPDF: {m['pdf']}\n配置参考文献: {m['citation']}\n"
                    f"PDF 页: {ch[0]}-{ch[-1]} (共 {len(ch)} 页{', 节选含关键词页' if len(text) > SHORT else ''})\n"
                    f"输出: {inbox / f'done_{tid}.tsv'}\n\n")
            body = "".join(f"=== p{p:04d} ===\n{text[p].strip()}\n\n" for p in ch)
            (inbox / f"todo_{tid}.md").write_text(head + body, encoding="utf-8")
            made += 1
    summary("13_lit_prep", [f"待办块 {made} 个 (已完成跳过 {skipped}; OCR 未完成的文献 {missing} 篇) -> {inbox}",
                            "下一步: 派 sonnet 子代理按 modules/checklist/LIT_PROMPT.md 处理 todo_*.md, 再跑 14"])


if __name__ == "__main__":
    main(sys.argv[1])
