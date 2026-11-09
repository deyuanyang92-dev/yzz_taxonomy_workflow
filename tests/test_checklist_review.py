"""modules/checklist/15_report.apply_review 回归测试 (2026-10-11 复核环节)."""
import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sp = importlib.util.spec_from_file_location("rep", ROOT / "modules/checklist/15_report.py")
rep = importlib.util.module_from_spec(sp)
sp.loader.exec_module(rep)


def test_apply_review(tmp_path):
    df = pd.DataFrame({"rid": ["a", "b", "c", "d"], "物种名（学名）": ["Perinereismuntia", "X y", "Syllis z", "N n"],
                       "采集地": ["", "", "", ""]})
    rv = tmp_path / "review"
    rv.mkdir()
    pd.DataFrame([
        {"rid": "a", "结论": "修改", "字段": "物种名（学名）", "新值": "Perinereis nuntia", "依据": "pdf190 种标题"},
        {"rid": "b", "结论": "删除", "字段": "", "新值": "", "依据": "引言中前人记录, 非本文"},
        {"rid": "c", "结论": "删除", "字段": "", "新值": "", "依据": "页眉裂虫科, 非沙蚕科"},
        {"rid": "d", "结论": "确认", "字段": "", "新值": "", "依据": "原书如此"},
    ]).to_csv(rv / "done_01.tsv", sep="\t", index=False)
    out, n = rep.apply_review(df.copy(), rv)
    assert n == 4
    assert list(out["rid"]) == ["a", "c", "d"]                      # b 删除; c 非本科 -> 保留但移另表
    assert out.set_index("rid").loc["a", "物种名（学名）"] == "Perinereis nuntia"
    assert out.set_index("rid").loc["c", "复核非本科"] == "Y"
    assert out.set_index("rid").loc["d", "人工核对"] == "已核: 原书如此"


def test_apply_resplit_moves_locality_and_rejects_fabrication(tmp_path):
    """2026-10-12: 采集地按内容划分; 只许移动已有文字, 不增不减."""
    df = pd.DataFrame({"rid": ["a", "b"],
                       "采集地": ["上海复兴岛（2标本）", "青岛"],
                       "note": ["海南三亚（25标本）。栖于河口泥滩。", "栖于泥滩。"]})
    rv = tmp_path / "resplit"
    rv.mkdir()
    pd.DataFrame([
        {"rid": "a", "采集地": "上海复兴岛（2标本）；海南三亚（25标本）", "note": "栖于河口泥滩。", "依据": "x"},
        {"rid": "b", "采集地": "青岛；威海", "note": "栖于泥滩。", "依据": "编造"},   # 多出"威海" -> 拒绝
    ]).to_csv(rv / "done_01.tsv", sep="\t", index=False)
    out, n, rej = rep.apply_resplit(df.copy(), rv)
    assert n == 1 and rej == ["b"]
    assert out.set_index("rid").loc["a", "采集地"] == "上海复兴岛（2标本）；海南三亚（25标本）"
    assert out.set_index("rid").loc["b", "采集地"] == "青岛"
