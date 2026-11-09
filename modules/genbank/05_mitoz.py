"""05 MitoZ 重新注释: 调用 batch_mitoz.py run (temp_scripts/Mitoz-annotate, GitHub deyuanyang92-dev/Mitom),
把下载的线粒体记录全部用 MitoZ 重新注释, 统一 NCBI 注释不一致 / 注释缺失. 原始 .gb 不改.

输入: 02_原始数据/genbank/gb/<tag>/*.gb   (不给 --tag 时处理名为 mito* 的 tag: mito、mitogenome)
输出: 02_原始数据/genbank/mitoz/<tag>/    (batch_mitoz.py 原样输出, 见其 README.txt)
      final_annotation/<accession>.gb 每条记录 (cox1 打头, 原 NCBI 头部已恢复); final_annotation_all.gb; summary.tsv;
      original_vs_mitom.tsv (与原注释逐基因对照); ncbi_submission/; reports/ (旧版为 04.final_gb/, annotation-summary.tsv)
      内部 ID 中间文件 (00.*/01.*/03.*、id_map.tsv) 跑完即删; 问题样本的 MitoZ 日志留在 failed_logs/
用法: python3 yzz.py genbank 05 <Taxon> --conda_env_mitoz <env> [--tag mitogenome] [--clade ...] [--genetic_code 5]
      其余参数原样传给 batch_mitoz.py run (如 --threads 8 --max_tasks 4 --keep_intermediate yes)
      MitoZ 位置也可写 config/mitoz.json: {"conda_env_mitoz": "mitoz3.6"} 或 {"mitoz_path": "/path/to/mitoz"}
      未找到 MitoZ 时本步跳过 (exit 0), 不影响 genbank all.
intron: MitoZ 不注释 intron (MitoZ 缺陷). batch_mitoz.py 注释后自动调用 mito_intron.py
      (MFannot 方法的 Python 移植: Exonerate protein2genome + MFannot 边界规则 + Rfam 判型) 补上 intron,
      需要 exonerate/cmsearch: --intron_bin <conda env bin> 或 config/mitoz.json "intron_bin";
      结果 mitoz/<tag>/intron_report.tsv; 需人工核对.
"""
import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from common import ROOT, summary
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gbpaths import step_dir, write_readme  # noqa: E402

SCRIPT = ROOT / "temp_scripts" / "Mitoz-annotate" / "batch_mitoz.py"
CONFIG = ROOT / "config" / "mitoz.json"


def mitoz_location(a):
    """命令行 > config/mitoz.json > PATH 上的 mitoz > 自动扫描 conda 环境; 都没有返回 []."""
    if a.conda_env_mitoz:
        return ["--conda_env_mitoz", a.conda_env_mitoz]
    if a.mitoz_path:
        return ["--mitoz_path", a.mitoz_path]
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    if cfg.get("conda_env_mitoz"):
        return ["--conda_env_mitoz", cfg["conda_env_mitoz"]]
    if cfg.get("mitoz_path"):
        return ["--mitoz_path", cfg["mitoz_path"]]
    if shutil.which("mitoz"):
        return ["--mitoz_path", shutil.which("mitoz")]
    sys.path.insert(0, str(SCRIPT.parent))
    import mito_env                                    # conda / mamba environments scanned automatically
    env = mito_env.mitoz_env() if SCRIPT.exists() else None
    return ["--conda_env_mitoz", env] if env else []


def passthrough(rest):
    """只把 batch_mitoz.py 认识的 --选项 (及其值) 传过去; genbank all 带来的 --gene/--minlen 等丢弃."""
    known = set(re.findall(r'add_argument\(\s*(?:"-\w",\s*)?"(--\w+)"', SCRIPT.read_text(encoding="utf-8")))
    known -= {"--input", "--out_root"}
    out, keep = [], False
    for x in rest:
        if x.startswith("-"):
            keep = x.split("=")[0] in known
        if keep:
            out.append(x)
    return out


def num(v):
    return int(v) if str(v).strip().isdigit() else 0


def n_intron_records(gb_dir):
    """原 NCBI 记录中带 intron 特征的条数 (MitoZ 不会注释出来)."""
    n = 0
    for f in gb_dir.glob("*.gb"):
        rec_has = False
        for line in f.open(encoding="utf-8", errors="ignore"):
            if line.startswith("LOCUS"):
                rec_has = False
            elif line.startswith("     intron ") and not rec_has:
                rec_has = True
                n += 1
    return n


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    p.add_argument("--tag", default="")
    p.add_argument("--conda_env_mitoz", default="")
    p.add_argument("--mitoz_path", default="")
    a, rest = p.parse_known_args(argv)
    gb_root = step_dir(a.taxon, "gb")
    tags = [a.tag] if a.tag else sorted(
        d.name for d in gb_root.iterdir() if d.is_dir() and d.name.startswith("mito") and any(d.glob("*.gb"))) \
        if gb_root.exists() else []
    if not tags:
        summary("05_mitoz", ["跳过: 没有线粒体记录 (先运行 genbank 01 --mitogenome 或 --mito, 或用 --tag 指定)"])
        return 0
    loc = mitoz_location(a)
    if not loc:
        summary("05_mitoz", ["跳过: 未找到 MitoZ; 一键安装: python3 yzz.py mito setup (体检: python3 yzz.py mito doctor)"])
        return 0
    if not SCRIPT.exists():
        raise SystemExit(f"缺少 {SCRIPT}: git clone https://github.com/deyuanyang92-dev/Mitom.git temp_scripts/Mitoz-annotate")
    rest = passthrough(rest)
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    if cfg.get("intron_bin") and "--intron_bin" not in rest:
        rest += ["--intron_bin", cfg["intron_bin"]]
    lines = []
    for tag in tags:
        out = step_dir(a.taxon, "mitom", tag)   # MitoM 的 -o 输出目录, 内部结构原样保留
        cmd = [sys.executable, str(SCRIPT), "run", "-i", str(gb_root / tag), "-o", str(out), *loc, *rest]
        rc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        # MitoM 新版输出 (2026-11): summary.tsv (protein_genes/tRNAs/rRNAs/ncbi_errors), final_annotation/, reports/;
        # 旧版: annotation-summary.tsv (PCG/tRNA/rRNA), 04.final_gb/, all_problem_samples.txt. 两种都认.
        new = (out / "summary.tsv").exists()
        sf = out / ("summary.tsv" if new else "annotation-summary.tsv")
        rows = list(csv.DictReader(sf.open(encoding="utf-8"), delimiter="\t")) if sf.exists() else []
        k = ("protein_genes", "tRNAs", "rRNAs") if new else ("PCG", "tRNA", "rRNA")
        short = sum(num(r.get(k[0])) < 13 or num(r.get(k[1])) < 22 or num(r.get(k[2])) < 2 for r in rows)
        if new:
            n_prob = sum(num(r.get("ncbi_errors")) > 0 for r in rows)
        else:
            prob = out / "all_problem_samples.txt"
            n_prob = sum(1 for x in prob.open(encoding="utf-8") if x.strip() and not x.startswith("#")) if prob.exists() else 0
        rep = next((x for x in (out / "reports" / "intron_report.tsv", out / "intron_report.tsv") if x.exists()), out / "intron_report.tsv")
        introns = [r for r in csv.DictReader(rep.open(encoding="utf-8"), delimiter="\t")
                   if r.get("intron_start") and r.get("written", "yes") != "no"] if rep.exists() else []
        fix = (f"mito_intron 补 intron {len(introns)} 个 / {len({(r['record'], r['gene']) for r in introns})} 个基因"
               if rep.exists() else "mito_intron 未运行 (无 exonerate: --intron_bin)")
        lines.append(f"{tag}: {'OK' if rc == 0 else f'FAILED (exit {rc}, 见 pipeline.log)'} — 注释完成 {len(rows)} 条; "
                     f"基因不全 (PCG<13/tRNA<22/rRNA<2) {short}; {'NCBI table2asn 有错误' if new else '问题样本'} {n_prob}; "
                     f"原记录含 intron {n_intron_records(gb_root / tag)} 条; {fix}")
    write_readme(a.taxon)
    summary("05_mitoz", lines + [f"输出: {step_dir(a.taxon, 'mitom')}/<tag>/final_annotation/*.gb, final_annotation_all.gb, summary.tsv, "
                                 "original_vs_mitom.tsv, ncbi_submission/, reports/intron_report.tsv (README.txt 有说明)"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
