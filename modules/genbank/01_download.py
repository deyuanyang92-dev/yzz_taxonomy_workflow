"""01 下载: 按类群从 NCBI nuccore 下载 GenBank (.gb) 记录 (调用 g2t.download, 代码在 vendor/gb2taxonomy).

默认只下"标记基因"集合: 排除 WGS contig、mRNA、RefSeq (预测模型及 NC_ 等与 INSDC 重复的拷贝).
按 accession 分批下载, 每批校验条数, 失败指数退避重试, 重跑同一命令即续传. 每种选择单独存 gb/<tag>/.

用法:
  python3 yzz.py genbank 01 Priapulidae --dry-run            # 只看类群构成、各基因条数与检索式
  python3 yzz.py genbank 01 Priapulidae                      # 默认 markers
  python3 yzz.py genbank 01 Priapulidae --mito               # 只要线粒体记录
  python3 yzz.py genbank 01 Priapulidae --mitogenome         # 只要完整线粒体基因组
  python3 yzz.py genbank 01 Priapulidae --gene COI,18S,28S   # 指定基因 (g2t/ncbi_genes.py)
  python3 yzz.py genbank 01 Priapulidae --all                # 全部记录 (含 WGS/mRNA/RefSeq, 可能极大)
  其他: --minlen N --maxlen N --query '<Entrez 子句>' --include-wgs --include-mrna --include-refseq --tag 名称 -b 200
NCBI 身份: config/ncbi.json {"email": "...", "api_key": "..."} 或环境变量 NCBI_EMAIL / NCBI_API_KEY (可选).
输出: 02_原始数据/genbank/gb/<tag>/batch_NNNN.gb, accessions.tsv, manifest.json
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
                   email=cfg.get("email") or None, api_key=cfg.get("api_key") or None)
    lines = describe(res, a.dry_run)
    if res.failed:
        lines[-1] += "  (失败批次: 重跑同一命令即可续传)"
    summary("01_download", lines)
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
