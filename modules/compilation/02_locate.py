"""02 记述页定位: 物种×文献 (已获取) 每行 -> 该种在 PDF 中的候选起止页 (供子代理确认).
依据: (1) WoRMS 印刷页码 + 每个 PDF 的 "印刷页 - PDF 页" 偏移 (页眉/页脚数字众数); (2) 种加词出现页 (容 1 个 OCR 错字);
(3) 标题行特征 (属名+种加词在短行, 或带 n. sp./sp. nov.).
输出 08_知识库/结构化/treatment_candidates.tsv
用法: python3 yzz.py compilation 02 <项目目录>
之后: 按 CONFIRM_PROMPT.md 派 sonnet 子代理核对 (结构化/confirm/in_K.tsv -> out_K.tsv)
"""
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import regex

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg  # noqa: E402  项目根目录与配置
ROOT, DB, TAB = cfg.ROOT, cfg.KB, cfg.TAB
OUT = cfg.S / "treatment_candidates.tsv"
NUM = re.compile(r"^\W*(\d{1,4})\b|\b(\d{1,4})\W*$")   # 页眉/页脚行首或行尾的数字


def page_offset(pages):
    """pages: {page_no: text} -> d (印刷页 = pdf页 + d) 或 None."""
    c = Counter()
    for p, t in pages.items():
        lines = [x.strip() for x in t.splitlines() if x.strip()]
        for ln in lines[:3] + lines[-3:]:
            if len(ln) < 100:
                for m in NUM.finditer(ln):
                    c[int(m.group(1) or m.group(2)) - p] += 1
    if not c:
        return None, 0
    d, n = c.most_common(1)[0]
    return (d, n) if n >= max(3, 0.15 * len(pages)) else (None, n)


def worms_range(s):
    m = re.search(r"(\d{1,4})\s*(?:[-–]\s*(\d{1,4}))?", str(s or ""))
    if not m:
        return None, None
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    if b < a and len(m.group(2)) < len(m.group(1)):        # 266-8
        b = int(m.group(1)[: -len(m.group(2))] + m.group(2))
    return a, (b if b >= a and b - a < 80 else a)


def pat(word):
    w = re.escape(word.lower())
    return regex.compile(rf"(?:\b{w}\b){{e<=1}}" if len(word) >= 6 else rf"\b{w}\b")


def main():
    con = sqlite3.connect(DB)
    texts = defaultdict(dict)
    for f, p, t in con.execute("select file, page_no, text from pages"):
        texts[f][p] = t or ""
    offs = {f: page_offset(pg) for f, pg in texts.items()}
    d = pd.read_excel(TAB, "物种×文献").fillna("")
    d = d[d["获取"].str.startswith("已获取") & (d.get("via", "") != "supplement")].copy()   # 补充文献由 supplement_accounts.tsv 直接给页码
    rows = []
    for i, r in d.iterrows():
        fn = Path(r["文件"]).name
        pg = texts.get(fn)
        if not pg:
            rows.append({"row": i, "file": fn, "method": "无全文"})
            continue
        words = str(r["scientific_name"]).split()
        ep, gen = words[-1], words[0]
        pe, pgn = pat(ep), pat(gen)
        hits, heads = {}, set()
        for p, t in pg.items():
            low = t.lower()
            n = len(pe.findall(low))
            if n:
                hits[p] = n
                for ln in low.splitlines():
                    if pe.search(ln) and (len(ln.strip()) < 90 and pgn.search(ln) or re.search(r"n\.\s*sp|sp\.\s*n|nov\.", ln)):
                        heads.add(p)
                        break
        off, sup = offs[fn]
        a, b = worms_range(r["page"])
        method, s, e = "", None, None
        if a and off is not None and (a - off) in pg:
            s, e = a - off, b - off
            near = [p for p in hits if s - 1 <= p <= e + 1]
            method = "WoRMS页码+偏移" + ("" if near else " (该页无种名!)")
        elif a and min(pg) <= a <= max(pg) and a in hits and len(pg) > a:   # 整本书 PDF 无偏移
            s, e, method = a, b, "WoRMS页码=PDF页"
        elif heads:
            s = min(heads)
            method = "标题行"
        elif hits:
            s = max(hits, key=hits.get)
            method = "种名最多页"
        else:
            method = "未见种名"
        if s and (e is None or e == s):                        # 向后延伸: 连续出现种名的页 (容 1 页空档), 最多 +8
            e, q = s, s + 1
            while q <= s + 8 and (q in hits or (q + 1) in hits and q + 1 <= s + 8):
                if q in hits:
                    e = q
                q += 1
        rows.append({"row": i, "valid_taxon": r["valid_taxon"], "scientific_name": r["scientific_name"], "level": r["level"],
                     "use": r["use"], "worms_page": r["page"], "note": r["note"], "authors": r["authors"], "year": r["year"],
                     "ref_no": r["ref_no"], "source_id": r["source_id"], "aphia_id": r["aphia_id"], "file": fn,
                     "n_pdf_pages": len(pg), "offset": off, "pdf_start": s, "pdf_end": e, "method": method,
                     "hit_pages": ",".join(map(str, sorted(hits)))[:300], "head_pages": ",".join(map(str, sorted(heads)))})
    o = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_csv(OUT, sep="\t", index=False)
    print(o.method.value_counts().to_string())
    print(f"[02] {len(o)} rows -> {OUT}")


if __name__ == "__main__":
    main()
