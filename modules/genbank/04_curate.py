"""04 校正: NCBI 矩阵 (Excel A) + 你自己的表 (Excel B) -> 校正后的新矩阵 (Excel C). (g2t.curate)

Excel B = 你自己整理的任意 Excel/csv, 列名随意 (中英文均可), 放在 02_原始数据/genbank/curation/,
或用 --table 指定. 自动识别: 标本号/voucher/凭证号 -> 定位标本; 任何登录号列 (COI登录号, 28S accession ...)
-> 定位标本; 生物种拉丁名/species -> organism; 纬度+经度 (十进制) -> lat_lon (GenBank 格式 "66.55 N 33.10 E");
采集日期 (20190612, 2019-06-12) -> 12-Jun-2019; 论文题目/作者/期刊 -> Ref1Title/Ref1Authors/Ref1Journal;
其余列作为新列 "user:<列名>" 加到矩阵. 识别错了用 --map "列名=字段" 指定.
Excel C 工作表: Matrix (改过的单元格标黄) / Changes / Problems / Column mapping / Matrix (GenBank)

另一种方式 (g2t 模板):

NCBI 上的元数据 (经纬度、物种名、地点、采集日期、出版物 ...) 常常没有随论文更新. 校正表每行一条修改,
按 accession (任一基因列的登录号, 版本号可省) 和/或 voucher (任何写法, 可加 organism_match 限定物种) 定位标本;
空单元格表示不改. 匹配不到、匹配到多行、accession 与 voucher 指向不同行的修改不应用, 列在 Problems 表.
模板另有工作表 "baseline (do not edit)" 保存生成时的值: 只有你改过的单元格才算修改, 没改的单元格不会把
GenBank 之后更新的值改回去; 你改过而 GenBank 也已变化的单元格列为冲突, 不应用.

校正表位置: 02_原始数据/genbank/curation/<tag>_corrections.xlsx (也可 .csv)
  不存在时: 按当前矩阵生成模板 (每个标本一行, 已填当前值), 改好单元格后重跑本步骤.
输出: 04_处理数据/genbank/<Taxon>_GenBank_<tag>_curated_<date>.xlsx
  工作表: Matrix (curated) / Curation log (原值 -> 新值, 匹配依据) / Problems / Matrix (GenBank)
用法: python3 yzz.py genbank 04 <Taxon> [--tag markers] [--table B.xlsx] [--sheet 0] [--map "列名=字段"]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from common import TODAY, data_dir, read_tsv, report_dir, summary
from excel import YELLOW, write_workbook

try:
    from g2t.curate import (apply_updates, apply_user_table, is_template, make_template, parse_map,
                            read_corrections, write_template)
    from g2t.curate import _read as read_table
except ImportError:
    raise SystemExit("未安装 g2t: pip install -e /mnt/n/yzz-分类工作流/vendor/gb2taxonomy")


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    p.add_argument("--tag", default="")
    p.add_argument("--table", help="你自己的 Excel B (默认: curation/ 下除模板外的 .xlsx/.csv)")
    p.add_argument("--sheet", default="0", help="Excel B 的工作表 (名称或从 0 起的序号)")
    p.add_argument("--map", action="append", metavar="列名=字段", help="强制指定列, 如 --map '编号=voucher'")
    a, _ = p.parse_known_args(argv)
    cmap = parse_map(a.map)
    sheet = int(a.sheet) if str(a.sheet).isdigit() else a.sheet
    root = data_dir(a.taxon, "genbank")
    tags = [a.tag] if a.tag else sorted(f.stem[len("matrix_"):] for f in root.glob("matrix_*.tsv"))
    if not tags:
        raise SystemExit("没有矩阵: 先运行 genbank 03")
    cur = root / "curation"
    cur.mkdir(exist_ok=True)
    lines = []
    for tag in tags:
        mat = read_tsv(root / f"matrix_{tag}.tsv")
        genes = [c for c in mat.columns if c not in ("specimen_key", "organism", "voucher_standardized",
                                                       "voucher_as_submitted", "voucher_note", "n_genes")
                 and mat[c].astype(str).str.contains(r"^[A-Z]{1,6}_?\d{5,}\.\d", regex=True).any()]
        own = [Path(a.table)] if a.table else sorted(
            f for f in cur.iterdir() if f.suffix.lower() in (".xlsx", ".csv") and not f.name.startswith("~$")
            and not f.stem.endswith("_corrections") and not f.name.endswith(".baseline.csv"))
        tmpl = next((f for f in (cur / f"{tag}_corrections.xlsx", cur / f"{tag}_corrections.csv") if f.exists()), None)
        jobs = [(f, "table") for f in own if not is_template(str(f))] + [(f, "template") for f in own if is_template(str(f))]
        if tmpl is not None:
            jobs.append((tmpl, "template"))
        if not jobs:
            t = make_template(mat, gene_columns=genes)
            path = cur / f"{tag}_corrections.xlsx"
            write_template(t, str(path))          # sheet 'corrections' + a baseline copy (do not edit)
            lines.append(f"{tag}: curation/ 下没有你的表 -> 可直接把自己的 Excel 放进 {cur}，"
                         f"或填写已生成的模板 {path}（{len(t)} 个标本）；然后重跑 genbank 04")
            continue
        for src, kind in jobs:
            mapping = None
            if kind == "table":
                out, log, problems, mapping = apply_user_table(mat, read_table(str(src), sheet), key_column="specimen_key",
                                                               gene_columns=genes, column_map=cmap)
            else:
                upd, base = read_corrections(str(src))
                out, log, problems = apply_updates(mat, upd, gene_columns=genes, key_column="specimen_key",
                                                   baseline=base)
            if kind == "template" and log.empty and problems.empty:
                lines.append(f"{tag}: 模板 {src.name} 未修改，跳过")
                continue
            sheets = {"Matrix": out, "Changes": log, "Problems": problems}
            if mapping is not None:
                sheets["Column mapping"] = mapping
            sheets["Matrix (GenBank)"] = mat
            xlsx = report_dir(a.taxon, "genbank") / f"{a.taxon}_GenBank_{tag}_curated_{src.stem}_{TODAY}.xlsx"
            xlsx = write_workbook(xlsx, sheets, freeze={"Matrix": "C2", "Matrix (GenBank)": "C2"},
                                  shade={"Matrix": [("curated_fields", lambda v: bool(v), YELLOW)]})
            lines.append(f"{tag}: {src.name} -> {len(log)} 处修改（{log['specimen'].nunique() if len(log) else 0} 个标本），"
                         f"问题 {len(problems)}；Excel C: {xlsx}")
            if mapping is not None:
                lines.append("  列识别: " + "; ".join(f"{r.user_column}->{r.used_as}" for r in mapping.itertuples()))
    summary("04_curate", lines)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
