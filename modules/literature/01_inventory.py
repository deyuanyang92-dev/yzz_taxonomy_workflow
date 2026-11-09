"""01 文献清点 + 文字层抽取: 遍历文献目录 (只读), 每个 PDF 逐页取文字层.

  python3 01_inventory.py <corpus> [--workers N]

  有文字层 (>= MIN_TEXT_CHARS 字符) 的页 -> pages.source='pdf', 存文本
  无文字层的页 -> pages.source='pending', 留给 02_ocr
  docx -> 整篇一页, source='docx'
  可重跑: relpath + size + mtime 未变的文件跳过.
"""
import argparse
import json
import unicodedata
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

EXTS = {".pdf": "pdf", ".docx": "docx"}


def extract(path):
    """子进程: 返回 (doc 信息, [(page_no, source, chars, quality, text)])."""
    kind = EXTS.get(path.suffix.lower(), "pdf")  # 知网 .caj/.kdh/.nh 中文件头为 %PDF 的按 PDF (16_refresh 筛过)
    try:
        if kind == "docx":
            import docx
            text = "\n".join(p.text for p in docx.Document(path).paragraphs)
            return {"kind": kind, "n_pages": 1, "status": "ok", "error": "", "pdf_meta": ""}, \
                [(1, "docx", len(text), litdb.quality(text), text)]
        import fitz
        pages = []
        with fitz.open(path) as d:
            meta = json.dumps({k: v for k, v in (d.metadata or {}).items() if v}, ensure_ascii=False)
            for i, pg in enumerate(d, 1):
                t = unicodedata.normalize("NFKC", pg.get_text()).strip()  # 知网全角 "Ｕｎｉｖｅｒｓｉｔｙ""第３１卷" -> 半角
                if len(t) >= litdb.MIN_TEXT_CHARS:
                    pages.append((i, "pdf", len(t), litdb.quality(t), t))
                else:
                    pages.append((i, "pending", len(t), None, t))
        return {"kind": kind, "n_pages": len(pages), "status": "ok", "error": "", "pdf_meta": meta}, pages
    except Exception as e:  # 损坏/加密 PDF: 记录错误, 不中断
        return {"kind": kind, "n_pages": 0, "status": "error", "error": f"{type(e).__name__}: {e}"[:500],
                "pdf_meta": ""}, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    src = Path(litdb.corpus_cfg(a.corpus)["source"])
    con = litdb.connect(a.corpus)
    known = {r[0]: (r[1], r[2]) for r in con.execute("SELECT relpath, size, mtime FROM docs WHERE status='ok'")}

    todo = []
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith("~$"):
            rel = p.relative_to(src).as_posix()
            st = p.stat()
            if known.get(rel) != (st.st_size, st.st_mtime):
                todo.append((p, rel, st))
    t0, done, errors = time.time(), 0, 0
    with ProcessPoolExecutor(a.workers) as ex:
        futs = {ex.submit(extract, p): (p, rel, st) for p, rel, st in todo}
        for f in as_completed(futs):
            p, rel, st = futs[f]
            info, pages = f.result()
            parts = rel.split("/")
            con.execute("DELETE FROM pages WHERE doc_id IN (SELECT doc_id FROM docs WHERE relpath=?)", (rel,))
            con.execute("DELETE FROM docs WHERE relpath=?", (rel,))
            cur = con.execute(
                "INSERT INTO docs (relpath, folder, author_dir, kind, size, mtime, n_pages, n_text, n_ocr,"
                " status, error, pdf_meta) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (rel, parts[0], parts[1] if parts[0] == "Taxonomy" and len(parts) > 2 else "",
                 info["kind"], st.st_size, st.st_mtime, info["n_pages"],
                 sum(x[1] != "pending" for x in pages), sum(x[1] == "pending" for x in pages),
                 info["status"], info["error"], info["pdf_meta"]))
            con.executemany("INSERT INTO pages (doc_id, page_no, source, chars, quality, text) VALUES (?,?,?,?,?,?)",
                            [(cur.lastrowid, *x) for x in pages])
            con.commit()
            done += 1
            errors += info["status"] == "error"
            if done % 50 == 0:
                print(f"  {done}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)

    n_docs, n_pages, n_pdf, n_pend = con.execute(
        "SELECT (SELECT count(*) FROM docs), count(*), sum(source IN ('pdf','docx')), sum(source='pending')"
        " FROM pages").fetchone()
    con.close()
    dst = litdb.backup(a.corpus)
    summary("01_inventory", [f"本次处理 {done} 个文件 ({errors} 个出错), 用时 {time.time() - t0:.0f}s",
                             f"库内 {n_docs} 个文件, {n_pages} 页: 文字层 {n_pdf} 页, 待 OCR {n_pend} 页",
                             f"备份 -> {dst}"])


if __name__ == "__main__":
    main()
