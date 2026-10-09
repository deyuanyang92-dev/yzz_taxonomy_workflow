"""01 下载: 类群 → NCBI nuccore GenBank 记录 (g2t.download).

用法:
  python3 yzz.py genbank 01 Polynoidae                 # 首次下载 (标记基因记录)
  python3 yzz.py genbank 01 Polynoidae --since auto    # 之后: 只取上次以来新增/修改的记录
  python3 yzz.py genbank 01 Polynoidae -n              # 只看各基因条数与检索式
选项同 g2t-download (-h). 记录库: cache/genbank/nuccore_records.sqlite (--store 换, --no-store 不用).
NCBI 身份: config/ncbi.json {"email": "...", "api_key": "..."} 或 NCBI_EMAIL / NCBI_API_KEY.
输出: 02_原始数据/genbank/gb/<tag>/ (batch_NNNN.gb, accessions.tsv, manifest.json, changes.tsv)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from common import ROOT, data_dir, summary

try:
    from g2t.download import add_selection_args, describe, download, options_from_args
except ImportError:
    raise SystemExit("未安装 g2t: pip install -e /mnt/n/yzz-分类工作流/vendor/gb2taxonomy")


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    add_selection_args(p)
    a, _ = p.parse_known_args(argv)
    cfg = {}
    f = ROOT / "config" / "ncbi.json"
    if f.exists():
        cfg = json.loads(f.read_text(encoding="utf-8"))
    res = download(a.taxon, str(data_dir(a.taxon, "genbank") / "gb"), options_from_args(a), dry_run=a.dry_run,
                   email=cfg.get("email") or None, api_key=cfg.get("api_key") or None,
                   progress=not a.quiet, report=a.report,
                   store=a.store or str(ROOT / "cache" / "genbank" / "nuccore_records.sqlite"))
    lines = describe(res, a.dry_run)
    if res.failed:
        lines[-1] += "  (失败批次: 重跑同一命令即可续传)"
    summary("01_download", lines)
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
