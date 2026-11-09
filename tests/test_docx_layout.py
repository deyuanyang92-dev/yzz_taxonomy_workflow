"""lib/docx_layout.py + lib/ms_build.py 回归测试：每条对应 2026-11-09 用户在 Word 中看到的问题。"""
import sys
from pathlib import Path

import docx as pydocx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import ms_build  # noqa: E402
import zh_office  # noqa: E402


def _issues(f):
    return zh_office.docx(f)


def test_nbsp_after_et_al_fixed(tmp_path):
    # Word 编辑标记下 "Zanol et al.°(2014" —— pandoc 插入的 U+00A0
    f = tmp_path / "a.docx"
    d = pydocx.Document()
    d.add_paragraph("Zanol et al. (2014: 93) and p. 85")
    d.save(f)
    assert any("U+00A0" in s for s in _issues(f))
    zh_office.docx(f, fix=True)
    assert not any("U+00A0" in s for s in _issues(f))
    assert " " not in pydocx.Document(f).paragraphs[0].text


def _table_doc(f, caption=True, widths_cm=(4, 4), cell="text", suppress=False):
    d = pydocx.Document()
    if caption:
        d.add_paragraph("Table 1. Caption.")
    t = d.add_table(rows=2, cols=len(widths_cm))
    for j, w in enumerate(widths_cm):
        for r in t.rows:
            r.cells[j].width = Cm(w)
            r.cells[j].text = cell
        t._tbl.tblGrid.findall(qn("w:gridCol"))[j].set(qn("w:w"), str(int(Cm(w).twips)))
    if suppress:
        p = t.rows[1].cells[0].paragraphs[0]
        p._p.get_or_add_pPr().append(OxmlElement("w:suppressLineNumbers"))
    d.save(f)


def test_suppress_line_numbers_in_cells_removed(tmp_path):
    # 每个单元格前的小黑块
    f = tmp_path / "a.docx"
    _table_doc(f, suppress=True)
    assert any("suppressLineNumbers" in s for s in _issues(f))
    zh_office.docx(f, fix=True)
    assert not any("suppressLineNumbers" in s for s in _issues(f))


def test_caption_keep_next_added(tmp_path):
    # 表头孤悬页底
    f = tmp_path / "a.docx"
    _table_doc(f)
    assert any("keepNext" in s for s in _issues(f))
    zh_office.docx(f, fix=True)
    assert not any("keepNext" in s for s in _issues(f))


def test_table_wider_than_text_block_reported(tmp_path):
    f = tmp_path / "a.docx"
    _table_doc(f, widths_cm=(10, 10))
    assert any("版心" in s for s in _issues(f))


def test_word_break_in_narrow_column_reported(tmp_path):
    # "Mossamb|ica-group"
    f = tmp_path / "a.docx"
    _table_doc(f, widths_cm=(1.2, 4), cell="Mossambica-group")
    assert any("拆词" in s for s in _issues(f))


def test_column_widths_never_below_longest_word():
    d = pydocx.Document()
    t = d.add_table(rows=3, cols=3)
    data = [["Group", "Name since 2010", "Later changes"],
            ["A", "Mossambica-group", "Now thought to hold five species " * 3],
            ["B-2", "Teretiuscula-group", "31 species " * 6]]
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            t.rows[i].cells[j].text = v
    w = ms_build.column_widths(t)
    assert sum(w) <= ms_build.USABLE_TW + 3
    for j in range(3):                       # real-metric floor (longest unbreakable chunk) respected
        floor = max(ms_build.cell_metrics(r.cells[j], i == 0)[1] for i, r in enumerate(t.rows))
        assert w[j] >= floor + ms_build.CELL_PAD - 1


def test_ms_build_output_passes_lint(tmp_path):
    md = tmp_path / "d.md"
    md.write_text("# A *Title*\n\n# 1. Intro\n\nSee Zanol et al. (2014: 93) and the 'sanguinea-like' group.\n\n"
                  "### 1.1 Sub\n\n**Table 1.** Caption.\n\n| Group | Name |\n|---|---|\n| A | Mossambica-group |\n\n"
                  "# References\n\n(x)\n\n# Figure legends\n\nNone.\n", encoding="utf-8")
    refs = tmp_path / "r.md"
    refs.write_text("# References\n\nZanol J. 2014. Title. *J* 1: 1.\n", encoding="utf-8")
    out = tmp_path / "o.docx"
    ms_build.main(str(md), str(refs), str(out))
    assert _issues(out) == []
    x = (tmp_path / "o.docx").read_bytes()
    assert b"SimSun" not in x                      # 英文稿不用宋体


def test_footer_suppress_line_numbers_removed(tmp_path):
    # 页脚页码前的小黑块
    f = tmp_path / "a.docx"
    d = pydocx.Document()
    d.add_paragraph("x")
    fp = d.sections[0].footer.paragraphs[0]
    fp._p.get_or_add_pPr().append(OxmlElement("w:suppressLineNumbers"))
    d.save(f)
    assert any("suppressLineNumbers" in s for s in _issues(f))
    zh_office.docx(f, fix=True)
    assert not any("suppressLineNumbers" in s for s in _issues(f))


def test_ms_build_pandoc_inserts_no_nbsp(tmp_path):
    md = tmp_path / "d.md"
    md.write_text("# T\n\n# 1. A\n\nZanol et al. (2014: p. 93).\n\n# References\n\n(x)\n", encoding="utf-8")
    refs = tmp_path / "r.md"
    refs.write_text("# References\n\nA. 2014. T.\n", encoding="utf-8")
    out = tmp_path / "o.docx"
    ms_build.main(str(md), str(refs), str(out))
    import zipfile
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert "\u00a0" not in xml
    assert b"suppressLineNumbers" not in zipfile.ZipFile(out).read("word/footer1.xml")
