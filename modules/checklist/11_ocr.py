"""11 文献 OCR: 扫描版专著/论文逐页 RapidOCR (中文远好于 tesseract chi_sim) -> 每页一个 txt

输入: projects/<Taxon>/02_原始数据/checklist/config.json 的 "monographs" 和 "papers" 段
      [{"pid": "CN01", "pdf": "<PDF 路径>", "citation": "孙瑞平, 杨德渐 2004. 中国动物志...", "pages": "1-521"}]
      条目加 "text": "layer" 表示文字层可靠 (如 Word 生成的论文), 直接 pdftotext, 不 OCR.
      注意: CNKI 老论文的文字层多为乱码, 默认一律 OCR.
      条目加 "select": "keywords" (大部头: 文选/集刊/综合专著) 只 OCR 关键词页±1:
      关键词页由 kb.db 旧 tesseract 文本判定 (中文乱码但拉丁属名可辨), 关键词同 13_lit_prep.keyword_re.
输出: 02_原始数据/checklist/ocr/<pid>/p0001.txt (每行一个文本块, 按阅读顺序)
可断点续跑: 已有 txt 的页跳过. 并行进程数 --procs (默认 4, 每进程 4 线程).
用法: python3 11_mono_ocr.py <Taxon> [--procs 4] [--pid CN01 P01 ...]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
from common import data_dir, summary  # noqa: E402

_ocr = None


def ocr_page(args):
    pdf, page, out, layer = args
    if layer:
        txt = subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), pdf, "-"],
                             capture_output=True, text=True).stdout
        Path(out).write_text(txt, encoding="utf-8")
        return page
    global _ocr
    if _ocr is None:
        os.environ.setdefault("OMP_NUM_THREADS", "4")
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR(intra_op_num_threads=4)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", "300", "-f", str(page), "-l", str(page), "-png", pdf, f"{td}/p"],
                       check=True, capture_output=True)
        png = next(Path(td).glob("p*.png"))
        res, _ = _ocr(str(png))
    lines = []
    for box, text, _score in res or []:
        lines.append((round(box[0][1] / 25), box[0][0], text))   # 行高 ~25px 归并同一行, 再按 x 排
    lines.sort()
    Path(out).write_text("\n".join(t for *_, t in lines), encoding="utf-8")
    return page


def keyword_pages(taxon, pid):
    import importlib.util
    import sqlite3
    sp = importlib.util.spec_from_file_location("prep", HERE / "13_lit_prep.py")
    prep = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(prep)
    kw = prep.keyword_re(taxon)
    con = sqlite3.connect("/mnt/n/沙蚕科-知识库/kb.db")
    pages = {p: t or "" for p, t in con.execute("select page, text from pages where pid=?", (pid,))}
    hit = {p for p, t in pages.items() if kw.search(t)}
    return sorted({q for p in hit for q in (p - 1, p, p + 1) if q in pages})


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("taxon")
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--pid", nargs="+")
    a = ap.parse_args(argv)
    d = data_dir(a.taxon, "checklist")
    conf = json.loads((d / "config.json").read_text(encoding="utf-8"))
    cfg = conf.get("monographs", []) + conf.get("papers", [])
    if not cfg:
        raise SystemExit(f"{d / 'config.json'} 缺 monographs/papers 段 (见本脚本说明)")
    if a.pid:
        cfg = sorted((m for m in cfg if m["pid"] in a.pid), key=lambda m: a.pid.index(m["pid"]))
    done = todo = 0
    for m in cfg:
        lo, _, hi = m["pages"].partition("-")
        od = d / "ocr" / m["pid"]
        od.mkdir(parents=True, exist_ok=True)
        pages = keyword_pages(a.taxon, m["pid"]) if m.get("select") == "keywords" else range(int(lo), int(hi or lo) + 1)
        jobs = [(m["pdf"], p, str(od / f"p{p:04d}.txt"), m.get("text") == "layer") for p in pages
                if not (od / f"p{p:04d}.txt").exists()]
        todo += len(jobs)
        with ProcessPoolExecutor(a.procs) as ex:
            for k, _ in enumerate(ex.map(ocr_page, jobs), 1):
                done += 1
                if k % 20 == 0:
                    print(f"   {m['pid']} {k}/{len(jobs)}", flush=True)
        (od / "_done").write_text("ok", encoding="utf-8")       # 13 步据此判断该文献 OCR 已完成
    summary("11_ocr", [f"OCR {done}/{todo} 页 -> {d / 'ocr'}"])


if __name__ == "__main__":
    main(sys.argv[1:])
