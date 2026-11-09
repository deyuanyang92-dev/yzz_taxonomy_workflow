"""lib/zh_office.py 回归测试：每个用户报告过的中文问题一条检查。"""
import sys
from pathlib import Path

import docx as pydocx
from docx.oxml.ns import qn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import zh_office  # noqa: E402


def _make(p: Path, text: str) -> None:
    d = pydocx.Document()
    r = d.add_paragraph().add_run(text)
    r.font.name = "Times New Roman"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    d.save(p)


def test_fullwidth_space_detected_and_removed(tmp_path):
    # 2026-10-09 用户报告：姓名：杨德援　　人员编号 在 Word 中显示 □□
    f = tmp_path / "a.docx"
    _make(f, "姓名：杨德援　　人员编号")
    assert any("全角空格" in s for s in zh_office.docx(f))
    zh_office.docx(f, fix=True)
    assert zh_office.docx(f) == []
    assert (tmp_path / "a.docx.bak").exists()


def test_fix_to_other_file_when_locked(tmp_path):
    f, o = tmp_path / "a.docx", tmp_path / "b.docx"
    _make(f, "测试“引号”")
    zh_office.docx(f, fix=True, out=o)
    assert zh_office.docx(o) == [] and zh_office.docx(f) != []


def test_ascii_only_untouched(tmp_path):
    f = tmp_path / "a.docx"
    _make(f, "plain English only")
    assert zh_office.docx(f) == []


def test_vertical_table_cell_detected_and_removed(tmp_path):
    # 2026-10-29 用户报告：申请书“十五五”时期 在 PDF/WPS 中字符重叠。
    # 根因：同页上方表格有竖排标签单元格(tbRl)，删掉竖排后恢复正常。
    f = tmp_path / "a.docx"
    d = pydocx.Document()
    cell = d.add_table(rows=1, cols=2).rows[0].cells[0]
    cell.text = "摘要"
    tcPr = cell._tc.get_or_add_tcPr()
    td = tcPr.makeelement(qn("w:textDirection"), {qn("w:val"): "tbRl"})
    tcPr.append(td)
    d.add_paragraph("“十五五”时期")
    d.save(f)
    assert any("竖排单元格" in s for s in zh_office.docx(f))
    zh_office.docx(f, fix=True)
    assert not any("竖排单元格" in s for s in zh_office.docx(f))


def test_txt_bom_crlf(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("中文\n第二行\n", encoding="utf-8")
    assert len(zh_office.txt(f)) == 2
    zh_office.txt(f, fix=True)
    assert zh_office.txt(f) == []
    assert f.read_bytes().startswith(b"\xef\xbb\xbf")


def test_xlsx_fullwidth_space_detected_and_fixed(tmp_path):
    """2026-10-11: zh check 原先跳过 .xlsx, 名录 Excel 无法按规定检查."""
    from openpyxl import Workbook
    p = tmp_path / "a.xlsx"
    wb = Workbook()
    wb.active["A1"] = "广东　大亚湾"
    wb.active["A2"] = "正常"
    wb.save(p)
    assert zh_office.xlsx(p) == ["全角空格 U+3000 1 个单元格"]
    zh_office.xlsx(p, fix=True)
    assert zh_office.xlsx(p) == []


def test_english_curly_quotes_not_eastasia(tmp_path):
    # 2026-11-09 用户报告：英文综述 'sanguinea-like' 的弯引号在 Word 中变全角、前后多空
    f = tmp_path / "a.docx"
    _make(f, "the ‘sanguinea-like’ group — see")
    assert zh_office.docx(f) == []          # 英文段落的共用标点不报
    d = pydocx.Document(f)
    d.paragraphs[0].runs[0]._element.rPr.rFonts.set(qn("w:hint"), "eastAsia")
    d.save(f)
    assert any("东亚字体" in s for s in zh_office.docx(f))
    zh_office.docx(f, fix=True)
    assert zh_office.docx(f) == []
    assert pydocx.Document(f).paragraphs[0].runs[0]._element.rPr.rFonts.get(qn("w:hint")) is None


def test_chinese_paragraph_quotes_still_eastasia(tmp_path):
    f = tmp_path / "a.docx"
    _make(f, "测试“引号”")
    assert any("hint" in s for s in zh_office.docx(f))
