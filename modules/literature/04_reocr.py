"""04 重做 OCR: 修 QC (2026-10-15) 发现的三类问题. 被替换的旧文本存 page_alt, 不丢.

  python3 04_reocr.py <corpus> [--workers N] [--only A|B|C]

  A 语言误判: 用新 detect_lang 重判所有有 OCR 页的文献; 语言变了 -> 该篇 OCR 页全部按新语言重做, 直接替换
    (旧算法信 OSD 低置信度 Cyrillic: Johnson 1901、Allan Hancock 系列等英文被当俄文)
  B 低置信度: ocr_conf < 70 的页 -> ocr_page (含测方向旋转) 重做, 新置信度高 5 以上才替换
  C 乱码文字层: source='pdf' 且 quality < 0.5 的页 (Jirkov 2001 全书为字体编码乱码) -> OCR,
    新文本 quality 更高且 conf >= 50 才替换, 替换后 source='ocr'
"""
import argparse
import importlib.util
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

_spec = importlib.util.spec_from_file_location("ocr02", Path(__file__).with_name("02_ocr.py"))
ocr = importlib.util.module_from_spec(_spec)
sys.modules["ocr02"] = ocr  # 子进程 pickle 函数需按模块名找到
_spec.loader.exec_module(ocr)

ALT = """CREATE TABLE IF NOT EXISTS page_alt (
    doc_id INTEGER, page_no INTEGER, reader TEXT, text TEXT, conf REAL, quality REAL, saved TEXT,
    PRIMARY KEY (doc_id, page_no, reader))"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--only", choices=["A", "B", "C"])
    a = ap.parse_args()
    src = Path(litdb.corpus_cfg(a.corpus)["source"])
    con = litdb.connect(a.corpus)
    con.execute(ALT)
    paths = {r[0]: src / r[1] for r in con.execute("SELECT doc_id, relpath FROM docs")}
    langs = {r[0]: r[1] for r in con.execute("SELECT doc_id, ocr_lang FROM docs")}
    t0 = time.time()
    jobs = {}  # (doc_id) -> {page_no: reason}

    with ProcessPoolExecutor(a.workers) as ex:
        # A: 重判语言 (C 类文献若无语言也在此判)
        need = {r[0] for r in con.execute("SELECT DISTINCT doc_id FROM pages WHERE source='ocr'")}
        need |= {r[0] for r in con.execute("SELECT DISTINCT doc_id FROM pages WHERE source='pdf' AND quality<0.5")}
        pages_of = {}
        for d, pn in con.execute("SELECT doc_id, page_no FROM pages WHERE source IN ('ocr','pdf') AND"
                                 " (source='ocr' OR quality<0.5) ORDER BY doc_id, page_no"):
            pages_of.setdefault(d, []).append(pn)
        futs = {ex.submit(ocr.detect_lang, paths[d], pages_of[d], 300, ocr.layer_text(con, d)): d
                for d in sorted(need) if d in pages_of}
        changed = set()
        for f in as_completed(futs):
            d = futs[f]
            new = f.result()
            if new != langs.get(d):
                if langs.get(d):
                    changed.add(d)
                langs[d] = new
                con.execute("UPDATE docs SET ocr_lang=? WHERE doc_id=?", (new, d))
        con.commit()
        print(f"  语言重判 {len(futs)} 篇, 改变 {len(changed)} 篇, {time.time() - t0:.0f}s", flush=True)

        if a.only in (None, "A"):
            for d, pn in con.execute("SELECT doc_id, page_no FROM pages WHERE source='ocr'"):
                if d in changed:
                    jobs.setdefault(d, {})[pn] = "A"
        if a.only in (None, "B"):
            for d, pn in con.execute("SELECT doc_id, page_no FROM pages WHERE source='ocr' AND ocr_conf<70"
                                     " AND chars>50"):
                jobs.setdefault(d, {}).setdefault(pn, "B")
        if a.only in (None, "C"):
            for d, pn in con.execute("SELECT doc_id, page_no FROM pages WHERE source='pdf' AND quality<0.5"):
                jobs.setdefault(d, {}).setdefault(pn, "C")
        total = sum(len(v) for v in jobs.values())
        print(f"  待重做 {total} 页 (A {sum(r == 'A' for v in jobs.values() for r in v.values())},"
              f" B {sum(r == 'B' for v in jobs.values() for r in v.values())},"
              f" C {sum(r == 'C' for v in jobs.values() for r in v.values())})", flush=True)

        futs = {}
        for d, pp in jobs.items():
            pns = sorted(pp)
            for k in range(0, len(pns), ocr.CHUNK):
                futs[ex.submit(ocr.ocr_chunk, paths[d], pns[k:k + ocr.CHUNK], langs[d] or "eng", 300)] = d
        done, replaced = 0, {"A": 0, "B": 0, "C": 0}
        last_bak = time.time()
        for f in as_completed(futs):
            d = futs[f]
            for pn, text, conf, err in f.result():
                done += 1
                if err:
                    continue
                reason = jobs[d][pn]
                old_src, old_text, old_conf, old_q = con.execute(
                    "SELECT source, text, ocr_conf, quality FROM pages WHERE doc_id=? AND page_no=?", (d, pn)).fetchone()
                q = litdb.quality(text)
                ok = (reason == "A" or (reason == "B" and conf and conf > (old_conf or 0) + 5)
                      or (reason == "C" and conf and conf >= 50 and q > (old_q or 0)))
                if not ok:
                    continue
                reader = "pdf_layer" if old_src == "pdf" else "ocr_v1"
                con.execute("INSERT OR REPLACE INTO page_alt VALUES (?,?,?,?,?,?,date('now'))",
                            (d, pn, reader, old_text, old_conf, old_q))
                con.execute("UPDATE pages SET source='ocr', text=?, chars=?, quality=?, ocr_conf=?, ocr_lang=?"
                            " WHERE doc_id=? AND page_no=?", (text, len(text), q, conf, langs[d] or "eng", d, pn))
                replaced[reason] += 1
            con.commit()
            if done % 500 < ocr.CHUNK:
                el = time.time() - t0
                print(f"  {done}/{total} 页 {el / 3600:.1f}h, 已替换 {replaced}", flush=True)
            if time.time() - last_bak > ocr.BACKUP_EVERY:
                litdb.backup(a.corpus)
                last_bak = time.time()
    con.close()
    dst = litdb.backup(a.corpus)
    summary("04_reocr", [f"语言改判 {len(changed)} 篇; 重做 {done} 页, 用时 {(time.time() - t0) / 3600:.1f}h",
                         f"替换: A 语言 {replaced['A']}, B 低置信 {replaced['B']}, C 乱码层 {replaced['C']}",
                         "旧文本 -> page_alt", f"备份 -> {dst}"])


if __name__ == "__main__":
    main()
