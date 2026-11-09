"""13 中文/日文文献重 OCR: 修 2026-10-21 用户发现的 "中国海文献搜不到".

  python3 13_zh_reocr.py <corpus> detect [--workers N] [--recheck]   抽样判定 -> <db 目录>/zh_reocr.tsv
  python3 13_zh_reocr.py <corpus> redo [--workers N]                 判定的文献全书按 chi_sim+eng / jpn+eng 重 OCR

  病因: (1) 02/04 detect_lang 把中文扫描书判成 eng/eng+dan (中国动物志 沙蚕目、吴宝铃文选 II、Wu et al. 1981),
            中文正文成 "PH ame Rob] FEM" 式乱码, 且乱码像英文词 -> quality 0.8, QC 抓不到;
        (2) 旧文字层本身乱码 (沈寿彭 & 吴宝铃 1993: "& * S # 0 B Al").
  detect: 候选 = 文件名含汉字, 或任一页有汉字, 或 ocr_lang 含 chi, 或有 OCR 页而未判中文
          (拉丁文件名的中文扫描件按英文 OCR 后不含任何汉字); 增量 (已抽检跳过); 抽 2 页 (1/3、2/3 处) chi_sim+eng OCR.
          判据 = 不同汉字种数 (去掉与表格符号形近的 一二十己乙王 等): 表格页误认只有 1-14 种, 中文文献 >= 84 种
          (2026-10-22 实测; 汉字个数、占比、连串都分不开: Ushakov 1974 俄文表格页 "一 十 十 一" 也成串).
          >= 60 种 -> 中文 (文件名繁体 -> chi_tra+eng); 20-60 种 -> 再试 jpn+eng, 假名 >= 30 -> 日文 (Imajima 2001);
          且新汉字 >= 旧 x 2. 韩文不走 jpn (会把谚文误认成假名: Paik 1997、韩国多鳞虫学位论文) -> kor+eng,
          逐页谚文 >= 30 且多于旧文本才替换.
  latin:  知网式文字层 (汉字 >= 1000 但拉丁字母 < 5%: 学名、数字被丢; 沈寿彭 & 戚桑 1982) -> mode=latin;
          redo 时拉丁字母翻倍以上且汉字保留 >= 60% 才替换.
  redo:   全书各页按判定语言 OCR; 新文本不同汉字 >= 8 种 (日文: 或假名 >= 20) 且汉字多于旧文本 -> 替换
          (source='ocr', ocr_lang=语言); 旧文本存 page_alt (reader='pre_zh'). 之后重跑 07_fts build.
"""
import argparse
import importlib.util
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

_spec = importlib.util.spec_from_file_location("ocr02", Path(__file__).with_name("02_ocr.py"))
ocr = importlib.util.module_from_spec(_spec)
sys.modules["ocr02"] = ocr  # 子进程 pickle 函数需按模块名找到
_spec.loader.exec_module(ocr)

CJK = re.compile(r"[一-鿿]")
KANA = re.compile(r"[぀-ヿ]")
LOOKALIKE = set("一二三十己已乙王上土干工口日人入八丨了子")  # 表格的 - + | 线框常被认成这些字
ZH, ZH_TRA, JA = "chi_sim+eng", "chi_tra+eng", "jpn+eng"
TRAD = re.compile(r"[國動誌蟲蠶鬚葉類屬綱門環節區灣臺錄錄學報]")  # 文件名含繁体 -> chi_tra (台湾《中國動物志》等)
KOREAN = re.compile(r"Korea|Paik|韩国|韓國", re.I)  # 韩文: jpn 会把谚文误认成假名 -> 不走 jpn, 用 kor+eng
KO = "kor+eng"  # kor 语言包 2026-10-22 装 (用户同意; tessdata_fast)
HANGUL = re.compile(r"[\uac00-\ud7af]")
DOC_ZH, DOC_JA = 60, 20        # 抽样 2 页不同汉字种数: >= 60 中文; 20-60 试日文
DOC_KANA, PAGE_KANA = 30, 20   # 假名个数: 文献判日文 / 逐页替换
PAGE_DISTINCT = 8              # 逐页替换: 新文本不同汉字种数下限
ALT = """CREATE TABLE IF NOT EXISTS page_alt (
    doc_id INTEGER, page_no INTEGER, reader TEXT, text TEXT, conf REAL, quality REAL, saved TEXT,
    PRIMARY KEY (doc_id, page_no, reader))"""


def n_cjk(t):
    return len(CJK.findall(t or ""))


def distinct(t):
    return len(set(CJK.findall(t or "")) - LOOKALIKE)


def page_ok(text, lang):
    """逐页把关: 新文本确有中/日文 (不是表格符号误认), 才允许替换."""
    return distinct(text) >= PAGE_DISTINCT or (lang == JA and len(KANA.findall(text)) >= PAGE_KANA)


def probe(args):
    """子进程: 抽样页 chi_sim+eng OCR (必要时再 jpn+eng) -> (doc_id, 旧汉字, 新汉字, 种数, 假名, 语言, 错误)."""
    doc_id, path, samples = args
    import fitz
    try:
        with fitz.open(path) as d:
            zh = "".join(ocr.ocr_page(ocr.render(d, p, 300), ZH)[0] for p, _ in samples)
            k, lang = 0, ""
            dz = distinct(zh)
            if dz >= DOC_ZH:
                lang = ZH_TRA if TRAD.search(Path(path).name) else ZH
            elif dz >= DOC_JA:
                ja = "".join(ocr.ocr_page(ocr.render(d, p, 300), JA)[0] for p, _ in samples)
                k = len(KANA.findall(ja))
                lang = JA if k >= DOC_KANA and not KOREAN.search(path) else ""
    except Exception as e:
        return doc_id, -1, -1, -1, -1, "", str(e)[:200]
    return doc_id, sum(n_cjk(t) for _, t in samples), n_cjk(zh), dz, k, lang, ""


def redo_page(args):
    doc_id, path, page_no, lang = args
    import fitz
    try:
        with fitz.open(path) as d:
            text, conf = ocr.ocr_page(ocr.render(d, page_no, 300), lang)[:2]
    except Exception as e:
        return doc_id, page_no, lang, None, None, str(e)[:200]
    return doc_id, page_no, lang, litdb.cjk_join(text), conf, ""


def detect(corpus, workers, recheck=False):
    con = litdb.connect(corpus)
    src = Path(litdb.corpus_cfg(corpus)["source"])
    cand = {}
    for doc_id, rel, lang, n in con.execute("SELECT doc_id, relpath, ocr_lang, n_pages FROM docs WHERE status='ok'"
                                            " AND kind='pdf'"):
        if CJK.search(Path(rel).name) or "chi" in (lang or ""):
            cand[doc_id] = (rel, n)
    extra = con.execute("SELECT DISTINCT doc_id FROM pages WHERE text GLOB '*[一-龥]*'").fetchall()
    # 拉丁文件名 + 按英文 OCR 的中文扫描件: 文本里一个汉字也没有, 上两条抓不到 -> 凡有 OCR 页且未判中文的都抽检
    extra += con.execute("SELECT DISTINCT p.doc_id FROM pages p JOIN docs d USING (doc_id) WHERE p.source='ocr'"
                         " AND coalesce(d.ocr_lang, '') NOT LIKE '%chi%'").fetchall()
    for (doc_id,) in extra:
        if doc_id not in cand:
            rel, n = con.execute("SELECT relpath, n_pages FROM docs WHERE doc_id=?", (doc_id,)).fetchone()
            cand[doc_id] = (rel, n)
    out = Path(litdb.corpus_cfg(corpus)["db"]).parent / "zh_reocr.tsv"
    prev = pd.read_csv(out, sep="\t") if out.exists() else pd.DataFrame(columns=["doc_id"])
    if recheck and len(prev):  # 旧判据 (汉字个数/占比) 判过 redo 或疑似的, 按种数重新抽检
        stale = prev.get("distinct", pd.Series(index=prev.index, dtype=float)).isna() & (prev.new_cjk >= DOC_JA)
        prev = prev[~stale]
    probed = set(prev.doc_id)  # 增量: 已抽检的不重做
    jobs = []
    for doc_id, (rel, n) in cand.items():
        if doc_id in probed:
            continue
        cnt = list(con.execute("SELECT page_no, text FROM pages WHERE doc_id=? AND chars > 300 ORDER BY page_no",
                               (doc_id,)))
        if not cnt:
            continue
        samples = [cnt[len(cnt) // 3], cnt[2 * len(cnt) // 3]] if len(cnt) > 2 else cnt[:1]
        jobs.append((doc_id, str(src / rel), samples))
    rows = []
    with ProcessPoolExecutor(workers) as ex:
        for f in as_completed([ex.submit(probe, j) for j in jobs]):
            doc_id, old, new, dz, kana, lang, err = f.result()
            rows.append({"doc_id": doc_id, "path": cand[doc_id][0], "pages": cand[doc_id][1], "old_cjk": old,
                         "new_cjk": new, "distinct": dz, "kana": kana, "lang": lang,
                         "redo": bool(lang) and new >= 2 * max(old, 1), "error": err})
    new_df = pd.DataFrame(rows)
    df = pd.concat([prev, new_df], ignore_index=True).sort_values("new_cjk", ascending=False)
    df.to_csv(out, sep="\t", index=False)
    r = df[df.redo.astype(bool)]
    return [f"本次抽检 {len(new_df)} 篇 (判需重做 {int(new_df.redo.sum()) if len(new_df) else 0}); 累计候选 {len(df)} 篇",
            f"需重 OCR {len(r)} 篇 ({r.lang.value_counts().to_dict()}), 共 {int(r.pages.sum())} 页 -> {out}"]


ASCII = re.compile(r"[A-Za-z]")


def detect_latin(corpus):
    """知网式文字层: 汉字多但几乎没有拉丁字母/数字 (学名、数字被丢, 沈寿彭 & 戚桑 1982 全文 Namalycastis 0 次)
    -> mode=latin 重 OCR. 只读库内文字, 不抽样 OCR."""
    con = litdb.connect(corpus)
    out = Path(litdb.corpus_cfg(corpus)["db"]).parent / "zh_reocr.tsv"
    prev = pd.read_csv(out, sep="\t", dtype={"error": object, "lang": object, "mode": object})
    have = set(prev[prev.redo.astype(bool)].doc_id)
    rows = []
    for doc_id, rel, n in con.execute("SELECT doc_id, relpath, n_pages FROM docs WHERE status='ok' AND kind='pdf'"):
        if doc_id in have:
            continue
        t = "".join(x or "" for (x,) in con.execute("SELECT text FROM pages WHERE doc_id=? AND source='pdf'", (doc_id,)))
        k = n_cjk(t)
        if k >= 1000 and len(ASCII.findall(t)) < 0.05 * k:
            rows.append({"doc_id": doc_id, "path": rel, "pages": n, "old_cjk": k, "new_cjk": None, "distinct": None,
                         "kana": 0, "lang": ZH_TRA if TRAD.search(Path(rel).name) else ZH, "redo": True,
                         "mode": "latin", "error": "文字层缺拉丁/数字"})
    df = pd.concat([prev, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(out, sep="\t", index=False)
    return [f"知网式文字层 (汉字 >= 1000, 拉丁字母 < 5%) {len(rows)} 篇, 共 {int(sum(r['pages'] for r in rows))} 页"
            " -> mode=latin, 跑 redo"]


def redo(corpus, workers):
    con = litdb.connect(corpus)
    con.execute(ALT)
    src = Path(litdb.corpus_cfg(corpus)["source"])
    df = pd.read_csv(Path(litdb.corpus_cfg(corpus)["db"]).parent / "zh_reocr.tsv", sep="\t")
    df = df[df.redo.astype(bool)]
    done_alt = {(d, p) for d, p in con.execute("SELECT doc_id, page_no FROM page_alt WHERE reader='pre_zh'")}
    mode = {int(r.doc_id): (getattr(r, "mode", "") if isinstance(getattr(r, "mode", ""), str) else "")
            for r in df.itertuples()}
    jobs = [(int(r.doc_id), str(src / r.path), p, r.lang) for r in df.itertuples()
            for (p,) in con.execute("SELECT page_no FROM pages WHERE doc_id=?", (int(r.doc_id),))
            if (int(r.doc_id), p) not in done_alt]
    t0, n, rep, last_bak = time.time(), 0, 0, time.time()
    print(f"中/日文重 OCR: {len(df)} 篇 {len(jobs)} 页, {workers} 进程", flush=True)
    with ProcessPoolExecutor(workers) as ex:
        for f in as_completed([ex.submit(redo_page, j) for j in jobs]):
            doc_id, page_no, lang, text, conf, err = f.result()
            n += 1
            if text is None:
                continue
            old, q_old, c_old = con.execute("SELECT text, quality, ocr_conf FROM pages WHERE doc_id=? AND page_no=?",
                                            (doc_id, page_no)).fetchone()
            con.execute("INSERT OR REPLACE INTO page_alt VALUES (?,?,?,?,?,?,datetime('now'))",
                        (doc_id, page_no, "pre_zh", old, c_old, q_old))
            if lang == KO:  # 韩文: 谚文 >= 30 且多于旧文本
                ok = len(HANGUL.findall(text)) >= 30 and len(HANGUL.findall(text)) > len(HANGUL.findall(old or ""))
            elif mode.get(doc_id) == "latin":  # 补学名/数字: 拉丁字母翻倍以上且汉字保留 >= 60%
                ok = (len(ASCII.findall(text)) >= 2 * len(ASCII.findall(old or "")) + 30
                      and n_cjk(text) >= 0.6 * n_cjk(old))
            else:
                ok = page_ok(text, lang) and n_cjk(text) > n_cjk(old)
            if ok:
                con.execute("UPDATE pages SET text=?, source='ocr', chars=?, quality=?, ocr_conf=?, ocr_lang=?"
                            " WHERE doc_id=? AND page_no=?",
                            (text, len(text), litdb.quality(text), conf, lang, doc_id, page_no))
                rep += 1
            if n % 200 == 0:
                con.commit()
                el = time.time() - t0
                print(f"  {n}/{len(jobs)} 页 {el / 3600:.1f}h 预计剩 {el / n * (len(jobs) - n) / 3600:.1f}h, 替换 {rep}",
                      flush=True)
            if time.time() - last_bak > 3600:
                con.commit()
                litdb.backup(corpus)
                last_bak = time.time()
    for r in df.itertuples():
        con.execute("UPDATE docs SET ocr_lang=? WHERE doc_id=?", (r.lang, int(r.doc_id)))
    con.commit()
    con.close()
    return [f"重 OCR {n} 页, 替换 {rep} 页, 用时 {(time.time() - t0) / 3600:.1f}h; 旧文本 -> page_alt pre_zh",
            f"备份 -> {litdb.backup(corpus)}", "下一步: 07_fts build (中文检索)"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("step", choices=["detect", "latin", "redo"])
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--recheck", action="store_true", help="detect: 旧判据下新汉字 >= 20 的按种数重新抽检")
    a = ap.parse_args()
    summary(f"13_zh_reocr {a.step}", {"detect": lambda: detect(a.corpus, a.workers, a.recheck),
                                      "latin": lambda: detect_latin(a.corpus),
                                      "redo": lambda: redo(a.corpus, a.workers)}[a.step]())


if __name__ == "__main__":
    main()
