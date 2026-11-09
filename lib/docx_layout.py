"""Word 排版检查（英文/中文稿通用），由 `yzz.py zh check|fix` 和 `yzz.py ms check` 调用.

每一条都是用户在 Word 里实际看到并投诉过的问题（2026-11-09，岩虫属综述）:
  - pandoc 在 "et al." "p." 后插入不换行空格 U+00A0，Word 编辑标记下显示为 °        → fix: 换普通空格
  - 英文段落 run 带 hint=eastAsia / 东亚字体，Word 用宋体排弯引号 → 全角、前后多空     → zh_office 负责
  - 表格单元格段落带 suppressLineNumbers，Word 每格前显示小黑块（Word 本不给表格编行号） → fix: 删除
  - 表格宽于版心（右侧被截）                                                         → 只报
  - 列宽小于该列最长单词，Word 把词拆开（"Mossamb|ica"）                              → 只报
  - 表题与表格分页（表头孤悬页底）：表题段落无 keepNext                                → fix: 加 keepNext
渲染核查: render() 用本机 MS Word（powershell COM）转 PDF，并导出含表页 PNG；LibreOffice 看不出上述问题。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CJK = re.compile("[⺀-鿿豈-﫿＀-￯　-〿]")
CHAR_TW = 105          # Times New Roman 10 pt 每字符 twips（含余量），与 ms_build 一致
CELL_PAD = 2 * 85 + 40
CAPTION = re.compile(r"^\s*(Table|表)\s*S?\d")


_FONTS: dict = {}
_FONT_FILES = {(0, 0): ("times", "Regular"), (1, 0): ("timesbd", "Bold"),
               (0, 1): ("timesi", "Italic"), (1, 1): ("timesbi", "BoldItalic")}


def _font(bold: bool, italic: bool):
    """Real Times New Roman metrics (Windows fonts on WSL); Liberation Serif is metric-compatible."""
    key = (int(bold), int(italic))
    if key not in _FONTS:
        from PIL import ImageFont
        win, lib = _FONT_FILES[key]
        _FONTS[key] = None
        for f in (Path("/mnt/c/Windows/Fonts") / f"{win}.ttf",
                  Path(f"/usr/share/fonts/truetype/liberation/LiberationSerif-{lib}.ttf")):
            if f.exists():
                _FONTS[key] = ImageFont.truetype(str(f), 200)
                break
    return _FONTS[key]


def text_twips(text: str, bold: bool = False, italic: bool = False, pt: float = 10) -> float:
    """Width of text in twips at pt size; CHAR_TW proxy if no font file is found."""
    f = _font(bold, italic)
    if f is None:
        return len(text) * CHAR_TW * (1.2 if bold else 1.0)
    return f.getlength(text) * pt / 200 * 20


def q(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _text(el: etree._Element) -> str:
    return "".join(t.text or "" for t in el.iter(q("t")))


def scan(root: etree._Element, fix: bool = False) -> list[str]:
    """document.xml 根节点上检查（fix=True 时就地修可修项）。"""
    issues: list[str] = []
    n_nbsp = 0
    for t in root.iter(q("t")):
        if t.text and " " in t.text:
            n_nbsp += t.text.count(" ")
            if fix:
                t.text = t.text.replace(" ", " ")
    if n_nbsp:
        issues.append(f"不换行空格 U+00A0 ×{n_nbsp}（Word 编辑标记下显示 °，多为 pandoc 在 et al./p. 后插入）")
    if root.tag in (q("ftr"), q("hdr")):     # 页眉页脚本不编行号，设置了只会显示小黑块
        bad = list(root.iter(q("suppressLineNumbers")))
    else:
        bad = [s for tc in root.iter(q("tc")) for s in tc.iter(q("suppressLineNumbers"))]
    if bad:
        issues.append(f"表格单元格/页眉页脚 suppressLineNumbers ×{len(bad)}（Word 显示小黑块；这些地方本不编行号）")
        if fix:
            for s in bad:
                s.getparent().remove(s)
    body = root.find(q("body"))
    sect = body.find(q("sectPr")) if body is not None else None
    usable = None
    if sect is not None and sect.find(q("pgSz")) is not None and sect.find(q("pgMar")) is not None:
        mar = sect.find(q("pgMar"))
        usable = int(sect.find(q("pgSz")).get(q("w"))) - int(mar.get(q("left"))) - int(mar.get(q("right")))
    for n, tbl in enumerate(root.iter(q("tbl")), 1):
        grid_el = tbl.find(q("tblGrid"))
        grid = [int(g.get(q("w")) or 0) for g in grid_el] if grid_el is not None else []
        if usable and sum(grid) > usable + 20:
            issues.append(f"表 {n}: 宽 {sum(grid)} twips > 版心 {usable}（右侧会被截）")
        rows = tbl.findall(q("tr"))
        for i, tr in enumerate(rows):
            tcs = tr.findall(q("tc"))
            if len(tcs) != len(grid) or CJK.search(_text(tr)):
                continue
            for j, tc in enumerate(tcs):
                words = re.split(r"[ \-\u2013\u2014]", _text(tc))
                word = max(words, key=lambda w: text_twips(w, bold=i == 0), default="")
                need = text_twips(word, bold=i == 0) + CELL_PAD
                if grid[j] and need > grid[j] + 3:   # 3 twips rounding tolerance
                    issues.append(f"表 {n} 第 {j + 1} 列: '{word}' 宽 {need:.0f} > 列宽 {grid[j]} twips，Word 会拆词")
                    break
        prev = tbl.getprevious()
        if prev is not None and prev.tag == q("p") and CAPTION.search(_text(prev)):
            ppr = prev.find(q("pPr"))
            if ppr is None or ppr.find(q("keepNext")) is None:
                issues.append(f"表 {n}: 表题无 keepNext（表题/表头可能与表格分页）")
                if fix:
                    if ppr is None:
                        ppr = etree.Element(q("pPr"))
                        prev.insert(0, ppr)
                    kn = etree.Element(q("keepNext"))
                    ps = ppr.find(q("pStyle"))
                    ppr.insert(1 if ps is not None else 0, kn)
    return sorted(set(issues), key=issues.index)


def _wpath(p: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(p.resolve())], capture_output=True, text=True, check=True).stdout.strip()


PS1 = r"""param([string]$In, [string]$Out)
$w = New-Object -ComObject Word.Application
$w.Visible = $false; $w.DisplayAlerts = 0
try { $d = $w.Documents.Open($In, $false, $true); $d.ExportAsFixedFormat($Out, 17); $d.Close(0) }
finally { $w.Quit() }
"""


def render(path: str | Path, outdir: str | Path | None = None, dpi: int = 80) -> tuple[Path, list[Path]]:
    """用 MS Word 渲染 .docx → PDF，导出所有含表题页的 PNG。返回 (pdf, pngs)。"""
    path = Path(path)
    outdir = Path(outdir) if outdir else path.parent / "_render"
    outdir.mkdir(exist_ok=True)
    for old in outdir.glob(f"{path.stem}_p-*.png"):
        old.unlink()
    ps1 = outdir / "_word2pdf.ps1"
    ps1.write_text(PS1, encoding="utf-8")
    pdf = outdir / f"{path.stem}_word.pdf"
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _wpath(ps1),
                    "-In", _wpath(path), "-Out", _wpath(outdir) + "\\" + pdf.name], check=True, timeout=600)
    pages = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout.split("\f")
    hit = [i + 1 for i, t in enumerate(pages) if re.search(r"^(Table|表)\s*S?\d", t, re.M)]
    for pg in hit:
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(pg), "-l", str(pg), str(pdf),
                        str(outdir / f"{path.stem}_p")], check=True)
    return pdf, sorted(outdir.glob(f"{path.stem}_p-*.png"))
