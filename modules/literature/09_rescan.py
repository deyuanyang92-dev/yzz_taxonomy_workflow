"""09 重扫纯扫描候选: 修 03_discover 漏判 (2026-10-21 发现).

  python3 09_rescan.py <corpus> [--workers N] [--samples 6]

  03 对无文字层 PDF 只 OCR 前 2 页 (多为封面/扉页) -> 整卷期刊、专著被判 exclude:
    Johnston 1840 (Ann. Mag. Nat. Hist. 整卷 534 页)、中国动物志 环节动物门 多毛纲 (二)、Imajima 2009 等.
  本步: 03 判 exclude 且 (how='ocr' 或 >= 20 页) 的候选, 在全书均匀抽 N 页 (有文字层直接取, 否则 OCR) (文件名含 CJK -> chi_sim+eng),
        MORPH 加中文术语, 文件名命中类群词也计入; 重新判定写回 candidates.tsv (原判定记入 rescan 列).
  之后: 新 include -> 05_ingest; 新 review -> 06_triage.

  python3 09_rescan.py <corpus> --zh
  03 的 MORPH 只有西文术语, 有文字层的中文论文命中 0 -> exclude (2026-10-22 用户发现: 沈寿彭 & 戚桑 1982
  《珠江广州河段的淡水环节动物多毛类》, 文件名就含 "多毛类"). 本步: exclude 且 how='pdf' 且前 8 页汉字 >= 200 的,
  按中文类群词 (多毛/环节动物/沙蚕/星虫/螠 + 名录环节动物中文科名) 与中文形态复合词重判:
    (类群词 >= 3 或文件名含类群词) 且 形态词 >= 3 种 -> include; 类群词 >= 1 或文件名含类群词 -> review; 否则不变.
"""
import argparse
import importlib.util
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

_spec = importlib.util.spec_from_file_location("disc03", Path(__file__).with_name("03_discover.py"))
disc = importlib.util.module_from_spec(_spec)
sys.modules["disc03"] = disc  # 子进程 pickle 函数需按模块名找到
_spec.loader.exec_module(disc)
_spec = importlib.util.spec_from_file_location("ocr02", Path(__file__).with_name("02_ocr.py"))
ocr = importlib.util.module_from_spec(_spec)
sys.modules["ocr02"] = ocr
_spec.loader.exec_module(ocr)

CJK = re.compile(r"[一-鿿]")
MORPH_ZH = ["疣足", "刚毛", "刚节", "口前叶", "围口节", "背须", "腹须", "鳃", "足刺", "钩毛", "触手"]
BINOMIAL = re.compile(r"^\(?[A-Z][a-z]+\)? [a-z]{3,} .*\b1[789]\d\d|^\(?[A-Z][a-z]+\)? [a-z]{3,} .*\b20\d\d")  # "Travisia forbesii Johnston, 1840.pdf"
MORPH_ZH2 = ["疣足", "刚节", "口前叶", "围口节", "背须", "腹须", "足刺", "钩毛", "触须", "背叶", "腹叶", "颚齿", "肛须",
             "刚毛"]  # 不用单字 鳃/吻 (鱼类论文也有); 刚毛 昆虫/甲壳类也用 -> 须同时有类群词
GROUP_ZH = ["多毛", "环节动物", "沙蚕", "星虫", "螠", "环虫", "管栖蠕虫"]
GROUP_NAME = ["多毛", "环节动物", "星虫", "螠", "沙蚕", "polychaet", "annelid", "sipuncul", "echiur"]


def rescan(args):
    path, samples = args
    import fitz
    try:
        lang = "chi_sim+eng" if CJK.search(Path(path).name) else "eng"
        with fitz.open(path) as d:
            n = d.page_count
            picks = sorted({min(n, max(3, round(n * (i + 1) / (samples + 1)))) for i in range(samples)}) if n > 2 else []
            text = "\n".join(t if len(t := d[p - 1].get_text().strip()) >= litdb.MIN_TEXT_CHARS
                             else ocr.ocr_page(ocr.render(d, p, 200), lang)[0] for p in picks)
    except Exception as e:
        return {"path": path, "r_error": str(e)[:200]}
    low = text.lower()
    morph = [m for m in disc.MORPH if m in low and m not in disc.WEAK_MORPH] + [m for m in MORPH_ZH if m in text]
    name_hit = [g for g in GROUP_NAME if g in Path(path).name.lower()] + (["binomial"] if BINOMIAL.match(Path(path).name) else [])
    return {"path": path, "r_pages": ",".join(map(str, picks)), "r_morph": ";".join(morph),
            "r_name": ";".join(name_hit), "r_error": ""}


def zh_families():
    import sqlite3
    cn = sqlite3.connect(Path(__file__).resolve().parents[2] / "cache" / "cn_names.sqlite")
    return [r[0] for r in cn.execute("SELECT DISTINCT cn FROM names WHERE rank='Family' AND phylum IN"
                                     " ('Annelida', 'Sipuncula', 'Echiura') AND length(cn) >= 3")]


def zh_score(args):
    """子进程: 文字层前 8 页 + 文件名 -> 中文类群词/形态词计数."""
    path, groups = args
    import fitz
    try:
        with fitz.open(path) as d:
            t = "\n".join(d[i].get_text() for i in range(min(8, d.page_count)))
    except Exception as e:
        return {"path": path, "z_error": str(e)[:200]}
    name = Path(path).name
    return {"path": path, "z_cjk": len(CJK.findall(t)), "z_group": sum(t.count(g) for g in groups),
            "z_group_kinds": ";".join(g for g in groups if g in t)[:200],
            "z_morph": ";".join(m for m in MORPH_ZH2 if m in t), "z_name": ";".join(g for g in groups if g in name),
            "z_error": ""}


def main_zh(a):
    dpath = Path(litdb.corpus_cfg(a.corpus)["db"]).parent / "discovery" / "candidates.tsv"
    cand = pd.read_csv(dpath, sep="\t", dtype={"rescan": object, "triage": object})
    sel = (cand.decision == "exclude") & (cand.how == "pdf")
    groups = GROUP_ZH + zh_families()
    with ProcessPoolExecutor(a.workers) as ex:
        res = pd.DataFrame(ex.map(zh_score, [(p, groups) for p in cand[sel].path], chunksize=8))
    res = res[res.z_cjk.fillna(0) >= 200].copy()  # 只看中文文献
    nm = res.z_morph.fillna("").map(lambda s: len([m for m in s.split(";") if m]))
    named = res.z_name.fillna("") != ""
    res["new"] = "exclude"
    res.loc[(res.z_group >= 1) | named, "new"] = "review"
    res.loc[((res.z_group >= 3) | named) & (nm >= 3), "new"] = "include"
    res.to_csv(dpath.with_name("rescan_zh.tsv"), sep="\t", index=False)
    new = {p: v for p, v in zip(res.path, res.new) if v != "exclude"}
    m = cand.path.isin(new) & sel
    cand.loc[m, "rescan"] = "was_exclude_zh"
    cand.loc[m, "decision"] = cand.loc[m, "path"].map(new)
    cand.to_csv(dpath, sep="\t", index=False)
    summary("09_rescan --zh", [f"exclude 且有文字层 {int(sel.sum())} 篇, 其中中文 (汉字 >= 200) {len(res)} 篇",
                               f"改判: {res.new.value_counts().to_dict()}",
                               f"-> {dpath.with_name('rescan_zh.tsv')}; include 跑 05_ingest, review 交子代理分拣"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--samples", type=int, default=6)
    ap.add_argument("--zh", action="store_true", help="中文文字层 PDF 按中文类群词/术语重判")
    a = ap.parse_args()
    if a.zh:
        return main_zh(a)
    dpath = Path(litdb.corpus_cfg(a.corpus)["db"]).parent / "discovery" / "candidates.tsv"
    cand = pd.read_csv(dpath, sep="\t")
    sel = (cand.decision == "exclude") & ((cand.how == "ocr") | (cand.pages >= 20))
    todo = cand[sel].path.tolist()
    with ProcessPoolExecutor(a.workers) as ex:
        res = pd.DataFrame(ex.map(rescan, [(p, a.samples) for p in todo], chunksize=2))
    nm = res.r_morph.fillna("").map(lambda s: len([m for m in s.split(";") if m]))
    nn = res.r_name.fillna("").map(lambda s: len([m for m in s.split(";") if m]))
    res["new"] = "exclude"
    res.loc[(nm >= 1) | (nn >= 1), "new"] = "review"
    res.loc[(nm >= 3) | ((nn >= 1) & (nm >= 1)), "new"] = "include"
    res.to_csv(dpath.with_name("rescan.tsv"), sep="\t", index=False)

    new = dict(zip(res.path, res.new))
    if "rescan" not in cand:
        cand["rescan"] = ""
    m = cand.path.isin(new) & sel
    cand.loc[m, "rescan"] = "was_exclude"
    cand.loc[m, "decision"] = cand.loc[m, "path"].map(new)
    cand.to_csv(dpath, sep="\t", index=False)
    summary("09_rescan", [f"exclude 候选 (扫描或 >= 20 页) {len(todo)} 篇, 每篇抽 {a.samples} 页 OCR",
                          f"改判: {res.new.value_counts().to_dict()}",
                          f"-> {dpath.with_name('rescan.tsv')}; include 跑 05_ingest, review 跑 06_triage"])


if __name__ == "__main__":
    main()
