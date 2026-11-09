"""86 批量: treatment.csv 中每个有 L1–L4 记述的分类单元 -> 85 汇编 (pptx + pdf). 已有当日成品的跳过 (可续跑).
用法: python3 yzz.py compilation 04 <项目目录> [--force] [--only Marphysa] [--species "Marphysa orientalis"]
日志: 11_物种图文汇编/86_all_decks.log
"""
import csv
import datetime
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg  # noqa: E402  项目根目录与配置
ROOT = cfg.ROOT
T = list(csv.DictReader(open(ROOT / "08_知识库/结构化/treatment.csv", encoding="utf-8-sig")))
taxa = sorted({t["taxon"] for t in T if t["level"][:2] in ("L1", "L2", "L3", "L4")})
if "--species" in sys.argv:
    taxa = [sys.argv[sys.argv.index("--species") + 1]]
if "--only" in sys.argv:
    g = sys.argv[sys.argv.index("--only") + 1]
    taxa = [t for t in taxa if t.startswith(g)]
stamp = datetime.date.today().isoformat()
log = open(ROOT / "11_物种图文汇编/86_all_decks.log", "a", encoding="utf-8")
for k, sp in enumerate(taxa, 1):
    out = ROOT / "11_物种图文汇编" / sp.replace(" ", "_") / f"{sp.replace(' ', '_')}_accounts_{stamp}.pdf"
    if out.exists() and "--force" not in sys.argv:
        continue
    r = subprocess.run([sys.executable, str(Path(__file__).with_name("deck.py")), str(ROOT), sp, "--no-open"],
                       capture_output=True, text=True, timeout=3600)
    msg = (r.stdout.strip().splitlines() or [""])[0] if r.returncode == 0 else "FAIL " + r.stderr.strip()[-300:]
    checks = [x for x in r.stdout.splitlines() if x.startswith("CHECK")]
    print(f"{k}/{len(taxa)} {sp}: {msg}" + (f" | {len(checks)} CHECK" if checks else ""), file=log, flush=True)
    for c in checks:
        print("   ", c, file=log, flush=True)
print(f"[86] {len(taxa)} taxa done; log {log.name}")
