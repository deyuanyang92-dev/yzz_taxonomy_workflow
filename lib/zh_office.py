"""中文 Office/PDF/txt 防乱码：检查与修复（yzz.py zh ...）.

已确认的问题（2026-10-09）:
  - 全角空格 U+3000 在 Word “显示编辑标记”下显示为 □ —— 用户视为乱码 → 一律换半角空格。
  - WSL 无 仿宋_GB2312/方正小标宋 等字体 → /etc/fonts/local.conf 映射；PDF 若回落 DejaVu 则无中文字形。
  - Windows 记事本/Excel 读无 BOM 的 UTF-8 txt/csv 可能乱码 → 写 UTF-8 BOM + CRLF。
  - 表格竖排单元格 tcPr/textDirection=tbRl（2026-10-29，申请书“摘要”“主题词”标签）:
    LibreOffice/WPS 渲染时同页后续中文字符重叠，“十五五”显示成乱码 → 去掉竖排（改横排）。
预防: 含中文的段落里，含中文/中文标点的 run 加 w:hint="eastAsia" 并补 eastAsia 字体。
  - 纯英文段落不加；已加的去掉（2026-11-09：英文稿弯引号在 Word 中变全角）。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from lxml import etree

import docx_layout  # lib/ 在 sys.path 上（yzz.py 与 tests 都如此）

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
CJK = re.compile("[⺀-鿿豈-﫿＀-￯　-〿]")
SHARED = re.compile("[　‘’“”…—―·×÷∶、-〿＀-￯]")
PARTS = re.compile(r"word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$")
BAD_TEXT = re.compile("[�□▯]")
VERTICAL = {"tbRl", "btLr", "tbRlV", "tbLrV"}


def q(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _scan(root: etree._Element, fix: bool, ea_font: str) -> list[str]:
    issues: list[str] = []
    for r in root.iter(q("r")):
        ts = list(r.iter(q("t")))
        text = "".join(t.text or "" for t in ts)
        if not (CJK.search(text) or SHARED.search(text)):
            continue
        # 共用标点（‘’“”—…× 等）只在所在段落含中文时才按东亚字体处理。
        # 英文段落里加 hint=eastAsia 会让 Word 用宋体排弯引号 → 显示为全角、前后多空（2026-11-09 实证）。
        para = next((a for a in r.iterancestors(q("p"))), None)
        ptext = "".join(para.itertext()) if para is not None else text
        if not CJK.search(ptext):
            rpr0 = r.find(q("rPr"))
            rf0 = rpr0.find(q("rFonts")) if rpr0 is not None else None
            if rf0 is not None and rf0.get(q("hint")) == "eastAsia":
                issues.append(f"英文段落标点被设为东亚字体(Word 显示全角): {text[:30]!r}")
                if fix:
                    del rf0.attrib[q("hint")]
            continue
        if "　" in text:
            issues.append(f"全角空格(Word 编辑标记下显示□): {text[:30]!r}")
            if fix:
                for t in ts:
                    if t.text and "　" in t.text:
                        t.text = t.text.replace("　", "  ")
                        t.set(XML_SPACE, "preserve")
        rpr = r.find(q("rPr"))
        rf = rpr.find(q("rFonts")) if rpr is not None else None
        if rf is None or rf.get(q("hint")) != "eastAsia":
            issues.append(f"缺 hint=eastAsia: {text[:30]!r}")
            if fix:
                if rpr is None:
                    rpr = etree.Element(q("rPr"))
                    r.insert(0, rpr)
                if rf is None:
                    rf = etree.Element(q("rFonts"))
                    rpr.insert(0, rf)
                rf.set(q("hint"), "eastAsia")
                if rf.get(q("eastAsia")) is None and rf.get(q("eastAsiaTheme")) is None:
                    rf.set(q("eastAsia"), ea_font)
    for td in list(root.iter(q("textDirection"))):
        if td.getparent().tag == q("tcPr") and td.get(q("val")) in VERTICAL:
            cell = "".join(td.getparent().getparent().itertext())[:15]
            issues.append(f"竖排单元格(LibreOffice/WPS 会把同页后续中文排乱): {cell!r}")
            if fix:
                td.getparent().remove(td)
    return issues


def docx(path: str | Path, fix: bool = False, out: str | Path | None = None, ea_font: str = "宋体") -> list[str]:
    """检查（fix=False）或修复 .docx。原地修复时留 .bak；文件被 Word 占用时用 out。"""
    path = Path(path)
    issues: list[str] = []
    entries: list[tuple[zipfile.ZipInfo, bytes]] = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            data = z.read(info)
            if PARTS.search(info.filename):
                root = etree.fromstring(data)
                issues += _scan(root, fix, ea_font)
                if re.search(r"word/(document|header\d*|footer\d*)\.xml$", info.filename):  # Word 排版（2026-11-09）
                    issues += docx_layout.scan(root, fix)
                if fix:
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            entries.append((info, data))
    if fix:
        dst = Path(out) if out else path
        if out is None:
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
            for info, data in entries:
                z.writestr(info, data)
    return issues


def pdf(path: str | Path) -> list[str]:
    """PDF：未嵌入字体、DejaVu 回落、文字层方框/替换字符。"""
    issues: list[str] = []
    fonts = subprocess.run(["pdffonts", str(path)], capture_output=True, text=True).stdout.splitlines()[2:]
    for line in fonts:
        cols = line.split()
        if len(cols) >= 5 and cols[-5] == "no":
            issues.append(f"未嵌入字体: {cols[0]}")
        if "DejaVu" in line:
            issues.append(f"回落 DejaVu（无中文字形）: {cols[0]}")
    text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True).stdout
    n = sum(1 for ln in text.splitlines() if BAD_TEXT.search(ln))
    if n:
        issues.append(f"文字层含方框/替换字符 {n} 行")
    return issues


def txt(path: str | Path, fix: bool = False) -> list[str]:
    """给 Windows 用的 txt/csv：UTF-8 BOM + CRLF。"""
    path = Path(path)
    raw = path.read_bytes()
    issues = []
    if not raw.startswith(b"\xef\xbb\xbf"):
        issues.append("无 UTF-8 BOM（Windows 可能乱码）")
    body = raw.removeprefix(b"\xef\xbb\xbf")
    if b"\n" in body.replace(b"\r\n", b""):
        issues.append("含 LF 换行（记事本旧版不换行）")
    if fix and issues:
        s = body.decode("utf-8").replace("\r\n", "\n")
        path.write_bytes(b"\xef\xbb\xbf" + s.replace("\n", "\r\n").encode("utf-8"))
    return issues


def xlsx(path: str | Path, fix: bool = False) -> list[str]:
    """Excel：单元格中的全角空格 U+3000（Word/WPS 编辑标记下显示 □）和方框/替换字符。"""
    from openpyxl import load_workbook
    wb = load_workbook(path)
    n_fw, bad = 0, []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    if "\u3000" in c.value:
                        n_fw += 1
                        if fix:
                            c.value = c.value.replace("\u3000", " ")
                    if BAD_TEXT.search(c.value):
                        bad.append(f"{ws.title}!{c.coordinate}")
    issues = [f"全角空格 U+3000 {n_fw} 个单元格"] if n_fw else []
    if bad:
        issues.append(f"方框/替换字符 {len(bad)} 个单元格: {', '.join(bad[:5])}")
    if fix and n_fw:
        wb.save(path)
    return issues


def main(argv: list[str]) -> int:
    """yzz.py zh <check|fix> 文件... [-o 输出]；按扩展名分派 docx/pdf/xlsx/txt/csv。"""
    if len(argv) < 2 or argv[0] not in ("check", "fix"):
        print("用法: python3 yzz.py zh check|fix <文件...> [-o out.docx]")
        return 2
    fix = argv[0] == "fix"
    args = argv[1:]
    out = None
    if "-o" in args:
        i = args.index("-o")
        out = args[i + 1]
        args = args[:i] + args[i + 2:]
    total = 0
    for f in args:
        ext = Path(f).suffix.lower()
        if ext == ".docx":
            iss = docx(f, fix, out if len(args) == 1 else None)
        elif ext == ".pdf":
            iss = pdf(f)
        elif ext == ".xlsx":
            iss = xlsx(f, fix)
        elif ext in (".txt", ".csv", ".tsv", ".md"):
            iss = txt(f, fix)
        else:
            print(f"[跳过] {f}: 不支持的格式")
            continue
        total += len(iss)
        tag = "已修复" if fix and iss and ext != ".pdf" else ("OK" if not iss else f"{len(iss)} 处问题")
        print(f"[{tag}] {f}")
        for s in iss[:10]:
            print(f"   - {s}")
    return 1 if total and not fix else 0
