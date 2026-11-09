# molheat — 分子数据分布热图 (类群 × 数据类型)

仿 Yang et al. (2024) 沙蚕科图 3：行 = 属（或某属的种），列 = coi cox2 cox3 cob 12s 16s 18s 28s its h3 | mt | lcWGS RNA Genome。

| 步骤 | 文件 | 作用 |
|---|---|---|
| 01 | `01_count.py` | GenBank 记录 + SRA 样本 + NCBI Assembly → 计数矩阵 TSV |
| 02 | `02_plot.py` | 矩阵 → 热图 (Python/matplotlib) |
| R | `molheat.R` | 同一矩阵 → 热图 (R/ggplot2)，参数与 02 相同 |
| — | `taxname.py` + `name_style.json` | 学名排版规则（两种脚本共用） |

## 计数规则（默认，均可改）
- 名称：NCBI 提交名原样（默认）；`--names worms` 可选改为 WoRMS 有效名。
- `--pool-informal sp`：`Marphysa sp. E HA-2019` 等并入 `Marphysa sp.`；cf./aff. 保留为 `M. cf. hentscheli`（去掉非正式编号）；`all` 连 cf./aff. 也并入；`none` 每个 NCBI 名一行。
- 科级名、environmental sample、无属名 → `<科> und.`。
- GenBank：按记录计；一条线粒体基因组同时计入 mt 和 coi/cox2/cox3/cob/12s/16s（`--mt-expand none` 关闭）。
- lcWGS（**列名暂定，用户 2026-11-08 定**）：低覆盖度短读长全基因组测序 = organise-sra 的 shallow_WGS（Illumina，每样本 0.5–10 Gb），用于建树（线粒体基因组、rDNA、BUSCO/UCE），不是重测序。基因组项目的 deep_WGS、长读长、Hi-C 不计入，以免与 Genome 列重复。RNA = RNA-Seq；单位 = BioSample（`--sra-unit runs|Gb`）。
  - 术语备注：genome skimming（Straub et al. 2012；Dodsworth 2015）是这类数据在系统学中的标准叫法；lcWGS 在文献中多指有参考基因组的群体基因组学（Lou et al. 2021）。用 lcWGS 时图注须写明"用于系统发育"。引文为记忆，投稿前核对。
  - 图注模板：lcWGS, low-coverage whole-genome sequencing (genome skimming; Illumina, 0.5–10 Gb per sample)；RNA, transcriptome；Genome, NCBI Assembly（含其深度短读长、长读长、Hi-C 原始数据）。
- Genome：NCBI Assembly，`<科>[Organism:exp] AND latest[filter]`，每个组装计 1；明细写入 `<out>_genomes.tsv`。
- `<out>_names.tsv`：每个原始名 → 归入哪一行、来源、条数（核对用）。

## 学名排版（name_style.json）
属、亚属、种/亚种加词、缩写属名 `M.` 斜体；科及以上 (`-idae -inae -oidea`、目名表)、`sp. spp. cf. aff. var. und.` 等限定词、`sp.` 之后的非正式编号、含数字/全大写/冒号的编号、命名人和年代 → 正体。
`--italic all|none` 整体斜体/正体；`python3 taxname.py "名称"` 与 `Rscript molheat.R --print-labels "名称"` 输出应一致（tests 检查）。

## 用法
```bash
cd /mnt/p/yzz-分类工作流/modules/molheat
python3 01_count.py Eunicidae --genbank Records.xlsx --sra samples.tsv --level genus --out out/Eunicidae_genus
python3 01_count.py Eunicidae --genbank Records.xlsx --sra samples.tsv --level species --genus Marphysa --out out/Marphysa_species
ARGS="--matrix out/Eunicidae_genus.tsv --matrix out/Marphysa_species.tsv --label Eunicidae --label Marphysa \
      --cmap viridis --cmap magma --vmax 200 --vmax 20 --abbreviate-genus no --abbreviate-genus yes --highlight Marphysa"
python3 02_plot.py $ARGS --out out/heatmap_py
Rscript molheat.R $ARGS --out out/heatmap_R          # R: ggplot2 + jsonlite (ragg 可选); 本机 /root/miniconda3/envs/rmap/bin/Rscript
```
默认输入（不给 --genbank/--sra）：`projects/<Taxon>/04_处理数据/genbank/<Taxon>_GenBank_markers_*.xlsx` 与 `projects/<Taxon>/02_原始数据/sra/samples.tsv`。

作图参数（两种脚本相同；每个 --matrix 一组的参数可重复）：`--cmap`（色板名或 `#fff,#000` 列表）`--vmax auto|N`（上限，色标顶端标 >N）`--log` `--values yes|no` `--zero cross|blank|grey|zero` `--gaps mt,WGS` `--columns` `--rows input|alpha|total` `--font` `--font-size` `--value-size` `--weight` `--italic auto|all|none` `--col-italic` `--abbreviate-genus` `--side-bar` `--colorbar` `--cell 宽,高(英寸)` `--highlight 行名` `--highlight-color` `--formats pdf,png,svg` `--dpi`。
PDF 文字可编辑（Python fonttype 42；R cairo_pdf）。WSL 下 Windows 字体（Arial）由 02_plot.py 经 fc-list 自动注册。
