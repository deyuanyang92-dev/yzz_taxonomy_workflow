"""回归检查: WoRMS 网页 note (REST 无) 解析与 16 步 L2 判定. 读缓存, 不联网 (首次运行需先跑 worms 04 Marphysa).
用户 2026-11-08 发现 M. orientalis / M. aegypti 的模式重描述 note 丢失.
用法: python3 modules/worms/tests/check_source_notes.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
import importlib.util  # noqa: E402
from worms import client, source_notes  # noqa: E402

spec = importlib.util.spec_from_file_location("s16", ROOT / "modules/worms/23_species_literature.py")
s16 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s16)

CASES = [  # (AphiaID, source_id, use, page_web 含, note 含)
    (329257, "289103", "redescription", "202", "redescription from holotype"),          # M. orientalis Treadwell, 1936; Liu et al. 2018
    (1306160, "365863", "redescription", "25/37", "redescribed from holotype & paratypes"),  # M. aegypti; Martin et al. 2020
]
fails = 0
for aid, sid, use, pg, note in CASES:
    r = [x for x in source_notes(client().taxdetails_html(aid)) if x["source_id"] == sid and x["use"] == use]
    ok = bool(r) and pg in r[0]["page_web"] and note in r[0]["note"]
    fails += not ok
    print("PASS" if ok else "FAIL", aid, sid, r[:1])
for args, want in [(("redescription", "202", "redescription from holotype, the only specimen known"), "L2 模式标本重描述"),
                   (("redescription", "211 [redescription from holotype]", ""), "L2 模式标本重描述"),
                   (("redescription", "466, figures 13-21", "new records for Kaikoura"), "L4 重描述 (未注明模式)"),
                   (("original description", "", ""), "L3 原始描述"),
                   (("additional source", "", ""), "其他用途")]:
    got = s16.level(*args)
    fails += got != want
    print("PASS" if got == want else "FAIL", args, got)
sys.exit(1 if fails else 0)
