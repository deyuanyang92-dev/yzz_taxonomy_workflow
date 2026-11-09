"""compilation 模块共用配置: 项目根目录 + <项目>/08_知识库/compilation.json.

项目根目录: 命令行第 1 个参数 (目录) > 环境变量 YZZ_PROJECT > 当前目录.
compilation.json 例:
  {"genus": "Marphysa",
   "table": "01_文献/Marphysa_物种文献_PDF_2026-11-08.xlsx",     # yzz worms 16 物种×文献 + PDF 对应 (sheet 物种×文献 / 文献清单)
   "pdf_dir": "01_文献/01_描述文献",
   "kb": "08_知识库/Marphysa_KB.sqlite",
   "genera_italic": ["Marphysa", "Paucibranchia", "Eunice", "Nicidion", "Treadwellphysa"],
   "worms_names": "/mnt/p/yzz-分类工作流/projects/Marphysa/02_原始数据/worms/names.tsv",
   "library_db": "/root/yzz-literature/polychaeta.db"}
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _root():
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir():
        return Path(sys.argv[1]).resolve(), sys.argv[2:]
    return Path(os.environ.get("YZZ_PROJECT") or Path.cwd()).resolve(), sys.argv[1:]


ROOT, ARGS = _root()
os.environ["YZZ_PROJECT"] = str(ROOT)
_cf = ROOT / "08_知识库" / "compilation.json"
if not _cf.exists():
    sys.exit(f"缺 {_cf} (见 cfg.py 说明)")
C = json.loads(_cf.read_text(encoding="utf-8"))
GENUS = C["genus"]
KB = ROOT / C.get("kb", f"08_知识库/{GENUS}_KB.sqlite")
TAB = ROOT / C["table"]
PDFDIR = ROOT / C.get("pdf_dir", "01_文献/01_描述文献")
S = ROOT / "08_知识库" / "结构化"
OUTDIR = ROOT / "11_物种图文汇编"
LIB = C.get("library_db", "/root/yzz-literature/polychaeta.db")
GENERA = set(C.get("genera_italic", [GENUS]))
WORMS_NAMES = C.get("worms_names", "")
# Windows 盘符路径前缀 (PDF 内本地链接用): /mnt/p/X -> P:/X
WIN = (lambda s: (s[5].upper() + ":" + s[6:]) if s.startswith("/mnt/") and len(s) > 6 else s)(str(ROOT)) + "/"
