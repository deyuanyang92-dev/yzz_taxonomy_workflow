"""yzz 工作流共享工具: 路径约定、项目模板、TSV 读写、文本/数值清洗.

路径约定 (所有模块统一):
  ROOT/projects/<Taxon>/                   项目目录 (00-10 编号模板, 同臭海蛹项目)
  ROOT/projects/<Taxon>/02_原始数据/<module>/  模块抓取/计算得到的 TSV (数据本体, 机器读写)
  ROOT/projects/<Taxon>/04_处理数据/<module>/  Excel 报表 (给人看的视图)
  ROOT/cache/                              跨项目共享缓存 (HTTP、地名标准化等)

外部项目 (用户自己的项目文件夹, 如 P:\岩虫属系统修订): 类群登记在 config/projects.json
({"Marphysa": "/mnt/p/岩虫属系统修订", ...}; python3 yzz.py project <Taxon> <目录> 登记),
或临时用 --project <目录> / 环境变量 YZZ_PROJECT_DIR. 登记后直接输出到该文件夹, 不写 ROOT/projects:
  <目录>/02_原始数据/<module>/<Taxon>/   数据 TSV        <目录>/04_处理数据/<module>/<Taxon>/  Excel 报表
  分子模块 (genbank, sra, molheat, phylogeny): 数据和报表都在 <目录>/10_分子数据/<module>/<Taxon>/
  maps 等用 project(taxon) 的模块: <目录>/05_图表/...
"""
import datetime
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache"
PROJECTS = ROOT / "projects"
TODAY = datetime.date.today().isoformat()

PROJECT_TEMPLATE = ["01_文献", "02_原始数据", "03_脚本", "04_处理数据", "05_图表", "06_稿件",
                    "07_审稿记录", "08_知识库", "09_文本抽取", "10_分子数据"]


MOLECULAR = {"genbank", "sra", "molheat", "phylogeny"}
REGISTRY = ROOT / "config" / "projects.json"


def external_project(taxon):
    """用户项目文件夹 (Path) 或 None: --project / YZZ_PROJECT_DIR 优先, 其次 config/projects.json."""
    import json
    import os
    env = os.environ.get("YZZ_PROJECT_DIR")
    if env:
        return Path(env)
    if REGISTRY.exists():
        d = json.loads(REGISTRY.read_text(encoding="utf-8")).get(taxon)
        if d:
            return Path(d)
    return None


def register_project(taxon, directory):
    import json
    reg = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {}
    reg[taxon] = str(Path(directory).resolve())
    REGISTRY.parent.mkdir(exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    return reg[taxon]


def project(taxon):
    """返回项目目录: 已登记的外部项目文件夹, 否则 ROOT/projects/<Taxon> (不存在则按模板创建)."""
    ext = external_project(taxon)
    if ext is not None:
        ext.mkdir(parents=True, exist_ok=True)
        CACHE.mkdir(exist_ok=True)
        return ext
    p = PROJECTS / taxon
    if not p.exists():
        for d in PROJECT_TEMPLATE:
            (p / d).mkdir(parents=True, exist_ok=True)
        (p / "00_README.md").write_text(
            f"# {taxon}\n\n创建: {TODAY}\n\n"
            "| 目录 | 内容 |\n|---|---|\n"
            "| 01_文献 | PDF (只读) |\n| 02_原始数据 | 抓取的原始数据; `worms/` = WoRMS TSV |\n"
            "| 03_脚本 | 本项目专用脚本 (通用脚本在 yzz 工作流 modules/) |\n"
            "| 04_处理数据 | 报表; `worms/` = WoRMS Excel |\n| 05_图表 | 图及作图源数据 |\n"
            "| 06_稿件 | 稿件 |\n| 07_审稿记录 | 审稿 |\n| 08_知识库 | 性状库等 |\n"
            "| 09_文本抽取 | 文献全文抽取 |\n| 10_分子数据 | 序列/树 |\n", encoding="utf-8")
    CACHE.mkdir(exist_ok=True)
    return p


def _module_dir(taxon, module, area):
    if external_project(taxon) is not None:
        d = project(taxon) / ("10_分子数据" if module in MOLECULAR else area) / module / taxon
    else:
        d = project(taxon) / area / module
    d.mkdir(parents=True, exist_ok=True)
    return d


def worms_root(taxon):
    """oworms 输出根目录 <项目>/02_原始数据/worms/<Taxon> (oworms 原生结构: data/*.tsv, reports/*.xlsx, 不改动).
    2026-11-09 起 yzz 的 WoRMS 部分由 oworms (github.com/deyuanyang92-dev/oworms) 完成, yzz 只调用."""
    d = project(taxon) / "02_原始数据" / "worms" / taxon
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_dir(taxon, module):
    if module == "worms":
        return worms_root(taxon) / "data"
    return _module_dir(taxon, module, "02_原始数据")


def report_dir(taxon, module):
    if module == "worms":
        return worms_root(taxon) / "reports"
    return _module_dir(taxon, module, "04_处理数据")


def read_tsv(path, required=True):
    import pandas as pd  # 延迟导入: sra 等纯标准库模块只用本文件的路径工具
    path = Path(path)
    # 空文件(如 06_specimens 在类群无标本时写出的空 TSV)与缺失同等处理, 否则 pandas 抛 EmptyDataError
    if not path.exists() or not path.read_text(encoding="utf-8", errors="ignore").strip():
        if required:
            raise SystemExit(f"缺少输入 {path.name}: 请先运行生成它的步骤")
        return pd.DataFrame()
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)


def write_tsv(df, path):
    df.to_csv(path, sep="\t", index=False)
    return path


def clean(x):
    """去 HTML 标签、合并空白; None/NaN/'None' -> ''."""
    if x is None or (isinstance(x, float) and x != x) or str(x) in ("None", "nan", "<NA>"):
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(x))).strip()


def uniq(xs):
    out = []
    for x in xs:
        x = clean(x)
        if x and x not in out:
            out.append(x)
    return out


def num(s):
    """'13.872 (13° 52' 19\" N)' -> 13.872 ; '4 498 m' -> 4498.0 ; 无数字 -> None"""
    m = re.match(r"\s*(-?\d[\d ]*(?:[.,]\d+)?)", str(s or ""))
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def year_of(authority):
    m = re.findall(r"(1[5-9]\d\d|20\d\d)", str(authority))
    return m[-1] if m else ""


DEPTH_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:[-–]|to)?\s*(\d+(?:[.,]\d+)?)?\s*(m|meters|metres|fathoms?|fms?)\b", re.I)


def parse_depth(text):
    """文本中第一个水深 -> (min_m, max_m, 原文片段); 英寻换算为米."""
    m = DEPTH_RE.search(text or "")
    if not m:
        return "", "", ""
    f = 1.8288 if m.group(3).lower().startswith("f") else 1.0
    lo = float(m.group(1).replace(",", ".")) * f
    hi = float(m.group(2).replace(",", ".")) * f if m.group(2) else lo
    return f"{min(lo, hi):g}", f"{max(lo, hi):g}", m.group(0)


def summary(step, lines):
    """每个步骤结束时打印的简短摘要 (≤5 行)."""
    print(f"[{step}] " + lines[0])
    for x in lines[1:5]:
        print("   " + x)
