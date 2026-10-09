"""02 g2t: 用 gb2taxonomy (g2t, vendor/gb2taxonomy) 处理 01 下载的 .gb:
提取元数据 -> 识别基因类型 -> 标本凭证号 -> 凭证号核对 (3b, 按证据合并写法不同的同一标本) -> 标本 × 基因矩阵.

输入: 02_原始数据/genbank/gb/<tag>/*.gb
输出: 02_原始数据/genbank/g2t/<tag>/ (g2t 原样输出, 不改)
用法: python3 yzz.py genbank 02 <Taxon> [--tag markers] [--min-confidence high|medium] [--no-reconcile]   (不给 --tag 则处理全部已下载的 tag)
"""
import argparse
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from common import data_dir, summary

try:
    import g2t
except ImportError:
    raise SystemExit("未安装 g2t: pip install -e /mnt/n/yzz-分类工作流/vendor/gb2taxonomy")


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    p.add_argument("--tag", default="")
    p.add_argument("--min-confidence", choices=["high", "medium"], default="medium",
                   help="凭证号核对合并所需证据强度 (high = 只按同一论文/日期/坐标合并)")
    p.add_argument("--no-reconcile", action="store_true")
    a, _ = p.parse_known_args(argv)
    root = data_dir(a.taxon, "genbank")
    tags = [a.tag] if a.tag else sorted(d.name for d in (root / "gb").iterdir() if d.is_dir() and any(d.glob("*.gb")))
    if not tags:
        raise SystemExit("没有已下载的 .gb: 先运行 genbank 01")
    lines = []
    for tag in tags:
        out = root / "g2t" / tag
        out.mkdir(parents=True, exist_ok=True)
        log = io.StringIO()
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            import logging
            logging.disable(logging.INFO)
            r = g2t.run(input_files=[str(root / "gb" / tag)], output_dir=str(out), stream=True,
                        skip_reconcile=a.no_reconcile, reconcile_min_confidence=a.min_confidence)
            logging.disable(logging.NOTSET)
        (out / "g2t_log.txt").write_text(log.getvalue() + "\n" + "\n".join(r.log), encoding="utf-8")
        ok = Path(r.final_output or "").exists()
        lines.append(f"{tag}: {'OK' if ok else 'FAILED'} — " + "; ".join(x.split(":")[0] + x[x.rfind("("):] for x in r.log))
    summary("02_g2t", lines + [f"输出: {root / 'g2t'}"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
