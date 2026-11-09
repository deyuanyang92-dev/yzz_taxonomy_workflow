"""yzz 团队工作流统一入口.

  python3 yzz.py list                         列出模块和步骤
  python3 yzz.py init <Taxon>                 按模板创建项目目录 projects/<Taxon>/
  python3 yzz.py project <Taxon> <项目目录>    登记: 该类群输出直接写入你的项目文件夹 (不带目录 = 列出登记)
  python3 yzz.py <module> ... --project <目录>  本次运行输出到该项目文件夹
  python3 yzz.py <module> all <Taxon>         依次运行模块全部步骤 (如: worms all Polynoidae)
  python3 yzz.py <module> <NN> <Taxon>        只运行某一步 (如: worms 06 Polynoidae)
  python3 yzz.py <module> <NN-MM> <Taxon>     运行一段 (如: worms 07-09 Polynoidae)
  python3 yzz.py zh check|fix <文件...>       中文 Word/PDF/txt 防乱码检查与修复 (lib/zh_office.py)
  python3 yzz.py ms build <稿.md> <参考文献.md> <out.docx> [图...]   投稿格式 Word（双倍行距/行号/三线表），随后自动 ms check (lib/ms_build.py)
  python3 yzz.py ms check <out.docx> [--no-render]   Word 排版检查 + 用本机 MS Word 渲染、导出含表页 PNG (lib/docx_layout.py)
  python3 yzz.py match <表格|名单> [--col 列] [--family 科]   WoRMS 批量名称匹配 -> 现行有效名 (lib/worms_match.py)
  python3 yzz.py grant check <材料目录>       厦大纵向项目申请材料检查, 只报问题不改文件 (yzz-项目申请/)
  python3 yzz.py sra all <Taxon> [--runs 列表|--runinfo csv]   SRA metadata 总表 + 数据类型 + 下载清单 (modules/sra)
  python3 yzz.py mito setup|doctor           线粒体注释软件一键安装 / 体检 (temp_scripts/Mitoz-annotate)
  python3 yzz.py compilation <NN> <项目目录>  类群修订本地分类数据库 + 物种图文汇编 pptx/pdf (modules/compilation, Travisia 版式)
  python3 yzz.py molheat 01|02 <Taxon> [选项]    分子数据分布热图: GenBank+SRA+Assembly 计数矩阵 -> 热图 (modules/molheat; R 版 molheat.R)

每步只读上一步的 TSV、只写自己的 TSV, 终端只打印简短摘要; 某步失败可单独重跑.
"""
import os
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "modules"


def steps(module):
    return sorted(p for p in (MODULES / module).glob("[0-9][0-9]_*.py"))


OWORMS_STEPS = {"01", "02", "03", "04", "05", "06", "07", "08", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20"}


def worms(sel, taxon, extra):
    """WoRMS 部分由 oworms 完成 (github.com/deyuanyang92-dev/oworms, 开发副本 /root/github/oworms, pip install -e).
    yzz 只调用: 输出 <项目>/02_原始数据/worms/<Taxon>/{data,reports} (oworms 原生结构);
    项目有 08_知识库/结构化/od_texts.tsv (compilation 05 导出的原始描述原文) 时自动加 --od-text, 原文复查 (10/17) 一并跑.
    yzz 独有步骤 (modules/worms/2N_*.py, 如 23 物种×文献) 在 oworms 之后运行."""
    sys.path.insert(0, str(ROOT / "lib"))
    from common import project, worms_root
    root = worms_root(taxon)
    own = steps("worms")                                   # yzz 独有步骤
    if sel == "all":
        ow, mine = "all", own
    else:
        lo, _, hi = sel.partition("-")
        lo, hi = lo.zfill(2), (hi or lo).zfill(2)
        ow = ",".join(n for n in sorted(OWORMS_STEPS) if lo <= n <= hi)
        mine = [p for p in own if lo <= p.name[:2] <= hi]
    if ow:
        cmd = ["oworms", "run", taxon, "--out", str(root.parent), "--steps", ow, *extra]
        odt = project(taxon) / "08_知识库" / "结构化" / "od_texts.tsv"
        if odt.exists() and "--od-text" not in extra:
            cmd += ["--od-text", str(odt)]
        print(" ".join(cmd), flush=True)
        rc = subprocess.run(cmd).returncode
        if rc:
            return rc
    for p in mine:
        rc = subprocess.run([sys.executable, str(p), taxon, *extra]).returncode
        if rc:
            print(f"[{p.stem}] 失败 (exit {rc}); 修复后可单独重跑: python3 yzz.py worms {p.name[:2]} {taxon}")
            return rc
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv[0] == "list":
        for m in sorted(p for p in MODULES.iterdir() if p.is_dir()):
            st = steps(m.name)
            print(f"{m.name}: " + (", ".join(p.stem for p in st) if st else "(planned)"))
        return 0
    if argv[0] == "zh":
        sys.path.insert(0, str(ROOT / "lib"))
        from zh_office import main as zh_main
        return zh_main(argv[1:])
    if argv[0] == "ms":
        sys.path.insert(0, str(ROOT / "lib"))
        from ms_build import cli as ms_cli
        return ms_cli(argv[1:])
    if argv[0] == "match":
        sys.path.insert(0, str(ROOT / "lib"))
        from worms_match import main as match_main
        return match_main(argv[1:])
    if argv[0] == "grant":
        sys.path.insert(0, str(ROOT / "yzz-项目申请"))
        from check import main as grant_main
        return grant_main(argv[2:] if argv[1:2] == ["check"] else argv[1:])
    if argv[0] == "mito":
        mito = ROOT / "temp_scripts" / "Mitoz-annotate"
        if argv[1:2] == ["setup"]:
            return subprocess.run(["bash", str(mito / "install.sh"), *argv[2:]]).returncode
        if argv[1:2] == ["doctor"]:
            return subprocess.run([sys.executable, str(mito / "mito_env.py"), "doctor", *argv[2:]]).returncode
        raise SystemExit("用法: python3 yzz.py mito setup|doctor")
    if "--project" in argv:                     # 本次运行输出到该项目文件夹 (子进程继承环境变量)
        i = argv.index("--project")
        os.environ["YZZ_PROJECT_DIR"] = str(Path(argv[i + 1]).resolve())
        argv = argv[:i] + argv[i + 2:]
    if argv[0] == "project":
        sys.path.insert(0, str(ROOT / "lib"))
        from common import REGISTRY, register_project
        if len(argv) == 3:
            print(f"{argv[1]} -> {register_project(argv[1], argv[2])}  (登记于 {REGISTRY})")
        else:
            print(REGISTRY.read_text(encoding="utf-8") if REGISTRY.exists() else "{}")
        return 0
    if argv[0] == "init":
        sys.path.insert(0, str(ROOT / "lib"))
        from common import project
        print(project(argv[1]))
        return 0
    module, sel, taxon, extra = argv[0], argv[1], argv[2], argv[3:]
    if module == "worms":
        return worms(sel, taxon, extra)
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
