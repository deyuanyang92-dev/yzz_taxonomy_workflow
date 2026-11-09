"""01 全文本地化: 01_文献/01_描述文献 每个 PDF 逐页文字 -> 08_知识库/<Genus>_KB.sqlite (表 files, pages).
文字层足够 (>=150 字) 用 PyMuPDF; 否则若该文件是多毛类文库 (/root/yzz-literature/polychaeta.db) 已入库文件的副本 (同大小同名)
则复用其 OCR; 都没有 -> tesseract (eng+deu+fra+spa+lat, 300 dpi). 可中断续跑 (已完成的文件跳过).
用法: python3 yzz.py compilation 01 <项目目录> [--workers 6]
"""
import os, sqlite3, subprocess, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg  # noqa: E402  项目根目录与配置
ROOT, SRC, DB, LIB = cfg.ROOT, cfg.PDFDIR, cfg.KB, cfg.LIB


def lib_index():
    con = sqlite3.connect(LIB)
    idx = {}
    for d, rp, op, size in con.execute("select doc_id, relpath, orig_path, size from docs"):
        for p in (rp, op):
            if p:
                idx[(os.path.basename(p), size)] = d
    return idx


def ocr_page(page):
    pix = page.get_pixmap(dpi=300)
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        pix.save(f.name)
        r = subprocess.run(["tesseract", f.name, "-", "-l", "eng+deu+fra+spa+lat", "--psm", "3"], capture_output=True, text=True, timeout=300)
    return r.stdout


def one(args):
    fn, lib_doc = args
    path = SRC / fn
    out = []
    doc = fitz.open(path)
    libpages = {}
    if lib_doc:
        con = sqlite3.connect(LIB)
        libpages = dict(con.execute("select page_no, text from pages where doc_id=? and source!='pending'", (lib_doc,)))
    for i, pg in enumerate(doc):
        t = pg.get_text()
        if len(t.strip()) >= 150:
            out.append((fn, i + 1, t, "pdf"))
        elif libpages.get(i + 1) and len(libpages[i + 1].strip()) >= 50:
            out.append((fn, i + 1, libpages[i + 1], "lib_ocr"))
        else:
            out.append((fn, i + 1, ocr_page(pg), "ocr"))
    return fn, out


def main():
    w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 6
    con = sqlite3.connect(DB)
    con.executescript("""create table if not exists files (file text primary key, ref_no text, n_pages int, done int default 0);
                         create table if not exists pages (file text, page_no int, text text, source text, primary key (file, page_no));""")
    idx = lib_index()
    todo = []
    for fn in sorted(os.listdir(SRC)):
        if not fn.lower().endswith(".pdf"):
            continue
        if con.execute("select done from files where file=?", (fn,)).fetchone() == (1,):
            continue
        orig = fn.split("__", 1)[-1] if "__" in fn else fn
        todo.append((fn, idx.get((orig, os.path.getsize(SRC / fn)))))
    print(f"[01_kb_pages] {len(todo)} files to process", flush=True)
    with ProcessPoolExecutor(w) as ex:
        for k, (fn, rows) in enumerate(ex.map(one, todo), 1):
            con.executemany("insert or replace into pages values (?,?,?,?)", rows)
            con.execute("insert or replace into files values (?,?,?,1)", (fn, fn.split("_")[0], len(rows)))
            con.commit()
            src = {s: sum(r[3] == s for r in rows) for s in ("pdf", "lib_ocr", "ocr")}
            print(f"{k}/{len(todo)} {fn[:70]} {src}", flush=True)
    if cfg.WORMS_NAMES and Path(cfg.WORMS_NAMES).exists():     # 名称表 (汇编封面的状态、排版斜体用)
        import pandas as pd
        nm = pd.read_csv(cfg.WORMS_NAMES, sep="\t", dtype=str).fillna("").rename(columns={"scientific_name": "name"})
        nm[["aphia_id", "name", "authority", "status", "valid_aphia_id", "valid_name", "valid_authority"]].to_sql(
            "worms_names", con, if_exists="replace", index=False)
    n = con.execute("select count(*), sum(source='ocr'), sum(source='lib_ocr') from pages").fetchone()
    print(f"[01_kb_pages] pages {n[0]} (new OCR {n[1]}, reused library OCR {n[2]}) -> {DB}")


if __name__ == "__main__":
    main()
