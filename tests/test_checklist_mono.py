"""modules/checklist/12_mono_extract.py 回归测试: 用户 2026-10-10 给的 CN01 (24) 突齿沙蚕示例等."""
import importlib.util
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "modules/checklist/12_mono_extract.py"
sp = importlib.util.spec_from_file_location("mono", P)
mono = importlib.util.module_from_spec(sp)
sp.loader.exec_module(mono)

PAGE = """(24）突齿沙蚕LeonnatesindicusKinberg，1866（图56)
Leonnates indicus Kinberg, 1866: 168; Qiu et Qian, 2000: 1113-1120, figs. 1-3.
标本采集地
广东大亚湾，海南陵水、新村，南海北部湾（水深29m）。在海南新
村的黎安，同栖的动物有海绵、石珊瑚和红角沙蚕Ceratonereis erythraeensis Fauvel等。
形态特征
大标本体长达96mm。
地理分布
万为热带种。分布于南海；印度洋，红海。
"""


def run(tmp_path, text):
    d = tmp_path / "ocr"
    d.mkdir()
    (d / "p0110.txt").write_text(text, encoding="utf-8")
    return mono.extract({"pid": "CN01", "citation": "孙瑞平, 杨德渐 2004", "_dir": d}, {})


def test_user_example_leonnates(tmp_path):
    rows = run(tmp_path, PAGE)
    spec = [r for r in rows if r["采集地类型"] == "研究标本"][0]
    assert spec["物种名（中文）"] == "突齿沙蚕"
    assert spec["物种名（学名）"] == "Leonnates indicus Kinberg, 1866"          # 从异名行补回空格
    assert spec["采集地"] == "广东大亚湾，海南陵水、新村，南海北部湾（水深29m）"
    assert spec["note"].startswith("在海南新村的黎安") and "形态" not in spec["note"]


def test_distribution_takes_fenbuyu_clause(tmp_path):
    rows = run(tmp_path, PAGE)
    dist = [r for r in rows if r["采集地类型"] == "文献记载分布"][0]
    assert dist["采集地"] == "南海；印度洋，红海"                               # 段首"万"去掉, 概括句进 note
    assert dist["note"] == "为热带种。"


def test_fig_residue_and_bad_chinese_name_flag():
    assert mono.FIG_RE.sub("", "Leonnates indicus Kinberg, 1866 〔") == "Leonnates indicus Kinberg, 1866"


def test_heading_residue_and_watermark():
    assert mono.split_section("标本采集地", "地青岛胶州湾（水深27m）。底质泥。")[0] == "青岛胶州湾（水深27m）"
    assert mono.split_section("标本采集地", "地中海沿岸。")[0] == "地中海沿岸"
    assert mono.joinlines(["福建三都澳、连DC", "江、厦门"]) == "福建三都澳、连江、厦门"


def test_user_example_discussion_to_note(tmp_path):
    """用户 2026-10-11 示例 (CN01 (3) 羽须鳃沙蚕): 采集地=海南三亚; 讨论段进 note; 地理分布不进采集地."""
    page = """(3）羽须鳃沙蚕DendronereispinnaticirrisGrube，1878（图33)
Dendronereis pinnaticirris Grube, 1878: 92-93, pl. IV, fig. 3c.
标本采集地
海南三亚。穴居于底泥中，降雨时盐度下降，从地内逸出可被潮水带
走。三亚金鸡岭桥头11月底退潮时的盐度为19.52‰。
形态特征
体长38mm。
地理分布
印度一西太平洋区热带海域咸淡水种。分布于海南岛近海河口区；印度恒河口。
讨论
赫列勃维奇（1963）和吴宝铃等（1963）均报道了海南三亚有河口鳃沙蚕
Dendronerei aestuarina Southern分布。
"""
    rows = run(tmp_path, page)
    spec = [r for r in rows if r["采集地类型"] == "研究标本"][0]
    assert spec["采集地"] == "海南三亚"
    assert spec["note"].startswith("穴居于底泥中") and spec["note"].endswith("19.52‰。")
    assert spec["讨论"].startswith("赫列勃维奇（1963）") and "aestuarina" in spec["讨论"]
