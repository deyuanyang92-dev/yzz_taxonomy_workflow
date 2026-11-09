"""kbshow: 从 <Genus>_KB.sqlite 取 PDF 页文字 (子代理核对记述页用).
  python3 kbshow.py <项目目录> <文件名片段> <起页> [止页]               整页全文
  python3 kbshow.py <项目目录> <文件名片段> <起页> <止页> --scan <种加词>  紧凑扫描: 每页页眉 2 行 + 疑似分类标题行 + 种加词前后 2 行
页号 = PDF 页 (1 起).
"""
import re
import sqlite3
import sys
from pathlib import Path

import regex

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg  # noqa: E402
DB = cfg.KB
HEAD = re.compile(r"^[A-Z][a-z]+\s+(\([A-Z][a-z]+\)\s+)?[a-z]{3,}(\s+[a-z]{3,})?\s*,?\s*(\(?[A-Z][A-Za-zé\-ü&. ]+,?\s*\d{4}\)?|n\.\s*sp|sp\.\s*n|new species|nov)")


def main(a):
    scan = "--scan" in a
    ep = a[a.index("--scan") + 1].lower() if scan else ""
    a = [x for x in a if x != "--scan" and x.lower() != ep]
    frag, p1 = a[0], int(a[1])
    p2 = int(a[2]) if len(a) > 2 else p1
    con = sqlite3.connect(DB)
    fs = [f for (f,) in con.execute("select file from files") if frag.lower() in f.lower()]
    if len(fs) != 1:
        sys.exit(f"文件匹配 {len(fs)} 个: {fs[:5]}")
    f = fs[0]
    pe = regex.compile(rf"(?:{re.escape(ep)}){{e<=1}}" if len(ep) >= 6 else re.escape(ep)) if ep else None
    print(f"## {f}")
    for p, t in con.execute("select page_no, text from pages where file=? and page_no between ? and ? order by page_no", (f, p1, p2)):
        print(f"\n===== PDF p{p} =====")
        if not scan:
            print(t)
            continue
        ls = [x.rstrip() for x in (t or "").splitlines() if x.strip()]
        keep = set(range(min(2, len(ls))))
        for i, x in enumerate(ls):
            if HEAD.match(x.strip()):
                keep.add(i)
            if pe and pe.search(x.lower()):
                keep.update(range(max(0, i - 2), min(len(ls), i + 3)))
        last = -2
        for i in sorted(keep):
            if i != last + 1:
                print("  ...")
            print(f"  {ls[i][:160]}")
            last = i


if __name__ == "__main__":
    main(cfg.ARGS)
