"""16 全盘增量刷新: 重新列出各盘文献文件, 只给新出现的打分并追加到 candidates.tsv.

  python3 16_refresh.py <corpus> [--drives c,d,e,...] [--workers N]

  起因 (2026-10-22): 赫列勃维奇 1963 (create_pdf.pdf) 在 10-14 全盘扫描后才下载, 库里没有;
        03 的清单由临时 find 命令生成, 没记录, 不能重跑.
  1) find 各盘 *.pdf -> discovery/pdfs_<盘>.tsv (size \\t path, 覆盖旧清单);
     *.caj/*.kdh/*.nh (知网格式) -> discovery/cnki_<盘>.tsv; 其中文件头是 %PDF 的按 PDF 处理, 其余列给用户转换
  2) 新路径 (不在 candidates.tsv、不在库内) -> 大小 + sha1 与库内/已有候选去重
     -> 03 西文打分 + 09 中文打分 -> include / review / exclude 追加到 candidates.tsv (refresh 列记日期)
  之后: include -> 05_ingest; review -> 子代理分拣.
"""
import argparse
import datetime
import importlib.util
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402


def load(name, mod):
    spec = importlib.util.spec_from_file_location(mod, Path(__file__).with_name(name))
    m = importlib.util.module_from_spec(spec)
    sys.modules[mod] = m  # 子进程 pickle 函数需按模块名找到
    spec.loader.exec_module(m)
    return m


disc = load("03_discover.py", "disc03")
resc = load("09_rescan.py", "resc09")
SKIP = ["/Windows/", "/Program Files", "/ProgramData/", "/$Recycle.Bin/", "/AppData/", "/site-packages/",
        "/node_modules/", "/win-library/", "/.git/", "/miniconda3/", "/anaconda3/"]


def find(drive, pattern):
    """find /mnt/<drive> -iname <pattern> -> [(size, path)]; 跳过系统/软件目录."""
    cmd = ["find", f"/mnt/{drive}", "-type", "f", "-iname", pattern, "-printf", "%s\\t%p\\n"]
    out = subprocess.run(cmd, capture_output=True, text=True, errors="replace").stdout
    rows = []
    for line in out.splitlines():
        size, _, p = line.partition("\t")
        if p and size.isdigit() and not any(s in p for s in SKIP):
            rows.append((int(size), p))
    return rows


def is_pdf(path):
    try:
        with open(path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def score_new(args):
    path, fams, groups = args
    r = disc.score((path, fams))
    z = resc.zh_score((path, groups)) if r.get("how") == "pdf" else {}
    return {**r, **{k: v for k, v in z.items() if k != "path"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--drives", default="c,d,e,f,g,h,i,j,k,l,m,n")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    cfg = litdb.corpus_cfg(a.corpus)
    dd = Path(cfg["db"]).parent / "discovery"
    lib_dir = str(Path(cfg["backup"]) / "文库") + "/"
    allp, cnki_pdf, cnki_other = [], [], []
    for d in a.drives.split(","):
        if not Path(f"/mnt/{d}").exists():
            continue
        pdfs = find(d, "*.pdf")
        pd.DataFrame(pdfs).to_csv(dd / f"pdfs_{d}.tsv", sep="\t", header=False, index=False)
        cnki = [r for pat in ("*.caj", "*.kdh", "*.nh") for r in find(d, pat)]
        pd.DataFrame(cnki, columns=["size", "path"]).to_csv(dd / f"cnki_{d}.tsv", sep="\t", index=False)
        allp += pdfs
        for s, p in cnki:
            (cnki_pdf if is_pdf(p) else cnki_other).append((s, p))
    cand = pd.read_csv(dd / "candidates.tsv", sep="\t", dtype=str)
    con = litdb.connect(a.corpus)
    known = set(cand.path) | {r[0] for r in con.execute("SELECT relpath FROM docs")} | {
        r[0] for r in con.execute("SELECT orig_path FROM docs WHERE orig_path IS NOT NULL")}
    src = str(Path(cfg["source"])) + "/"
    new = [(s, p) for s, p in allp + cnki_pdf if s > 10_000 and p not in known
           and not p.startswith(src) and not p.startswith(lib_dir)]
    # 去重: 同大小 -> sha1, 与库内文件及已有候选比
    sizes = {}
    for rel, size in con.execute("SELECT coalesce(orig_path, relpath), size FROM docs"):
        sizes.setdefault(size, []).append(rel if rel.startswith("/") else src + rel)
    rows, keep = [], []
    hashes = {}
    for s, p in new:
        dup = None
        for q in sizes.get(s, []):
            if q not in hashes and Path(q).exists():
                hashes[q] = disc.sha1(q)
            if hashes.get(q) and hashes[q] == disc.sha1(p):
                dup = q
                break
        if dup:
            rows.append({"path": p, "decision": "duplicate", "note": f"same sha1 as {dup}"})
        else:
            keep.append(p)
    fams = [ln.split("\t")[0] for ln in (dd / "family_vocab.txt").read_text().splitlines()]
    groups = resc.GROUP_ZH + resc.zh_families()
    with ProcessPoolExecutor(a.workers) as ex:
        scored = list(ex.map(score_new, [(p, fams, groups) for p in keep], chunksize=4))
    for r in scored:
        nm = len([m for m in (r.get("morph") or "").split(";") if m and m not in disc.WEAK_MORPH])
        nf = len([x for x in (r.get("fams") or "").split(";") if x])
        zg, zm = r.get("z_group", 0) or 0, len([m for m in (r.get("z_morph") or "").split(";") if m])
        named = bool(r.get("z_name")) or bool(resc.BINOMIAL.match(Path(r["path"]).name))
        dec = "exclude"
        if nm >= 1 or nf >= 3 or zg >= 1 or named:
            dec = "review"
        if nm >= 3 or ((zg >= 3 or named) and zm >= 3):
            dec = "include"
        if r.get("how") == "error":
            dec = "error"
        rows.append({**{k: r.get(k) for k in ("path", "pages", "how", "morph", "fams", "snippet")},
                     "n_morph": nm, "n_fam": nf, "decision": dec})
    today = datetime.date.today().isoformat()
    add = pd.DataFrame(rows).assign(refresh=today)
    pd.concat([cand, add], ignore_index=True).to_csv(dd / "candidates.tsv", sep="\t", index=False)
    pd.DataFrame(cnki_other, columns=["size", "path"]).to_csv(dd / "cnki_需转换.tsv", sep="\t", index=False)
    vc = add.decision.value_counts().to_dict() if len(add) else {}
    return summary("16_refresh", [f"全盘 PDF {len(allp)} 个 (+ 知网格式 {len(cnki_pdf) + len(cnki_other)} 个, 其中实为 PDF "
                                  f"{len(cnki_pdf)})", f"新文件 {len(new)} 个 -> {vc}",
                                  f"真 CAJ/KDH/NH {len(cnki_other)} 个需转换 -> {dd / 'cnki_需转换.tsv'}",
                                  "下一步: include -> 05_ingest; review -> 子代理分拣"])


if __name__ == "__main__":
    main()
