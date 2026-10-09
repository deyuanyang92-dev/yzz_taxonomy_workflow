"""第二金标准: Travisia 有效种模式产地坐标, 对照臭海蛹项目人工核实表
   /mnt/n/大连-臭海蛹-2026/04_处理数据/Travisia_valid_species_type_localities_2026-10-04.xlsx  (文献核实的经纬度、精度、出处)

判定 (每个有效种):
  MISSING   人工表有坐标, 我们没有
  OK        距离 <= 容差: original 坐标 50 km; approximate 坐标 max(300 km, coord_uncertainty_km)
  FAR       超出容差 -> 打印出来逐条查原因
输出: 汇总 + FAR/MISSING 明细; 全部 OK/可解释 才算通过 (退出码 0)
用法: python3 modules/worms/tests/check_travisia.py
"""
import math, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD = Path("/mnt/n/大连-臭海蛹-2026/04_处理数据/Travisia_valid_species_type_localities_2026-10-04.xlsx")
c = pd.read_csv(ROOT / "projects/Travisia/02_原始数据/worms/coordinates.tsv", sep="\t", dtype=str, keep_default_na=False)
g = pd.read_excel(GOLD, sheet_name="Valid species", dtype=str).fillna("")


def km(a, b, c_, d):
    p = math.pi / 180
    h = math.sin((c_ - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c_ * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1, h)))


rows = []
for x in g.itertuples(index=False):
    sp, glat, glon = x[1], x[6], x[7]
    if not glat or not glon:
        continue
    m = c[c.scientific_name == sp]
    if not len(m) or not m.iloc[0].coord_lat:
        rows.append((sp, "MISSING", "", x[5][:60], "", ""))
        continue
    r = m.iloc[0]
    d = km(float(glat), float(glon), float(r.coord_lat), float(r.coord_lon))
    gold_approx = "approx" in str(x[8]).lower()   # 人工表自身是近似坐标时按宽容差
    tol = 50 if (r.coord_precision == "original" and not gold_approx) else max(300, float(r.coord_uncertainty_km or 0))
    rows.append((sp, "OK" if d <= tol else "FAR", f"{d:.0f} km (tol {tol:.0f})", x[5][:60], r.coord_basis, r.coord_detail[:90]))
R = pd.DataFrame(rows, columns=["species", "verdict", "distance", "gold type locality", "our basis", "our detail"])
print(R.verdict.value_counts().to_string())
pd.set_option("display.width", 250, "display.max_colwidth", 90)
bad = R[R.verdict != "OK"]
if len(bad):
    print(bad.to_string(index=False))
sys.exit(1 if len(bad) else 0)
