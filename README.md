# yzz 分类学工作流

杨德援团队的本地科研工作流：分类学、系统发育。**脚本做事，Claude 调度；数据存表，结论有据。**

## 用法

```bash
python3 yzz.py list                       # 有哪些模块/步骤
python3 yzz.py init <Taxon>               # 新建项目目录
python3 yzz.py worms all <Taxon>          # 运行 worms 模块全部步骤
python3 yzz.py worms 06 <Taxon>           # 只跑某一步；07-09 跑一段
```

在 Claude Code 里直接说"整理 Polynoidae 的 WoRMS 数据"即可（skill `yzz-worms`）；"下载 Priapulidae 的 GenBank 并整理多基因表"（skill `yzz-genbank`）。

## 结构

```
yzz-分类工作流/
├── yzz.py              统一入口
├── CLAUDE.md           团队规则（Claude 必读）
├── lib/                共享代码：common.py（路径/TSV/清洗）、worms.py（WoRMS 访问+页面解析）、excel.py（报表格式）
├── modules/            一个科研任务一个模块；一个步骤一个脚本（NN_name.py），每个模块有 README + REQUIREMENTS
│   ├── worms/          ✅ 名称、文献、模式产地、标本（01–09）
│   ├── literature/     ⏳ 文献下载、全文抽取
│   ├── synonymy/       ⏳ 异名录
│   ├── characters/     ⏳ 性状比较表
│   ├── keys/           ⏳ 检索表
│   ├── maps/           ⏳ 分布图、模式产地图
│   ├── genbank/        ✅ NCBI 下载 → g2t → 多基因表 + FASTA（01–03）
│   └── phylogeny/      ⏳ 序列 → 矩阵 → 建树
├── projects/<Taxon>/   每个类群一个项目（00–10 编号模板，同臭海蛹项目）
│   ├── 02_原始数据/<module>/*.tsv   数据本体（机器读写）
│   └── 04_处理数据/<module>/*.xlsx  报表（给人看）
├── vendor/             第三方工具源码：gb2taxonomy (g2t)（独立仓库，不含在本仓库；见下方“安装”）
├── temp_scripts/       临时脚本（GitHub deyuanyang92-dev/Temp_scripts 的本地副本：MitoZ 注释、MitoFinder 批量、GetOrganelle、blast2metadata）；待逐步整合进 modules/
├── config/             本地配置（ncbi.json：NCBI 邮箱/API key，可选）
├── cache/              跨项目缓存（HTTP、名称记录、地名标准化）
├── docs/               设计文档、指南 PDF
└── archive/            旧脚本与旧输出（只归档不删除）
```

## 设计原则：模块边界

```
worms 模块        只提取 WoRMS 信息 + 必要格式转换（如地名→坐标）；WoRMS 没有的留空，不推断
literature 模块   从文献整理物种信息（模式产地、描述、性状…），每条带出处（文献、页码）
合并步骤（后续）  worms + literature → 物种信息总表：用文献补 WoRMS 缺失，每个值标明来源
```

一个模块不替另一个模块做事；新需求先判断属于哪个模块，再加到该模块的 REQUIREMENTS.md。

## 新增模块的约定

1. `modules/<name>/NN_step.py`：单一职责；`python3 NN_step.py <Taxon>`；只读上一步 TSV、只写自己的 TSV；结束时用 `common.summary()` 打印 ≤5 行。
2. 路径一律用 `common.data_dir(taxon, module)` / `report_dir(...)`，不硬编码。
3. 写 `README.md`（步骤表）和 `REQUIREMENTS.md`（需求 + 状态）。
4. 在 `~/.claude/skills/yzz-<name>/SKILL.md` 写 skill：何时用、跑哪条命令、怎么汇报。
5. 有可复用的老脚本（`/mnt/n/codex`、`/mnt/n/claude`、项目 `03_脚本`）先复用，不重写。

## 安装

```bash
git clone https://github.com/deyuanyang92-dev/yzz_taxonomy_workflow.git
cd yzz_taxonomy_workflow
git clone https://github.com/deyuanyang92-dev/gb2taxonomy.git vendor/gb2taxonomy
pip install -e vendor/gb2taxonomy
cp config/ncbi.example.json config/ncbi.json   # 可选：填 NCBI 邮箱 / API key（已被 .gitignore 忽略）
python3 yzz.py worms all <Taxon>
```

`cache/`、`projects/`、`outputs/`、`archive/` 为运行产物与历史数据，不入库；`temp_scripts/` 见 GitHub `deyuanyang92-dev/Temp_scripts`。
