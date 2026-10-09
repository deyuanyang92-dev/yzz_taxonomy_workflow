"""yzz 团队工作流统一入口.

  python3 yzz.py list                         列出模块和步骤
  python3 yzz.py init <Taxon>                 按模板创建项目目录 projects/<Taxon>/
  python3 yzz.py <module> all <Taxon>         依次运行模块全部步骤 (如: worms all Polynoidae)
  python3 yzz.py <module> <NN> <Taxon>        只运行某一步 (如: worms 06 Polynoidae)
  python3 yzz.py <module> <NN-MM> <Taxon>     运行一段 (如: worms 07-09 Polynoidae)

每步只读上一步的 TSV、只写自己的 TSV, 终端只打印简短摘要; 某步失败可单独重跑.
"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "modules"


def steps(module):
    return sorted(p for p in (MODULES / module).glob("[0-9][0-9]_*.py"))


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv[0] == "list":
        for m in sorted(p for p in MODULES.iterdir() if p.is_dir()):
            st = steps(m.name)
            print(f"{m.name}: " + (", ".join(p.stem for p in st) if st else "(planned)"))
        return 0
    if argv[0] == "init":
        sys.path.insert(0, str(ROOT / "lib"))
        from common import project
        print(project(argv[1]))
        return 0
    module, sel, taxon, extra = argv[0], argv[1], argv[2], argv[3:]
    st = steps(module)
    if not st:
        raise SystemExit(f"模块 {module} 没有步骤脚本")
    if sel != "all":
        lo, _, hi = sel.partition("-")
        hi = hi or lo
        st = [p for p in st if lo <= p.name[:2] <= hi]
    for p in st:
        rc = subprocess.run([sys.executable, str(p), taxon, *extra]).returncode
        if rc:
            print(f"[{p.stem}] 失败 (exit {rc}); 修复后可单独重跑: python3 yzz.py {module} {p.name[:2]} {taxon}")
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
