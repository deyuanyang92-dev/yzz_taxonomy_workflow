"""89 记述原文抽取 (供 03 -> treatment.original_text -> 85/88 排版).

只取该种记述的正文, 去掉不属于记述的版面元素 (2026-11-08 用户截图: Liu 2017 Table 3、页眉混入正文):
  文字层 PDF (PyMuPDF dict):
    - 页眉/页脚: 上下 7% 页边内、≤3 行的块
    - 表格、图注、脚注: 块的中位字号 < 正文字号 - 0.8 pt (正文字号 = 全文按字符加权的众数)
    - 以 TABLE / Table n / FIGURE / Fig. n / Plate 开头的块, 单独的 "continued"
    - 双栏: 窄块 (< 55% 页宽) 按 左栏 -> 右栏 排序
  扫描件 (KB 中的 OCR 文本, 无版面信息):
    - 每页首末 2 行中, 去掉数字后在 >=3 页重复的行 (页眉), 和只有页码的行
页码标记: 每页开头单独一行 "[p. <印刷页>]" (无印刷页 -> "[p. PDF n]"), 88 的 PAGE_RE 识别为灰色分隔.
截取: 起于该种标题行 (属名+种加词的短行), 止于下一个他种标题行 (整行只有 "属 种 作者, 年" 或 n. sp., <80 字, 起点 3 行之后;
      异名录条目带 ':' ';' 页码, 不当作标题).
"""
import re
import statistics
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache

import fitz
import regex

CAP = re.compile(r"^\s*(TABLE|Table|FIGURE|Figure|FIG\.|Fig\.|Figs?\.|PLATE|Plate|Tafel|Taf\.)\s*[0-9IVXL]+", re.S)
_AUTH = r"\(?[A-Z][A-Za-zÀ-ÿ'\-]+\.?(\s+(&|and|et|in)\s+[A-Z][A-Za-zÀ-ÿ'\-]+\.?)*,?\s*(\d{4})?\)?\.?"
_NEW = r",?\s*(n\.\s*sp\.?|sp\.\s*n(ov)?\.?|new species|nov\.?\s*sp\.?|n\.\s*comb\.?|sp\.\s*nov\.?)"
# 标题行 = 属 种 + (作者[, 年] 或 n. sp.) 且整行无他物; 属名须在已知属表中 (否则 "The larger" 之类正文会被当成标题)
TITLE_TAIL = re.compile(r"^([A-Z][a-z]+|[A-Z]\.)\s+(\([A-Z][a-z]+\)\s+)?[a-z]{3,}(\s+[a-z]{3,})?\s*(" + _AUTH + r")?\s*(" + _NEW + r")?\s*\.?\s*$")
GENERA = set()


def is_title(x):
    """已知属: 属 种 [作者[, 年]] [n. sp.]; 未知属: 须带作者、年份或 n. sp. (排除 "The larger" 一类正文行)."""
    m = TITLE_TAIL.match(x.strip())
    if not m:
        return False
    if m.group(1) in GENERA:
        return True
    if m.group(1).endswith("."):        # 缩写属名 "N. corallina n." 须带 n./n. sp. 等新种标记或作者
        return bool(m.group(4) or re.search(r"\bn\.|sp\.\s*n|nov\.", x))
    return bool(m.group(4) or re.search(r"\d{4}|n\.\s*sp|sp\.\s*n|nov\.|new species", x))   # 带作者名即可


FAMILY = re.compile(r"^(Family\s+)?[A-Z][a-z]+idae\b.{0,40}$"       # 科名小标题 = 记述终止
                    r"|^Fam(\.|ilie)\s"                                 # Fam. III. ... (Kinberg 1865)
                    r"|^[A-Z]{4,}\s*,?\s*(n\.|nov\.|gen\.)"                # 大写新属 NAUSICAA n., DENDRONEREIS nov. gen.
                    r"|^(\d+\.\s*)?[A-Z]\.\s+[a-z]{3,}\s*,?\s+(n\.|sp\.\s*n|nov\.)")   # N. striata n. — ... / 9. E. mossambica n. sp.
NOISE = re.compile(r"^(This article was )?downloaded (by|from)\b|^Downloaded by|©|Copyright|^Published online|"
                   r"https?://|^\s*doi\s*:", re.I)                   # 水印 / 版权 / 链接行


def _size(b):
    s = [sp["size"] for ln in b["lines"] for sp in ln["spans"] if sp["text"].strip()]
    return statistics.median(s) if s else 0


def _txt(b):
    """块文字; 首行缩进 (比块左缘右移 >= 6 pt, 且不是块首行) 的行前加 \x00 作段首标记."""
    x0 = min(ln["bbox"][0] for ln in b["lines"])
    x1 = max(ln["bbox"][2] for ln in b["lines"])
    out, prev = [], None
    for ln in b["lines"]:
        t = "".join(sp["text"] for sp in ln["spans"]).strip()
        if not t:
            continue
        # 段首 = 新的一行 (不与上一行同高) + 首行缩进 + 上一行未写满
        new_para = (prev is not None and ln["bbox"][1] >= prev["bbox"][3] - 1 and ln["bbox"][0] - x0 >= 6
                    and prev["bbox"][2] < x1 - 15)
        out.append(("\x00" if new_para else "") + t)
        prev = ln
    return "\n".join(out).strip()


@lru_cache(maxsize=8)
def _doc(path):
    return fitz.open(path)


@lru_cache(maxsize=64)
def body_size(path):
    d, c = _doc(path), Counter()
    for p in d.pages(0, min(len(d), 40)):
        for b in p.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for sp in ln["spans"]:
                    c[round(sp["size"], 1)] += len(sp["text"].strip())
    return c.most_common(1)[0][0] if c else 0


def page_lines_pdf(path, pno):
    """文字层页 -> 正文行 (去页眉页脚/表格/图注). pno 1 起."""
    d = _doc(path)
    p = d[pno - 1]
    W, H, bs = p.rect.width, p.rect.height, body_size(path)
    keep = []
    for b in p.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        t = _txt(b)
        if not t:
            continue
        x0, y0, x1, y1 = b["bbox"]
        if (y1 < 0.08 * H or y0 > 0.90 * H) and len(b["lines"]) <= 3:
            continue
        if bs and _size(b) < bs - 0.8:
            continue
        if CAP.match(t) or t.lower().strip(" .") == "continued":
            continue
        col = 0 if (x1 - x0) > 0.55 * W else (1 if x0 > 0.45 * W else 0)
        keep.append((col if (x1 - x0) <= 0.55 * W else -1, y0, t))
    # 通栏块按 y; 窄块按栏再按 y (通栏块与左栏一起按 y 排)
    keep.sort(key=lambda k: (max(k[0], 0), k[1]))
    out = []
    for _, _, t in keep:            # 块之间空一行 = 段落分隔 (88 reflow 遇空行断段); 块内首行缩进 (\x00 标记) 也断段
        ls = [ln for ln in t.splitlines() if ln.strip() and not NOISE.search(ln)]
        if ls and out and out[-1] and not re.search(r"[.:!?)\]]\s*$", out[-1]):
            pass                    # 上一块没以句末标点结束 -> 同一段 (每行一个块的 PDF, 如 Willey 1905)
        elif ls and out and out[-1]:
            out.append("")
        for ln in ls:
            if ln.startswith("\x00"):
                out.append("")
                ln = ln[1:]
            out.append(ln)
    return out


def is_scan(page):
    """整页是一张图 (扫描件; 文字层若有也是隐藏 OCR, 字号/分块不可靠)."""
    area = page.rect.width * page.rect.height
    return any((i["bbox"][2] - i["bbox"][0]) * (i["bbox"][3] - i["bbox"][1]) > 0.6 * area for i in page.get_image_info())


def visual_lines(page):
    """扫描件隐藏 OCR 文字层 -> 按词坐标重建的真实行 (同一行的词常被拆成多个 line)."""
    words = []                         # 只取水平行的 span (竖排的 "Downloaded by ..." 水印丢弃)
    for bl in page.get_text("dict")["blocks"]:
        for ln in bl.get("lines", []):
            if abs(ln["dir"][0] - 1) > 0.05:
                continue
            for sp in ln["spans"]:
                if sp["text"].strip():
                    x0, y0, x1, y1 = sp["bbox"]
                    words.append((x0, y0, x1, y1, sp["text"].strip()))
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows = []
    for w in words:
        yc, h = (w[1] + w[3]) / 2, w[3] - w[1]
        if rows and abs(rows[-1][0] - yc) <= max(3.0, 0.6 * h):
            rows[-1][1].append(w)
        else:
            rows.append([yc, [w]])
    return [" ".join(x[4] for x in sorted(r[1], key=lambda w: w[0])) for r in rows]


def page_lines_ocr(pages):
    """[(pno, text)] 扫描件 OCR -> {pno: 正文行}; 去重复页眉和纯页码行."""
    norm = (lambda s: re.sub(r"[\d\W_]+", "", s.lower()))
    edge = Counter()
    split = {p: [x.strip() for x in (t or "").splitlines() if x.strip()] for p, t in pages}
    for ls in split.values():
        for x in set(ls[:2] + ls[-2:]):
            if len(x) < 90 and norm(x):
                edge[norm(x)] += 1
    out = {}
    for p, ls in split.items():
        keep = []
        for i, x in enumerate(ls):
            if re.fullmatch(r"[\W\d_]{0,6}\d{1,4}[\W\d_]{0,6}", x):
                continue
            if (i < 2 or i >= len(ls) - 2) and len(x) < 90 and edge.get(norm(x), 0) >= 3:
                continue
            if NOISE.search(x):
                continue
            keep.append(x)
        out[p] = keep
    return out


def _norm(s):
    return re.sub(r"[\d\W_]+", "", s.lower())


def running_heads(texts):
    """整篇各页文字 -> 页眉/页脚候选 Counter{规范化行: 出现页数} (各页首末 3 行, 去数字)."""
    c = Counter()
    for t in texts:
        ls = [x.strip() for x in (t or "").splitlines() if x.strip()]
        for x in set(ls[:3] + ls[-3:]):
            if len(x) < 100 and len(_norm(x)) >= 4:
                c[_norm(x)] += 1
    return c


def is_head(x, heads):
    """该行与整篇 >=3 页的首末行近似相同 (OCR 拼写变体按相似度 >= 0.8 合并计数)."""
    n = _norm(x)
    if not heads or len(x) >= 100 or len(n) < 4:
        return False
    if heads.get(n, 0) >= 3:
        return True
    return sum(k for h, k in heads.items() if abs(len(h) - len(n)) <= 4 and SequenceMatcher(None, h, n).ratio() >= 0.8) >= 3


def account(path, a, b, epithet, offset, kb, heads=None):
    """path: PDF; a..b PDF 页 (1 起); kb: {pno: (text, source)}; offset: 印刷页 - PDF 页 或 None.
    -> (原文, 说明)."""
    ocr_pages = [(p, kb[p][0]) for p in range(a, b + 1) if p in kb and kb[p][1] != "pdf"]
    ocr = page_lines_ocr(ocr_pages) if ocr_pages else {}
    lines, srcs = [], set()
    for p in range(a, b + 1):
        lines.append(f"[p. {p + offset}]" if offset is not None else f"[p. PDF {p}]")
        if p in ocr:
            lines += ocr[p]
            srcs.add("OCR")
        elif is_scan(_doc(path)[p - 1]):           # 扫描件 + 隐藏 OCR 文字层
            vl = page_lines_ocr([(p, "\n".join(visual_lines(_doc(path)[p - 1])))])[p]
            lines += vl
            srcs.add("scan text layer")
        else:
            try:
                lines += page_lines_pdf(path, p)
                srcs.add("text layer")
            except Exception:
                lines += [x for x in (kb.get(p, ("", ""))[0] or "").splitlines() if x.strip()]
                srcs.add("KB")
    out, pnum, k = [], None, 0
    for x in lines:                    # 页首/页末 3 行中与整篇重复的页眉页脚
        k = 0 if x.startswith("[p. ") else k + (1 if x else 0)
        if x and k <= 3 and is_head(x, heads):
            continue
        out.append(x)
    lines = [x for i, x in enumerate(out) if not (x and is_head(x, heads) and i + 1 < len(out) and (out[i + 1].startswith("[p. ") or not out[i + 1]) and i + 2 < len(out) and out[i + 2].startswith("[p. "))]
    out, pnum = [], None
    for x in lines:                    # 带本页印刷页码的短行 = 页眉 (OCR 拼写多变, 重复检测漏掉的); 图版页 OCR 碎字
        if x.startswith("[p. "):
            pnum = x[4:-1].strip()
            out.append(x)
            continue
        if pnum and pnum.isdigit() and len(x) < 80 and re.search(rf"(^|\D){pnum}\W*$|^\W*{pnum}\D", x):
            continue
        if x and len(re.findall(r"[A-Za-z]", x)) < 3 and not re.search(r"\d+\s*[+:–-]\s*\d+", x):
            continue
        out.append(x)
    lines = out
    ep = epithet.lower()
    pe = regex.compile(rf"(?:{re.escape(ep)}){{e<=1}}" if len(ep) >= 6 else rf"\b{re.escape(ep)}\b")
    hit = [i for i, x in enumerate(lines) if not x.startswith("[p. ") and pe.search(x.lower())]
    if not hit:
        return "\n".join(lines), "+".join(sorted(srcs)) + "; epithet not found in text, all pages kept"
    head = [i for i in hit if len(lines[i]) < 120 and is_title(lines[i])] or \
           [i for i in hit if re.match(r"^([A-Z][a-z]+|[A-Z]\.)\s+" + re.escape(ep[:5]) + r"\w*,?\s+(n\.|sp\.\s*n|nov\.)", lines[i], re.I)] or \
           [i for i in hit if len(lines[i]) < 80]
    s = head[0] if head else hit[0]
    while s > 0 and lines[s - 1].startswith("[p. "):     # 带上本页页码标记
        s -= 1
    if not lines[s].startswith("[p. "):                   # 起点前最近的页码标记
        mk = [x for x in lines[:s] if x.startswith("[p. ")]
        if mk:
            lines = lines[:s] + [mk[-1]] + lines[s:]
    e = len(lines)
    for i in range(s + 4, len(lines)):
        x = lines[i].strip()
        if not pe.search(x.lower()) and ((len(x) < 80 and is_title(x) and not re.search(r"[:;]", x)) or FAMILY.match(x)):
            e = i
            break
    while e > s and lines[e - 1].startswith("[p. "):
        e -= 1
    seg = lines[s:e]
    # 空页码标记 (该页只有图/表) 去掉; 连续空行合并
    nxt = (lambda k: next((y for y in seg[k + 1:] if y), None))   # 下一个非空行
    seg = [x for k, x in enumerate(seg) if not (x.startswith("[p. ") and (nxt(k) is None or nxt(k).startswith("[p. ")))]
    seg = [x for k, x in enumerate(seg) if x or (k and seg[k - 1])]
    txt = "\n".join(seg).strip()
    note = "+".join(sorted(srcs)) + "; from " + ("species heading" if head else "first mention") + ("; to next heading" if e < len(lines) else "; to last page")
    if len(re.sub(r"\[p\.[^\]]*\]", "", txt)) < 150:
        return "\n".join(x for x in lines[s:] if x is not None), note + "; cut too short, kept to end of last page"
    return txt, note
