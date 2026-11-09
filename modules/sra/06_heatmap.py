"""06 热图: samples.tsv -> 类群 × 数据类型热图 (SVG) + 矩阵 TSV. 调用 vendor/organise_sra 的 heatmap 步骤 (无需 pip 安装).

用法: python3 yzz.py sra 06 <Taxon> [--level genus|species|family] [--family X] [--unit samples|runs|Gb] [--cmap magma] ...
输入: projects/<Taxon>/02_原始数据/sra/samples.tsv (04 table)
输出: 同目录 heatmap_<level>.tsv; projects/<Taxon>/04_处理数据/sra/<Taxon>_SRA_heatmap_<level>_<date>.svg
参数说明: organise-sra heatmap -h / vendor/organise_sra/README.md "热图" 一节.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "vendor" / "organise_sra" / "src"))
from common import data_dir, report_dir  # noqa: E402
from organise_sra import heatmap  # noqa: E402


def main(argv):
    if not argv or argv[0].startswith("-"):
        raise SystemExit(__doc__)
    taxon, rest = argv[0], argv[1:]
    opts = [] if "-o" in rest or "--outdir" in rest else ["-o", str(data_dir(taxon, "sra"))]
    if "--report-dir" not in rest:
        opts += ["--report-dir", str(report_dir(taxon, "sra"))]
    return heatmap.main([taxon, *opts, *rest])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
