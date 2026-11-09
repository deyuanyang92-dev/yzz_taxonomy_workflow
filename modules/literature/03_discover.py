"""03 全盘发现: 从各盘 PDF 清单中找出库外的多毛类 (及星虫/螠) 分类文献.

  python3 03_discover.py <corpus> [--workers N]

  输入: <db 目录>/discovery/pdfs_<盘>.tsv  (size \\t path; 由 find 全盘扫描生成, 见 README)
  1) 去重: 与库内文件大小相同者算 sha1 比对; 候选之间也按 sha1 去重 (保留路径最短的一份)
  2) 打分: 文件名 + 前 8 页文字 (无文字层则 OCR 前 2 页) 中出现的
       MORPH = 多毛类形态术语 (非环节动物文献几乎不出现), FAM = 库内高频科名 (含少量非环节动物科, 只作弱证据)
     include: MORPH >= 3 种;  review: MORPH 1-2 种 或 FAM >= 3 种 (交给子代理读首页判断);  exclude: 其余
  输出: discovery/candidates.tsv (每个候选一行, 含判定依据), 不改数据库.
"""
import argparse
import hashlib
import unicodedata
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

MORPH = ["parapodi", "notopodi", "neuropodi", "notochaet", "neurochaet", "notoset", "neuroset", "chaetiger",
         "setiger", "prostomi", "peristomi", "pygidi", "elytr", "polychaet", "polychète", "sipuncul", "echiur",
         "acicul", "uncini", "tentacular cirr", "dorsal cirr", "ventral cirr", "nuchal organ", "branchiae",
         "borsten", "ruder", "kopflappen", "soies", "rame", "quetas", "sedas"]
WEAK_MORPH = {"borsten", "ruder", "soies", "rame", "quetas", "sedas", "branchiae"}  # 一般词, 不单独计入
FAM_MIN_DOCS = 15


def sha1(path, limit=None):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
            if limit and f.tell() >= limit:
                break
    return h.hexdigest()


def text_of(path):
    import fitz
    with fitz.open(path) as d:
        n = d.page_count
        t = unicodedata.normalize("NFKC", "\n".join(d[i].get_text() for i in range(min(8, n))))  # 全角 -> 半角
        if len(t.strip()) < 300 and n:
            import importlib.util
            spec = importlib.util.spec_from_file_location("ocr", Path(__file__).with_name("02_ocr.py"))
            ocr = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ocr)
            t = "\n".join(ocr.ocr_page(ocr.render(d, i + 1, 200), "eng")[0] for i in range(min(2, n)))
            return t, n, "ocr"
        return t, n, "pdf"


def score(args):
    path, fams = args
    try:
        t, n, how = text_of(path)
    except Exception as e:
        return {"path": path, "pages": 0, "how": "error", "morph": "", "fams": "", "note": str(e)[:200]}
    low = (Path(path).name + "\n" + t).lower()
    morph = sorted(m for m in MORPH if m in low)
    fam = sorted(f for f in fams if f.lower() in low)
    return {"path": path, "pages": n, "how": how, "morph": ";".join(morph), "fams": ";".join(fam),
            "snippet": re.sub(r"\s+", " ", t[:400])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    cfg = litdb.corpus_cfg(a.corpus)
    disc = Path(cfg["db"]).parent / "discovery"
    src = Path(cfg["source"])
    con = litdb.connect(a.corpus)

    rows = []
    for f in sorted(disc.glob("pdfs_*.tsv")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            size, _, p = line.partition("\t")
            if p and size.isdigit():
                rows.append((int(size), p))
    cand = pd.DataFrame(rows, columns=["size", "path"]).drop_duplicates("path")
    in_lib = {r[0] for r in con.execute("SELECT relpath FROM docs")}
    if "orig_path" in [r[1] for r in con.execute("PRAGMA table_info(docs)")]:
        in_lib |= {r[0] for r in con.execute("SELECT orig_path FROM docs WHERE orig_path IS NOT NULL")}
    lib_dir = str(Path(cfg["backup"]) / "文库") + "/"  # 12_library 的副本, 不是新发现
    cand = cand[~cand.path.map(lambda p: p in in_lib or p.startswith(str(src) + "/") or p.startswith(lib_dir))]
    cand = cand[cand["size"] > 10_000]  # <10 KB 多为空壳/损坏

    # 1) 与库内同大小文件 sha1 比对
    lib_sizes = {}
    for relpath, size in con.execute("SELECT relpath, size FROM docs"):
        lib_sizes.setdefault(size, []).append(relpath)
    lib_hash = {}
    dup_of = {}
    for size, p in cand[cand["size"].isin(lib_sizes)].itertuples(index=False):
        h = sha1(p)
        for rel in lib_sizes[size]:
            if rel not in lib_hash:
                lib_hash[rel] = sha1(src / rel)
            if lib_hash[rel] == h:
                dup_of[p] = rel
                break
    # 候选之间去重: 同大小 -> sha1, 保留路径最短的
    keep, seen = [], {}
    for size, p in sorted(cand.itertuples(index=False), key=lambda r: (r[0], len(r[1]))):
        if p in dup_of:
            continue
        if (cand["size"] == size).sum() > 1:
            h = sha1(p)
            if h in seen:
                dup_of[p] = seen[h]
                continue
            seen[h] = p
        keep.append(p)

    # 2) 打分
    fams = [r.split("\t")[0] for r in (disc / "family_vocab.txt").read_text().splitlines()]
    fams = [f for f in fams]  # 全部科名, 只作弱证据
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(score, [(p, fams) for p in keep], chunksize=4))
    out = pd.DataFrame(res)
    nm = out.morph.map(lambda s: len([m for m in s.split(";") if m and m not in WEAK_MORPH]))
    nf = out.fams.map(lambda s: len([x for x in s.split(";") if x]))
    out["n_morph"], out["n_fam"] = nm, nf
    out["decision"] = "exclude"
    out.loc[(nm >= 1) | (nf >= 3), "decision"] = "review"
    out.loc[nm >= 3, "decision"] = "include"
    out.loc[out.how == "error", "decision"] = "error"
    dups = pd.DataFrame([{"path": p, "decision": "duplicate", "note": f"same sha1 as {d}"} for p, d in dup_of.items()])
    out = pd.concat([out, dups], ignore_index=True)
    out.to_csv(disc / "candidates.tsv", sep="\t", index=False)
    vc = out.decision.value_counts().to_dict()
    summary("03_discover", [f"全盘 PDF {len(rows)} 个, 库外候选 {len(cand)} 个",
                            "判定: " + ", ".join(f"{k} {v}" for k, v in vc.items()),
                            f"-> {disc / 'candidates.tsv'}"])


if __name__ == "__main__":
    main()
