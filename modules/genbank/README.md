# genbank 模块

从 NCBI nuccore 下载一个类群的 GenBank 记录，用 g2t（gb2taxonomy，`vendor/gb2taxonomy`，GitHub deyuanyang92-dev/gb2taxonomy）整理为"标本 × 基因"多基因表。需求见 [REQUIREMENTS.md](REQUIREMENTS.md)。

```bash
python3 yzz.py genbank all Priapulidae                       # 默认: 标记基因集 (下载 → g2t → Excel/FASTA)
python3 yzz.py genbank 01 Priapulidae --dry-run              # 只看检索式与各基因条数, 不下载
python3 yzz.py genbank all Priapulidae --mito                # 只要线粒体记录
python3 yzz.py genbank all Priapulidae --mitogenome          # 只要完整线粒体基因组 (10–30 kb)
python3 yzz.py genbank all Priapulidae --gene COI,18S,28S    # 指定基因 (见 vendor/gb2taxonomy/src/g2t/ncbi_genes.py)
python3 yzz.py genbank all Priapulidae --gene COI --minlen 500
python3 yzz.py genbank all Priapulidae --query 'Russia[Country]'   # 追加任意 Entrez 子句
python3 yzz.py genbank all Priapulidae --all                 # 全部 (含 WGS/mRNA/RefSeq, 可能极大)
```

| 步骤 | 输入 → 输出 | 说明 |
|---|---|---|
| 01_download | 调用 `g2t.download`；类群名 → `02_原始数据/genbank/gb/<tag>/batch_NNNN.gb` + `accessions.tsv` + `manifest.json` | 检索式、类群构成 (WGS/mRNA/RefSeq/线粒体) 与按基因条数写入 manifest；默认跳过 >100 kb 记录（`--include-large`）；记录按 accession.version 存共享库 `cache/genbank/nuccore_records.sqlite`，只下载库中没有的（重跑、换选择、重叠类群都复用，旧批文件自动导入）；`gb/<tag>/changes.tsv` / `changes_history.tsv` 记录新增/更新/撤下；并行 `-w 3`，校验条数，指数退避重试 |
| 02_g2t | gb/<tag> → `g2t/<tag>/`（g2t 原样输出） | 提取元数据 → 基因类型 → 凭证号 → **凭证号核对 (3b)** → 矩阵；`--min-confidence high` 只按强证据合并，`--no-reconcile` 关闭 |
| 03_export | g2t/<tag> → `04_处理数据/genbank/<Taxon>_GenBank_<tag>_<date>.xlsx`；`02_原始数据/genbank/fasta/<tag>/<gene>.fasta` | 只读 g2t 结果；导出 Matrix / Species x gene / Records / Voucher reconciliation / Not classified / QC / Query |

| 04_curate | Excel A（`matrix_<tag>.tsv`）+ 你自己的 Excel B（放 `02_原始数据/genbank/curation/` 或 `--table`）→ Excel C `04_处理数据/genbank/<Taxon>_GenBank_<tag>_curated_<B名>_<date>.xlsx` | g2t.curate：B 列名随意（中英文），自动识别标本号/登录号/拉丁名/纬度+经度/采集日期/题目等，`--map "列名=字段"` 强制；其余列加为 `user:<列名>`；工作表 Matrix（修改标黄）/ Changes / Problems / Column mapping / Matrix (GenBank)；也支持 g2t 预填模板（未修改则跳过） |

**统一凭证号**：Matrix 中 `voucher_as_submitted` = GenBank 原样（全部写法），`voucher_standardized` = 统一后的唯一凭证号（去 COI_/28S_ 等前缀、`:`/空格 → `_`、取最完整写法），`voucher_note` 非空时需人工核对。

**tag**：每种检索选择一个子目录（`markers`、`mito`、`mitogenome`、`gene-COI_18S`、`len500-max`、`custom` 或 `--tag` 自定义），同一项目可并存；02/03 不给 `--tag` 时处理全部 tag。

**默认排除**（`--include-wgs / --include-mrna / --include-refseq` 可放开）：WGS contig、mRNA、RefSeq（预测模型 XM_/XR_ 及 NC_ 等与 INSDC 重复的拷贝）。例：Priapulidae 共 95,726 条，其中 WGS 69,704、mRNA 23,053；标记基因集仅 548 条。

**凭证号核对（g2t 步骤 3b，全自动）**：同一标本不同基因的凭证号写法常不同（`COI_ZMMU_MSU_WS399` / `28S_ZMMU_WS399` / `WS399`）。候选 = 同一物种 + 核心编号相同；**按记录中的证据判定**：强证据（同一论文、同采集日期、坐标 ≤0.01°）→ 合并 high；中等证据 ≥2（同第一作者/采集人/详细地点、坐标 ≤0.5°）→ 合并 medium；有矛盾（日期/国家/坐标不符）或证据不足 → 不合并。跨物种同号只报告。每对候选的证据与判定见 Excel 的 Voucher reconciliation 表；未合并的进 QC。Matrix 中 medium 行黄底，可抽查。Priapulidae 实测：130 对候选全部有"同一论文"强证据 → 94 个标本合并（high）；WS3020 跨物种（*H. spinulosus* 28S vs *P. caudatus* COI/16S）未合并。

**NCBI 身份**（可选）：`config/ncbi.json`（参照 `config/ncbi.example.json`）或环境变量 `NCBI_EMAIL` / `NCBI_API_KEY`。有 api_key 时 10 次/秒。

**g2t 已知行为**：<150 bp 等未归入 13 类标记基因的记录被静默丢弃 → 03 的 Not classified 表补齐列出；g2t 有未匹配序列时可能返回非零退出码（见 vendor/gb2taxonomy/BUGS.md）。新增基因类型：编辑 `vendor/gb2taxonomy/src/g2t/data/gene_dict.yaml`（g2t 分类用）与 `vendor/gb2taxonomy/src/g2t/ncbi_genes.py`（下载检索用）。改 g2t 后跑 `python3 -m pytest -q`（vendor/gb2taxonomy 下）并推送 GitHub。
