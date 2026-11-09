"""05 库外文献入库: 03_discover 判 include 的 PDF 原地引用 (不复制), 逐页取文字层.

  python3 05_ingest.py <corpus> [--workers N] [--decision include] [--decision review]

  docs.relpath 存绝对路径 (pathlib: source / 绝对路径 = 绝对路径, 02/04 无需改), folder='external'
  无文字层页 -> pending, 之后跑 02_ocr
  可重跑: 路径 + size + mtime 未变的跳过; 文件已不存在的跳过并计数.
"""
import argparse
import csv
import importlib.util
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

_spec = importlib.util.spec_from_file_location("inv01", Path(__file__).with_name("01_inventory.py"))
inv = importlib.util.module_from_spec(_spec)
sys.modules["inv01"] = inv  # 子进程 pickle 函数需按模块名找到
_spec.loader.exec_module(inv)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--decision", action="append", help="candidates.tsv 中要入库的判定, 默认 include")
    a = ap.parse_args()
    decisions = set(a.decision or ["include"])
    cand = Path(litdb.corpus_cfg(a.corpus)["db"]).parent / "discovery" / "candidates.tsv"
    con = litdb.connect(a.corpus)
    cols = [r[1] for r in con.execute("PRAGMA table_info(docs)")]
    key = "coalesce(orig_path, relpath)" if "orig_path" in cols else "relpath"  # 12_library 后 relpath 指文库副本
    known = {r[0]: (r[1], r[2]) for r in con.execute(f"SELECT {key}, size, mtime FROM docs WHERE status='ok'")}

    todo, missing = [], 0
    with open(cand, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["decision"] not in decisions:
                continue
            p = Path(row["path"])
            if not p.is_file():
                missing += 1
                continue
            st = p.stat()
            if known.get(row["path"]) != (st.st_size, st.st_mtime):
                todo.append((p, row["path"], st))
    t0, done, errors = time.time(), 0, 0
    with ProcessPoolExecutor(a.workers) as ex:
        futs = {ex.submit(inv.extract, p): (p, rel, st) for p, rel, st in todo}
        for f in as_completed(futs):
            p, rel, st = futs[f]
            info, pages = f.result()
            con.execute(f"DELETE FROM pages WHERE doc_id IN (SELECT doc_id FROM docs WHERE {key}=?)", (rel,))
            con.execute(f"DELETE FROM docs WHERE {key}=?", (rel,))
            cur = con.execute(
                "INSERT INTO docs (relpath, folder, author_dir, kind, size, mtime, n_pages, n_text, n_ocr,"
                " status, error, pdf_meta) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (rel, "external", "", info["kind"], st.st_size, st.st_mtime, info["n_pages"],
                 sum(x[1] != "pending" for x in pages), sum(x[1] == "pending" for x in pages),
                 info["status"], info["error"], info["pdf_meta"]))
            con.executemany("INSERT INTO pages (doc_id, page_no, source, chars, quality, text) VALUES (?,?,?,?,?,?)",
                            [(cur.lastrowid, *x) for x in pages])
            con.commit()
            done += 1
            errors += info["status"] == "error"
            if done % 50 == 0:
                print(f"  {done}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)

    n_ext, n_pend = con.execute(
        "SELECT (SELECT count(*) FROM docs WHERE folder='external'),"
        " (SELECT count(*) FROM pages WHERE source='pending')").fetchone()
    con.close()
    dst = litdb.backup(a.corpus)
    summary("05_ingest", [f"判定 {sorted(decisions)}: 本次入库 {done} 篇 ({errors} 个出错, {missing} 个文件已不存在),"
                          f" 用时 {time.time() - t0:.0f}s",
                          f"库内库外文献 {n_ext} 篇; 全库待 OCR {n_pend} 页 -> 跑 02_ocr",
                          f"备份 -> {dst}"])


if __name__ == "__main__":
    main()
