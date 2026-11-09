"""01 底本名录: 把一篇经典名录 (seed catalogue) 解析成逐种表 -> seed.tsv

输入: projects/<Taxon>/02_原始数据/habitat/config.json 的 "seed" 段
      {"parser": "glasby2009", "pdf": "<完整 PDF 路径>", "citation": "...", "doi": "..."}
输出: 02_原始数据/habitat/seed.tsv (每条名录条目一行, 字段原样, 附页码)
解析器: modules/habitat/parsers/<parser>.py, 须提供 parse(text) -> list[dict], 每行含 glasby_name 等原文字段.
用法: python3 01_seed.py <Taxon>
"""
import importlib, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
sys.path.insert(0, str(HERE / "parsers"))
import pandas as pd
from common import data_dir, summary, write_tsv


def config(taxon):
    p = data_dir(taxon, "habitat") / "config.json"
    if not p.exists():
        raise SystemExit(f"缺少 {p}: 先写好 seed / habitat_map / seeds_doi 配置 (见 modules/habitat/README.md)")
    return json.loads(p.read_text(encoding="utf-8"))


def main(taxon):
    cfg = config(taxon)["seed"]
    out = data_dir(taxon, "habitat")
    txt = out / "seed_fulltext.txt"
    subprocess.run(["pdftotext", "-layout", cfg["pdf"], str(txt)], check=True)
    rows = importlib.import_module(cfg["parser"]).parse(txt.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df.insert(0, "seed_no", range(1, len(df) + 1))
    df["seed_source"] = cfg["citation"]
    write_tsv(df, out / "seed.tsv")
    expect = cfg.get("expected_entries")
    ok = "OK" if not expect or expect == len(df) else f"!! 期望 {expect}"
    summary("01_seed", [f"{len(df)} 条 ({ok}), {df['glasby_family'].nunique()} 科 -> seed.tsv"])


if __name__ == "__main__":
    main(sys.argv[1])
