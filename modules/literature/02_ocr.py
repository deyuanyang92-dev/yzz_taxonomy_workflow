"""02 OCR: 对 01 标记为 pending 的页 (无文字层扫描页) 做 tesseract OCR. 设计为后台长时间运行.

  python3 02_ocr.py <corpus> [--workers N] [--dpi 300] [--limit-docs N]

  1) 每篇文献定语言 (detect_lang): 取 2 页正文先用 eng 识别, 置信度 >= LATIN_CONF -> 拉丁字母,
     停用词判 fr/de/es/it/pt/la/sv/da/nl/no; 否则 rus/jpn/chi_tra 逐一试识别, 按 置信度 x 该文字占比 取最高.
     不用 OSD 判文字: 图版/空白/横排页上 OSD 乱报 Cyrillic (置信度 <5), 对汉字也不可靠 (QC 2026-10-15).
     结果存 docs.ocr_lang (总带 eng, 学名是拉丁字母).
  逐页: 置信度 < 70 时用 OSD 测方向, 需旋转且方向置信度 >= 5 则旋转重识别, 择优.
  2) 按 ≤CHUNK 页分块并行 OCR, 每块完成即写库 -> 中断后重跑只做剩下的 pending 页.
  每页存 tesseract 平均置信度 ocr_conf, 供后续质量筛查.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

CHUNK = 10
MAX_SIDE = 6000  # 折页大图限制像素, 防内存爆
BACKUP_EVERY = 1800  # 秒

STOP = {
    "fra": "le la les des du et est une dans pour sur avec par que qui sont pas ce cette au aux".split(),
    "deu": "der die das und ist nicht mit von den dem des ein eine sich auf zu im bei wie sind auch".split(),
    "spa": "el la los las del y en que con por una para es se como más sus al".split(),
    "ita": "il lo la gli le di del della e che con per una sono nel alla dei da".split(),
    "por": "o os da do das dos e em que com por uma para não se ao na no".split(),
    "lat": "et in est ad cum non sunt vel aut sed ex quae qui setis segmento segmentis".split(),
    "swe": "och att det som en på är av för med till den har de inte om ett".split(),
    "dan": "og at det som en på er af for med til den har de ikke om et".split(),
    "nld": "de het een en van in is op te dat met voor zijn niet aan bij".split(),
    "nor": "og at det som en på er av for med til den har de ikke om et".split(),
    "eng": "the and of to in is with are on for from by as at this that".split(),
}
NONLATIN = {"rus+eng": r"[\u0400-\u04FF]", "jpn+eng": r"[\u3040-\u30FF\u4E00-\u9FFF]",
            "chi_tra+chi_sim+eng": r"[\u4E00-\u9FFF]"}
LATIN_CONF = 75
ENV = {**os.environ, "OMP_THREAD_LIMIT": "1"}


def render(doc, page_no, dpi):
    pg = doc[page_no - 1]
    z = dpi / 72
    side = max(pg.rect.width, pg.rect.height) * z
    if side > MAX_SIDE:
        z *= MAX_SIDE / side
    import fitz
    return pg.get_pixmap(matrix=fitz.Matrix(z, z), colorspace=fitz.csGRAY).tobytes("png")


def tess(png, lang, psm=3):
    """返回 (文本, 平均置信度). 用 TSV 输出以同时拿置信度, 按 block/par/line 重组文本."""
    r = subprocess.run(["tesseract", "stdin", "stdout", "-l", lang, "--psm", str(psm), "tsv"],
                       input=png, capture_output=True, env=ENV, timeout=600)
    confs, key_prev, par_prev = [], None, None
    out = []
    for row in r.stdout.decode("utf-8", "replace").splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        key = (f[2], f[3], f[4])  # block, par, line
        if key != key_prev:
            if (f[2], f[3]) != par_prev and out:
                out.append("")
            out.append(f[11])
            key_prev, par_prev = key, (f[2], f[3])
        else:
            out[-1] += " " + f[11]
        c = float(f[10])
        if c >= 0:
            confs.append(c)
    return "\n".join(out).strip(), (round(sum(confs) / len(confs), 1) if confs else None)


def _run(arr):
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "PNG")
    return b.getvalue()


def trim(png):
    """裁掉与纸张底色不同的边带 (扫描白边/黑边). 两侧同时有异常边带时 tesseract 整页返回空 (Ehlers 1897 实测)."""
    import io
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(io.BytesIO(png)).convert("L"))
    h, w = a.shape
    paper = np.median(a[h // 4: 3 * h // 4, w // 4: 3 * w // 4])

    def span(med):
        good = np.abs(med - paper) < 20
        best, cur, start = (0, len(med)), 0, 0
        blen = 0
        for i, g in enumerate(good):
            if g:
                if cur == 0:
                    start = i
                cur += 1
                if cur > blen:
                    blen, best = cur, (start, i + 1)
            else:
                cur = 0
        return best

    x0, x1 = span(np.median(a, axis=0))
    y0, y1 = span(np.median(a, axis=1))
    return _run(np.ascontiguousarray(a[y0:y1, x0:x1])), (x1 - x0) * (y1 - y0) / (w * h)


def rotate_if_needed(png):
    """OSD 测方向; 需旋转且方向置信度 >= 5 则返回旋转后的 png, 否则 None. (Hartman 1951 横排页实测)"""
    import io
    from PIL import Image
    r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "0"], input=png, capture_output=True, env=ENV,
                       timeout=120).stdout.decode("utf-8", "replace")
    m, c = re.search(r"Rotate: (\d+)", r), re.search(r"Orientation confidence: ([\d.]+)", r)
    if not (m and c) or m.group(1) == "0" or float(c.group(1)) < 5:
        return None
    b = io.BytesIO()
    Image.open(io.BytesIO(png)).rotate(-int(m.group(1)), expand=True).save(b, "PNG")
    return b.getvalue()


def ocr_page(png, lang):
    """整页识别; 低置信度测方向旋转重试; 几乎无字时裁边重试. 择优. 中/日文去掉字间空格 (litdb.cjk_join)."""
    text, conf = _ocr_page(png, lang)
    return (litdb.cjk_join(text) if re.search(r"chi|jpn", lang) else text), conf


def _ocr_page(png, lang):
    text, conf = tess(png, lang)
    if conf is not None and conf < 70 and len(text) > 50:
        rot = rotate_if_needed(png)
        if rot:
            t2, c2 = tess(rot, lang)
            if c2 and c2 > conf + 5:
                text, conf = t2, c2
    if len(text) < 50:
        cropped, frac = trim(png)
        if 0.3 < frac < 0.995:
            t2, c2 = tess(cropped, lang)
            if len(t2) > len(text):
                return t2, c2
    return text, conf


def latin_lang(text):
    """拉丁字母文本: 停用词判欧洲语种. 外语停用词明显 (≥ 英文的一半且 ≥5 次) 才加; 否则纯英文."""
    words = re.findall(r"[a-zà-ÿ]+", text.lower())
    score = {k: sum(words.count(w) for w in v) for k, v in STOP.items()}
    best = max((k for k in score if k != "eng"), key=score.get)
    if score[best] >= 5 and score[best] >= score["eng"] * 0.5:
        return f"eng+{best}"
    return "eng"


def lang_from_text(text):
    """已有可靠文字层 (同篇的 pdf 页) 时直接据此判语言."""
    chars = max(len(re.sub(r"\s", "", text)), 1)
    for lang, pat in NONLATIN.items():
        if len(re.findall(pat, text)) / chars > 0.3:
            return lang
    return latin_lang(text)


def detect_lang(path, page_nos, dpi, layer_text=""):
    """子进程: 同篇有可靠文字层则据此判; 否则取 2 页 (中段, 避开封面) OCR 判. 见模块说明."""
    if len(layer_text) > 3000:
        return lang_from_text(layer_text)
    import fitz
    try:
        with fitz.open(path) as d:
            picks = sorted({page_nos[len(page_nos) // 3], page_nos[(2 * len(page_nos)) // 3]})
            pngs = [render(d, pn, 200) for pn in picks]
        eng = [ocr_page(p, "eng") for p in pngs]
        eng = [(t, c) for t, c in eng if c is not None and len(t) > 200] or eng
        confs = [c for _, c in eng if c is not None]
        if confs and sum(confs) / len(confs) >= LATIN_CONF:
            return latin_lang(" ".join(t for t, _ in eng))
        best, best_s = "eng", (sum(confs) / len(confs) if confs else 0) * 0.5
        for lang, pat in NONLATIN.items():
            t, c = tess(pngs[0], lang)
            frac = len(re.findall(pat, t)) / max(len(re.sub(r"\s", "", t)), 1)
            if c and frac > 0.3 and c * frac > best_s:
                best, best_s = lang, c * frac
        return best if best != "eng" else latin_lang(" ".join(t for t, _ in eng))
    except Exception:
        return "eng"


def ocr_chunk(path, page_nos, lang, dpi):
    import fitz
    res = []
    with fitz.open(path) as d:
        for pn in page_nos:
            try:
                text, conf = ocr_page(render(d, pn, dpi), lang)
                res.append((pn, text, conf, ""))
            except Exception as e:
                res.append((pn, "", None, f"{type(e).__name__}: {e}"[:200]))
    return res


def layer_text(con, doc_id, n=6):
    """同篇质量好的原文字层页 (最多 n 页) 文本, 供判语言."""
    rows = con.execute("SELECT text FROM pages WHERE doc_id=? AND source='pdf' AND quality>=0.8 AND chars>800"
                       " ORDER BY page_no LIMIT ?", (doc_id, n)).fetchall()
    return "\n".join(r[0] for r in rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--limit-docs", type=int, default=0, help="只做前 N 篇 (测试用)")
    a = ap.parse_args()
    src = Path(litdb.corpus_cfg(a.corpus)["source"])
    con = litdb.connect(a.corpus)
    if "ocr_lang" not in [r[1] for r in con.execute("PRAGMA table_info(docs)")]:
        con.execute("ALTER TABLE docs ADD COLUMN ocr_lang TEXT")

    pend = {}
    for doc_id, pn in con.execute("SELECT doc_id, page_no FROM pages WHERE source='pending' ORDER BY doc_id, page_no"):
        pend.setdefault(doc_id, []).append(pn)
    docs = {r[0]: (src / r[1], r[2]) for r in con.execute("SELECT doc_id, relpath, ocr_lang FROM docs")}
    ids = list(pend)[: a.limit_docs or None]
    total = sum(len(pend[i]) for i in ids)
    print(f"待 OCR: {len(ids)} 篇 {total} 页, {a.workers} 进程", flush=True)

    t0 = last_bak = time.time()
    done = failed = 0
    with ProcessPoolExecutor(a.workers) as ex:
        need = [i for i in ids if not docs[i][1]]
        for i, f in [(i, ex.submit(detect_lang, docs[i][0], pend[i], a.dpi, layer_text(con, i))) for i in need]:
            lang = f.result()
            con.execute("UPDATE docs SET ocr_lang=? WHERE doc_id=?", (lang, i))
            docs[i] = (docs[i][0], lang)
        con.commit()
        print(f"  语言判定完成 {len(need)} 篇, {time.time() - t0:.0f}s", flush=True)

        futs = {}
        for i in ids:
            for k in range(0, len(pend[i]), CHUNK):
                futs[ex.submit(ocr_chunk, docs[i][0], pend[i][k:k + CHUNK], docs[i][1], a.dpi)] = i
        for f in as_completed(futs):
            i = futs[f]
            try:
                rows = f.result()
            except Exception as e:
                print(f"  ! doc {i}: {e}", flush=True)
                continue
            for pn, text, conf, err in rows:
                if err:
                    failed += 1
                    continue
                con.execute("UPDATE pages SET source='ocr', text=?, chars=?, quality=?, ocr_conf=?, ocr_lang=?"
                            " WHERE doc_id=? AND page_no=?",
                            (text, len(text), litdb.quality(text), conf, docs[i][1], i, pn))
            con.commit()
            done += len(rows)
            el = time.time() - t0
            if done % 200 < CHUNK:
                eta = el / max(done, 1) * (total - done) / 3600
                print(f"  {done}/{total} 页  {el / 3600:.1f}h  预计剩 {eta:.1f}h", flush=True)
            if time.time() - last_bak > BACKUP_EVERY:
                litdb.backup(a.corpus)
                last_bak = time.time()

    left = con.execute("SELECT count(*) FROM pages WHERE source='pending'").fetchone()[0]
    con.close()
    dst = litdb.backup(a.corpus)
    summary("02_ocr", [f"OCR {done - failed} 页, 失败 {failed} 页, 用时 {(time.time() - t0) / 3600:.1f}h",
                       f"库内仍待 OCR {left} 页 (失败页可重跑本步)", f"备份 -> {dst}"])


if __name__ == "__main__":
    main()
