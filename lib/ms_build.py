#!/usr/bin/env python3
"""Build a journal-submission .docx from the Markdown master.

Usage:
    python3 yzz.py ms build DRAFT.md REFERENCES.md OUT.docx [FIG1.png FIG2.png ...]
    python3 yzz.py ms check OUT.docx        # layout lint + render in MS Word, PNG of every table page
(origin: 岩虫属系统修订/12_综述/04_统稿/build_docx.py, 2026-11-09)

Manuscript format (ZJLS-type submission, generic for zoology journals):
  A4, 2.5 cm margins, Times New Roman 12 pt, double spacing, continuous line
  numbers, page numbers bottom centre, black headings (H1 bold, H2 bold italic),
  three-line tables (single spaced, 10 pt), figures at the end with legends.

Lessons built in (2026-11-09): never ship pandoc's default template (blue Calibri,
single spacing, no line numbers); do not skip heading levels (### -> ##); render
the docx to PDF and look at the pages before delivery; run yzz zh check.
"""
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor, Twips
from docx_layout import text_twips as _tw  # real TNR metrics, shared with the lint

FONT = "Times New Roman"


def set_font(style, size, bold=None, italic=None):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor(0, 0, 0)
    if bold is not None:
        style.font.bold = bold
    if italic is not None:
        style.font.italic = italic
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(a), FONT)  # English text: no SimSun, or Word sets quotes full-width
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        rfonts.attrib.pop(qn(a), None)


def make_reference(path):
    data = subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"],
                          capture_output=True, check=True).stdout
    Path(path).write_bytes(data)
    doc = Document(path)
    st = {s.name: s for s in doc.styles}  # python-docx maps "Heading 1" to "heading 1"; pandoc uses capitals
    for name in ("Normal", "Body Text", "First Paragraph", "Abstract", "Bibliography",
                 "Block Text", "Title", "Subtitle", "Author", "Date"):
        if name in st:
            set_font(st[name], 12)
            pf = st[name].paragraph_format
            pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
    for name in ("Body Text", "First Paragraph"):
        st[name].paragraph_format.first_line_indent = Cm(0) if name == "First Paragraph" else Cm(0.75)
    set_font(st["Title"], 14, bold=True)
    st["Title"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    st["Title"].paragraph_format.space_after = Pt(12)
    heads = {"Heading 1": (12, True, False), "Heading 2": (12, True, True), "Heading 3": (12, False, True)}
    for name, (size, b, i) in heads.items():
        set_font(st[name], size, bold=b, italic=i)
        pf = st[name].paragraph_format
        pf.space_before = Pt(12)
        pf.space_after = Pt(0)
        pf.keep_with_next = True
        pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    # Compact = table cells and list items
    set_font(st["Compact"], 10)
    st["Compact"].paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    st["Compact"].paragraph_format.space_after = Pt(0)
    if "Hyperlink" in st:
        st["Hyperlink"].font.color.rgb = RGBColor(0, 0, 0)
        st["Hyperlink"].font.underline = False
    doc.save(path)


def preprocess(md, refs, figs=()):
    md = re.sub(r"^### ", "## ", md, flags=re.M)          # no skipped heading levels
    lines = md.splitlines()
    title = lines[0].lstrip("# ").strip()
    body = "\n".join(lines[1:])
    refs_body = re.sub(r"^#.*\n", "", refs, count=1).strip()
    refs_body = re.sub(r"^[-*] ", "", refs_body, flags=re.M)
    body = re.sub(r"(# References\s*\n)(.*?)(?=\n# )", lambda m: m.group(1) + "\n" + refs_body + "\n",
                  body, count=1, flags=re.S)
    if figs:  # figures at the very end, one per page, labelled
        body += "\n\n# Figures\n\n" + "\n\n".join(
            f"![]({f}){{width=16cm}}\n\n**Figure {i}**" for i, f in enumerate(figs, 1))
    return f"---\ntitle: \"{title}\"\n---\n\n" + body


def table_borders(tbl):
    tblPr = tbl._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):  # schema order
        e = OxmlElement(f"w:{edge}")
        if edge in ("top", "bottom"):
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "8")
            e.set(qn("w:color"), "000000")
        else:
            e.set(qn("w:val"), "nil")
        b.append(e)
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    tblPr.insert_element_before(b, "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook",
                                "w:tblCaption", "w:tblDescription")
    # rule under header row
    for cell in tbl.rows[0].cells:
        tcPr = cell._tc.get_or_add_tcPr()
        tb = OxmlElement("w:tcBorders")
        e = OxmlElement("w:bottom")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), "000000")
        tb.append(e)
        tcPr.insert_element_before(tb, "w:shd", "w:noWrap", "w:tcMar", "w:textDirection",
                                   "w:tcFitText", "w:vAlign", "w:hideMark")


def merge_subheader_rows(tbl):
    """A row whose first cell is italic text and other cells empty becomes one merged cell."""
    for row in tbl.rows[1:]:
        cells = row.cells
        if cells[0].text.strip() and all(not c.text.strip() for c in cells[1:]):
            first = cells[0]
            merged = first.merge(cells[-1])
            # merge() concatenates empty paragraphs; drop them
            for p in merged.paragraphs[1:]:
                if not p.text.strip():
                    p._element.getparent().remove(p._element)


CHAR_TW = 105     # Times New Roman 10 pt, twips per char incl. margin of safety (Word render 2026-11-09)
CELL_PAD = 2 * 85 + 40   # left + right cell margin + slack, twips
USABLE_TW = int(Cm(16.0).twips)


def cell_metrics(cell, header):
    """(max-content, min-content) widths in twips, run-aware (bold/italic).

    Breaks are allowed after a space or a hyphen/dash only (Word does not reliably break at '/')."""
    mx = mn = 0.0
    for p in cell.paragraphs:
        line = word = 0.0
        for r in p.runs:
            b, i = bool(r.bold) or header, bool(r.italic)
            for ch in r.text:
                w = _tw(ch, b, i)
                line += w
                if ch == " ":
                    mn, word = max(mn, word), 0.0
                else:
                    word += w
                    if ch in "-\u2013\u2014":
                        mn, word = max(mn, word), 0.0
        mn, mx = max(mn, word), max(mx, line)
    return mx, mn


def column_widths(tbl):
    """Width allocation re-implemented after flextable fit_columns (logic only; flextable is GPL-3).

    Share the text width in proportion to max-content widths; clamp any column that falls below
    its floor (longest unbreakable word + padding) at the floor; redistribute; repeat.
    History: fixed shares broke words in Word ('Mossamb|ica'); a char-count proxy left 13 twips slack."""
    n = len(tbl.columns)
    pretty, floor = [0.0] * n, [0.0] * n
    for k, row in enumerate(tbl.rows):
        cells = row.cells
        if len({id(c._tc) for c in cells}) == 1 and n > 1:   # merged sub-header row
            continue
        for j, c in enumerate(cells):
            mx, mn = cell_metrics(c, k == 0)
            pretty[j] = max(pretty[j], mx + CELL_PAD)
            floor[j] = max(floor[j], mn + CELL_PAD)
    W = USABLE_TW
    if sum(pretty) <= W:
        return [int(p * W / sum(pretty)) for p in pretty]
    free, tgt = [True] * n, list(floor)
    while True:
        avail = W - sum(f for f, fr in zip(floor, free) if not fr)
        tot = sum(p for p, fr in zip(pretty, free) if fr)
        clamped = False
        for j in range(n):
            if free[j]:
                tgt[j] = pretty[j] / tot * avail
                if tgt[j] < floor[j]:
                    tgt[j], free[j], clamped = floor[j], False, True
        if not clamped or not any(free):
            break
    s = W / sum(tgt) if sum(tgt) > W else 1.0   # floors alone too wide: shrink (better: 9 pt or landscape)
    return [math.ceil(t * s) if s == 1.0 else int(t * s) for t in tgt]   # ceil: floors must not be truncated


def format_table(tbl):
    """Three-line table: content-based widths, 10 pt single spaced, 2 pt cell padding, rows not split."""
    widths = column_widths(tbl)
    tblPr = tbl._tbl.tblPr
    tbl.autofit = False
    for old in tblPr.findall(qn("w:tblW")) + tblPr.findall(qn("w:tblLayout")) + tblPr.findall(qn("w:tblCellMar")):
        tblPr.remove(old)
    tw = OxmlElement("w:tblW")
    tw.set(qn("w:type"), "dxa")
    tw.set(qn("w:w"), str(sum(widths)))
    tblPr.insert_element_before(tw, "w:jc", "w:tblCellSpacing", "w:tblInd", "w:tblBorders",
                                "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook")
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.insert_element_before(lay, "w:tblCellMar", "w:tblLook", "w:tblCaption", "w:tblDescription")
    mar = OxmlElement("w:tblCellMar")
    for edge, v in (("top", 40), ("left", 85), ("bottom", 40), ("right", 85)):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:w"), str(v))
        e.set(qn("w:type"), "dxa")
        mar.append(e)
    tblPr.insert_element_before(mar, "w:tblLook", "w:tblCaption", "w:tblDescription")
    for gc, w in zip(tbl._tbl.tblGrid.findall(qn("w:gridCol")), widths):
        gc.set(qn("w:w"), str(w))
    for i, row in enumerate(tbl.rows):
        trPr = row._tr.get_or_add_trPr()
        if trPr.find(qn("w:cantSplit")) is None:
            trPr.insert(0, OxmlElement("w:cantSplit"))
        for c, w in zip(row.cells, widths):
            c.width = Twips(w)
            c.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM if i == 0 else WD_ALIGN_VERTICAL.TOP
            for p in c.paragraphs:
                pf = p.paragraph_format
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                pf.first_line_indent = Cm(0)
                pf.left_indent = Cm(0)
                pf.space_before = Pt(0)
                pf.space_after = Pt(0)
                pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
                if i == 0:
                    for run in p.runs:
                        run.font.bold = True
    # keep the header row with the first data row (no orphan header at a page foot)
    for row in list(tbl.rows)[:2]:
        for c in row.cells:
            for p in c.paragraphs:
                p.paragraph_format.keep_with_next = True
    # caption above the table stays with it
    prev = tbl._tbl.getprevious()
    if prev is not None and prev.tag == qn("w:p"):
        from docx.text.paragraph import Paragraph
        Paragraph(prev, tbl._parent).paragraph_format.keep_with_next = True
    merge_subheader_rows(tbl)
    table_borders(tbl)
    # no suppressLineNumbers in cells: Word never numbers table lines, and the property
    # shows as a black square before every cell paragraph (2026-11-09 user screenshot)


def postprocess(path):
    doc = Document(path)
    for sec in doc.sections:
        sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
        for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            setattr(sec, m, Cm(2.5))
        sec.gutter, sec.header_distance, sec.footer_distance = Cm(0), Cm(1.25), Cm(1.25)
        sectPr = sec._sectPr
        ln = OxmlElement("w:lnNumType")
        ln.set(qn("w:countBy"), "1")
        ln.set(qn("w:restart"), "continuous")
        ln.set(qn("w:distance"), "360")
        sectPr.insert_element_before(ln, "w:pgNumType", "w:cols", "w:formProt", "w:vAlign",
                                     "w:noEndnote", "w:titlePg", "w:textDirection", "w:bidi",
                                     "w:rtlGutter", "w:docGrid", "w:printerSettings", "w:sectPrChange")
        p = sec.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run()
        for t, txt in (("begin", None), (None, "PAGE"), ("end", None)):
            if t:
                f = OxmlElement("w:fldChar")
                f.set(qn("w:fldCharType"), t)
                r._r.append(f)
            else:
                it = OxmlElement("w:instrText")
                it.set(qn("xml:space"), "preserve")
                it.text = txt
                r._r.append(it)
        r.font.name = FONT
        r.font.size = Pt(10)
    # pandoc inserts U+00A0 after abbreviations ("et al.", "p.", "pp."); Word shows it as a degree sign
    for t in doc.element.body.iter(qn("w:t")):
        if t.text and "\u00a0" in t.text:
            t.text = t.text.replace("\u00a0", " ")
    # pandoc bugs: list items put pStyle after numPr; tblPr puts jc last
    body = doc.element.body
    for pPr in body.iter(qn("w:pPr")):
        ps = pPr.find(qn("w:pStyle"))
        if ps is not None and pPr.index(ps) != 0:
            pPr.remove(ps)
            pPr.insert(0, ps)
    for tblPr in body.iter(qn("w:tblPr")):
        jc = tblPr.find(qn("w:jc"))
        if jc is not None:
            tblPr.remove(jc)
            tblPr.insert_element_before(jc, "w:tblCellSpacing", "w:tblInd", "w:tblBorders", "w:shd",
                                        "w:tblLayout", "w:tblCellMar", "w:tblLook")
    for tbl in doc.tables:
        format_table(tbl)
    # pandoc gives tight lists the table style "Compact"; body lists must look like body text
    body_style = next(st for st in doc.styles if st.name == "Body Text")
    for p in doc.paragraphs:
        if p.style.name == "Compact":
            p.style = body_style  # numbering supplies the hanging indent; no direct indent here
    # references: hanging indent, no first-line indent
    in_refs = False
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            in_refs = p.text.strip() == "References"
            continue
        if in_refs and p.text.strip():
            pf = p.paragraph_format
            pf.left_indent = Cm(0.75)
            pf.first_line_indent = Cm(-0.75)
        elif re.match(r"(Table|Figure) S?\d", p.text) or p.text.startswith("Keywords"):
            p.paragraph_format.first_line_indent = Cm(0)  # captions/legends flush left
    # figures: centre, page break before each image paragraph
    for p in doc.paragraphs:
        if p._p.findall(".//" + qn("w:drawing")):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.page_break_before = True
            p.paragraph_format.first_line_indent = Cm(0)
    doc.save(path)


def main(md_path, refs_path, out, *figs):
    o = Path(out)
    if o.exists():
        try:
            with open(o, "ab"):
                pass
        except PermissionError:
            raise SystemExit(f"{o} 正被 Word 打开（锁定），无法覆盖。请在 Word 中关闭该文件后重跑。")
    md = Path(md_path).read_text(encoding="utf-8")
    refs = Path(refs_path).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as td:
        ref = Path(td) / "reference.docx"
        make_reference(ref)
        src = Path(md_path).parent / ".build_tmp.md"
        src.write_text(preprocess(md, refs, figs), encoding="utf-8")
        try:
            abbr = Path(td) / "no_abbreviations.txt"   # empty: pandoc inserts no NBSP after et al./p.
            abbr.write_text("", encoding="utf-8")
            subprocess.run(["pandoc", str(src.name), "-o", str(Path(out).resolve()), f"--abbreviations={abbr}",
                            "--reference-doc", str(ref), "--resource-path", "."],
                           cwd=src.parent, check=True)
        finally:
            src.unlink()
    postprocess(out)
    print("written", out)


def cli(argv):
    """yzz.py ms build|check ..."""
    if argv[:1] == ["build"] and len(argv) >= 4:
        main(*argv[1:])
        argv = ["check", argv[3]]
    if argv[:1] == ["check"] and len(argv) >= 2:
        import docx_layout
        import zh_office
        bad = zh_office.docx(argv[1])
        print("LINT:", "OK" if not bad else "\n  - " + "\n  - ".join(bad))
        if "--no-render" not in argv:
            pdf, pngs = docx_layout.render(argv[1])
            print(f"Word PDF: {pdf}\n表格页 PNG {len(pngs)} 张: {pngs[0].parent if pngs else '-'}  ← 逐张查看再交付")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
