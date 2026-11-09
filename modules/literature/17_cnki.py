"""17 知网 CAJ 转 PDF: 16_refresh 列出的真 CAJ (文件头不是 %PDF) -> <backup>/知网转换/<原名>.pdf; 原文件不动.

  python3 17_cnki.py <corpus> [--workers N]

  工具: vendor/caj2pdf (GitHub caj2pdf/caj2pdf, 用户 2026-10-22 同意下载), 独立 venv (PyPDF2 2.2.0);
        它调用的 `mutool clean` 用 vendor/caj2pdf/bin/mutool (PyMuPDF 重存) 代替, 不装系统 MuPDF.
  只转 .caj (.nh/.kdh 本库现有 4 个: 长江口生态、海葵, 不需要). caj 内部为 HN 格式的需 libjbigdec.so
  (vendor/caj2pdf 下 cc -fPIC --shared -o libjbigdec.so lib/jbigdec.cc lib/JBigDecode.cc 已编译);
  JBIG2 图像需 libjbig2codec.so (要 apt 装 poppler/jbig2dec 开发包, 未装); 纯文本 HN 无法转换.
  按 sha1 去重后转换; 每个文件在独立临时目录里跑 (caj2pdf 在当前目录写 pdf.tmp).
  之后: 16_refresh --drives n 会把 知网转换/ 里的新 PDF 当新文件打分 -> 分拣 -> 05_ingest.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

V = ROOT / "vendor" / "caj2pdf"


def sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def convert(args):
    src, dst = args
    with tempfile.TemporaryDirectory() as w:
        tmp = Path(w) / "out.pdf"
        for so in V.glob("lib*.so"):  # caj2pdf 从当前目录 ./ 加载 JBIG 解码库 (libjbigdec.so 已在 vendor 编译)
            shutil.copy(so, w)
        env = dict(os.environ, PATH=f"{V}/bin:" + os.environ["PATH"])
        try:
            r = subprocess.run([str(V / ".venv/bin/python"), str(V / "caj2pdf"), "convert", src, "-o", str(tmp)],
                               cwd=w, env=env, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            return src, "", "timeout"
        if r.returncode or not tmp.exists():
            return src, "", (r.stderr or r.stdout)[-200:].replace("\n", " ")
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp, dst)
    return src, dst, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    cfg = litdb.corpus_cfg(a.corpus)
    lst = pd.read_csv(Path(cfg["db"]).parent / "discovery" / "cnki_需转换.tsv", sep="\t")
    out_dir = Path(cfg["backup"]) / "知网转换"
    seen, jobs, used = set(), [], set()
    for p in lst.path:
        if not p.lower().endswith(".caj") or not Path(p).exists():
            continue
        h = sha1(p)
        if h in seen:
            continue
        seen.add(h)
        name = Path(p).stem + ".pdf"
        k = 2
        while name.lower() in used:
            name = f"{Path(p).stem}__{k}.pdf"
            k += 1
        used.add(name.lower())
        dst = out_dir / name
        if not dst.exists():
            jobs.append((p, str(dst)))
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(convert, jobs))
    ok = [r for r in res if r[1]]
    bad = [r for r in res if not r[1]]
    pd.DataFrame(res, columns=["src", "pdf", "error"]).to_csv(out_dir / "转换记录.tsv", sep="\t", index=False)
    summary("17_cnki", [f"CAJ {int(lst.path.str.lower().str.endswith('.caj').sum())} 个, 去重后待转 {len(jobs)} 个",
                        f"成功 {len(ok)}, 失败 {len(bad)} -> {out_dir} (转换记录.tsv)",
                        "下一步: 16_refresh --drives n (新 PDF 打分) -> 分拣 -> 05_ingest"])


if __name__ == "__main__":
    main()
