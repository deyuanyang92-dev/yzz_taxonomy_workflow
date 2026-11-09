"""literature 模块共享: 文献库配置、SQLite schema、页面文本质量判断.

文献库 (corpus) 不属于某个类群项目, 而是一个跨项目的全文库:
  config/literature.json  {"<corpus>": {"source": 文献目录(只读), "db": SQLite 路径, "backup": 备份目录}}
  未配置时用 DEFAULTS.
SQLite 放 Linux 盘 (WSL 下 /mnt/* 上 SQLite 锁不可靠且慢), 步骤结束时备份到 backup.
"""
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

DEFAULTS = {
    "polychaeta": {
        "source": "/mnt/n/多毛类分类文献-薛整理-杨接力",
        "db": "/root/yzz-literature/polychaeta.db",
        "backup": "/mnt/n/多毛类文献库",
    }
}

MIN_TEXT_CHARS = 80  # 页面文字层少于此字符数 -> 需要 OCR

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
    doc_id     INTEGER PRIMARY KEY,
    relpath    TEXT UNIQUE NOT NULL,   -- 相对 source 的路径
    folder     TEXT,                   -- 一级目录 (Taxonomy / Sipuncula References ...)
    author_dir TEXT,                   -- Taxonomy/<作者> 目录名
    kind       TEXT,                   -- pdf / docx
    size       INTEGER,
    mtime      REAL,
    n_pages    INTEGER,
    n_text     INTEGER,                -- 有文字层的页数
    n_ocr      INTEGER,                -- 需要 OCR 的页数
    status     TEXT,                   -- ok / error
    error      TEXT,
    pdf_meta   TEXT                    -- PDF 自带 metadata (JSON)
);
CREATE TABLE IF NOT EXISTS pages (
    doc_id   INTEGER NOT NULL,
    page_no  INTEGER NOT NULL,          -- 1 起
    source   TEXT NOT NULL,             -- pdf / ocr / pending (待 OCR) / docx
    chars    INTEGER,
    quality  REAL,                      -- 像单词的 token 占比 (0-1), 低 = 乱码文字层
    ocr_conf REAL,                      -- tesseract 平均置信度 (仅 ocr)
    ocr_lang TEXT,
    text     TEXT,
    PRIMARY KEY (doc_id, page_no)
);
CREATE INDEX IF NOT EXISTS pages_source ON pages(source);
"""


def corpus_cfg(name):
    p = ROOT / "config" / "literature.json"
    cfg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else DEFAULTS
    if name not in cfg:
        raise SystemExit(f"未知文献库 {name}; 可用: {', '.join(cfg)} (config/literature.json)")
    return cfg[name]


def connect(name):
    db = Path(corpus_cfg(name)["db"])
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db, timeout=60)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


def backup(name):
    """在线备份 SQLite 到 backup 目录 (sqlite backup API, 运行中也安全)."""
    cfg = corpus_cfg(name)
    dst_dir = Path(cfg["backup"])
    dst_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(cfg["db"]).with_suffix(".backup.tmp")
    src = sqlite3.connect(cfg["db"])
    out = sqlite3.connect(tmp)
    src.backup(out)
    out.close()
    src.close()
    dst = dst_dir / Path(cfg["db"]).name
    shutil.move(str(tmp), dst)
    return dst


_WORD = re.compile(r"^[^\W\d_]{2,}$")


def quality(text):
    """像单词的 token 占比. 乱码文字层 (旧 OCR、字体映射错) 通常 < 0.5."""
    toks = [t.strip(".,;:()[]\"'!?-–—") for t in text.split()]
    toks = [t for t in toks if t]
    if not toks:
        return 0.0
    return round(sum(bool(_WORD.match(t)) for t in toks) / len(toks), 3)


_CJK_GAP = re.compile(r"(?<=[\u3040-\u30ff\u4e00-\u9fff\u3000-\u303f\uff01-\uff5e]) +(?=[\u3040-\u30ff\u4e00-\u9fff\u3000-\u303f\uff01-\uff5e])")


def cjk_join(text):
    """tesseract chi_sim/jpn 在每个汉字间插空格 ("溪 沙 蚕"), 中文 trigram 检索因此搜不到 "溪沙蚕" (2026-10-22 发现);
    写库前去掉 汉字/假名/全角标点 之间的空格."""
    return _CJK_GAP.sub("", text or "")
